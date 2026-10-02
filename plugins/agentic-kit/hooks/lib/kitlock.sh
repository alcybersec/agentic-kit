# shellcheck shell=bash
# Shared hook preamble. Sourced, not executed.
#
# Contract: every hook in this plugin is INERT outside a kit project. A missing or
# unparseable .claude/kit.lock.json is the normal case — the plugin is installed
# machine-wide and most repositories are not kit projects.
#
# Every guard below ends in `exit 0`, silently: nothing on stdout or stderr.
#
# Sets KIT_LOCK (path) and KIT_INPUT (raw stdin) as PLAIN shell variables, plus
# kit_q()/kit_in() to query them.
#
# KIT_INPUT is deliberately NOT exported. An exported variable is copied into every
# child process's environment, and Linux caps a single environment string at
# MAX_ARG_STRLEN (32 pages, 131072 bytes): past that, execve fails with E2BIG and
# EVERY child dies -- including the `jq` these helpers run. The hook then reads an
# empty command and exits 0, so a payload over ~128 KB silently disarmed the whole
# guard layer. A long Bash heredoc reaches that, and a verbose subagent's
# `last_assistant_message` reaches it easily, which made the handoff gate pass
# precisely for the agents that said the most. Nothing needs it in the environment:
# every consumer is in this same shell and receives it through a pipe.
#
# Path matching (kit_lexnorm, kit_candidates, kit_match_glob):
#   kit_candidates <file_path> <cwd>   fills KIT_CANDS with project-relative spellings of
#       the path (lexical, and the realpath target so a symlink is caught by name AND by
#       target). Returns 1 when none is inside the project: "not ours to police", which is
#       distinct from "inside but no match".
#   kit_match_glob <patterns>          newline-separated globs, leading "./" optional;
#       sets KIT_MATCHED (the pattern) and KIT_MATCHED_REL (the candidate) for the first
#       match and returns 0, else returns 1. No stdout: callers need the vars, not a subshell.
#
# Task 12b's per-role ownership guard depends on these exact semantics. In particular:
# `case` anchors the WHOLE string, so ".env" must never match ".env.example"; and `**`
# in a bash case glob spans "/", so "secrets/**" matches "secrets/db/pw.txt". Patterns
# are root-anchored: "./.env" does not cover "sub/.env".

kit_bail_ok() { exit 0; }

kit_init() {
  command -v jq >/dev/null 2>&1 || kit_bail_ok

  # A builtin read, not `$(cat)`. These hooks run on the hot path of every tool call,
  # and `cat` is a whole process to do what `read` does in the shell. `read -d ''`
  # stops at the first NUL — which JSON never contains — so it consumes stdin to EOF
  # and then returns non-zero for having found no delimiter. That status is the normal
  # case, so it is ignored and emptiness is checked instead.
  IFS= read -r -d '' KIT_INPUT 2>/dev/null || true
  [ -n "${KIT_INPUT:-}" ] || kit_bail_ok
  printf '%s' "$KIT_INPUT" | jq -e 'type == "object"' >/dev/null 2>&1 || kit_bail_ok

  local root="${CLAUDE_PROJECT_DIR:-}"
  if [ -z "$root" ]; then
    root=$(printf '%s' "$KIT_INPUT" | jq -r '.cwd // empty | strings' 2>/dev/null)
  fi
  if [ -z "$root" ] || [ ! -d "$root" ]; then kit_bail_ok; fi

  KIT_LOCK="$root/.claude/kit.lock.json"
  [ -f "$KIT_LOCK" ] || kit_bail_ok
  # Compare the output: `jq -e` exits 0 on an EMPTY file (no input, no output), which
  # would let a zero-byte lock through as if it were a profile.
  [ "$(jq -r 'type' "$KIT_LOCK" 2>/dev/null)" = "object" ] || kit_bail_ok

  export KIT_LOCK   # a short path, and `kit_q` hands it to jq as an argument
}

# kit_q <jq-filter> — query the lock, empty string when absent
kit_q() { jq -r "$1 // empty" "$KIT_LOCK" 2>/dev/null; }

# kit_in <jq-filter> — query the hook payload
kit_in() { printf '%s' "$KIT_INPUT" | jq -r "$1 // empty" 2>/dev/null; }

# kit_lexnorm <abs-path> — collapse //, /./ and /../ without touching the filesystem.
# Pure parameter expansion so a newline in the path cannot split it, and no `dirname`.
kit_lexnorm() {
  local rest="${1#/}" seg out=""
  while :; do
    seg="${rest%%/*}"
    case "$seg" in
      ''|.) ;;
      ..)   out="${out%/*}" ;;
      *)    out="$out/$seg" ;;
    esac
    case "$rest" in */*) rest="${rest#*/}" ;; *) break ;; esac
  done
  printf '%s' "${out:-/}"
}

# kit_candidates <file_path> <cwd> — see header. Needs KIT_LOCK (after kit_init).
kit_candidates() {
  local path="$1" cwd="$2" root abs lex res root_lex root_res c
  root="${KIT_LOCK%/.claude/kit.lock.json}"
  [ -n "$cwd" ] || cwd="$root"
  case "$path" in /*) abs="$path" ;; *) abs="$cwd/$path" ;; esac
  lex=$(kit_lexnorm "$abs")
  root_lex=$(kit_lexnorm "$root"); root_res="$root_lex"
  local -a abss=("$lex")
  if command -v realpath >/dev/null 2>&1; then
    res=$(realpath -m -- "$abs" 2>/dev/null) && [ "$res" != "$lex" ] && abss+=("$res")
    root_res=$(realpath -m -- "$root" 2>/dev/null) || root_res="$root_lex"
  fi
  KIT_CANDS=(); export KIT_CANDS
  for c in "${abss[@]}"; do
    case "$c" in
      "$root_lex"/*) KIT_CANDS+=("${c#"$root_lex"/}") ;;
      "$root_res"/*) KIT_CANDS+=("${c#"$root_res"/}") ;;
    esac
  done
  [ "${#KIT_CANDS[@]}" -gt 0 ]
}

# kit_match_glob <newline-separated patterns> — see header.
kit_match_glob() {
  local pattern pat c
  while IFS= read -r pattern; do
    [ -n "$pattern" ] || continue
    pat="${pattern#./}"
    for c in "${KIT_CANDS[@]}"; do
      # shellcheck disable=SC2254  # the pattern is a glob on purpose; case anchors it
      case "$c" in $pat) KIT_MATCHED="$pattern"; KIT_MATCHED_REL="$c"; export KIT_MATCHED KIT_MATCHED_REL; return 0 ;; esac
    done
  done <<<"$1"
  return 1
}

# kit_read_nul <var>... — read NUL-delimited fields from stdin into those variables, in
# order. Pair it with `jq -j` emitting `field, "\u0000"` per field.
#
# The point is ONE jq process instead of one per question: these hooks run on the hot
# path of every tool call, and a jq call is ~20 ms. The delimiter must be NUL rather
# than newline, because the values are not newline-free — a `git commit -m` message
# spans lines, and the first version of this read line-by-line and silently truncated
# the command at the first newline, so the attribution check stopped firing. A list
# field is passed as ONE value with newlines inside it, which is already the format
# kit_match_glob expects.
kit_read_nul() {
  local _v
  for _v in "$@"; do
    # Non-zero at EOF without a delimiter is the normal case for the last field.
    IFS= read -r -d '' "$_v" || true
  done
}

# kit_is_template <path> — true for a committed example/sample/template file.
#
# `./secrets/**` otherwise swallows `secrets/prod.yaml.example`, so the deny
# message recommended reading a file the same deny blocked. Checked on the LAST
# path component only: a directory named `examples/` holding real material is not
# exempt, and neither is `.env.example.bak`.
kit_is_template() {
  # `?*` requires a stem: `*` matches the empty string, so a file named exactly
  # `.example` would otherwise be exempt without being a template of anything.
  case "${1##*/}" in
    ?*.example|?*.sample|?*.template|?*.dist) return 0 ;;
  esac
  return 1
}

# kit_drop_templates — drop template spellings from KIT_CANDS, in place. Returns 1
# when nothing is left to judge.
#
# Per candidate, deliberately: a symlink NAMED `x.example` that points at the real
# secret keeps its realpath candidate and is still blocked by the target's name.
kit_drop_templates() {
  local keep=() c
  for c in "${KIT_CANDS[@]}"; do
    kit_is_template "$c" || keep+=("$c")
  done
  KIT_CANDS=(${keep[@]+"${keep[@]}"}); export KIT_CANDS
  [ "${#KIT_CANDS[@]}" -gt 0 ]
}

# kit_deny <reason> — block the tool call, per the Claude Code hook contract.
#
# The reason is PROSE on STDERR, and the exit code does the blocking.
# Claude Code reads a hook's decision object from *stdout* ("your hook's stdout
# must contain only the JSON object"), and when a PreToolUse hook exits 2 it
# blocks the call and feeds the hook's *stderr* to the agent as the reason.
# Writing the object to stderr therefore got the worst of both: the decision was
# never read, so only `exit 2` blocked anything, and the remediation advice
# reached the agent as a raw JSON blob instead of a sentence it could act on.
#
# Prose + exit 2 is preferred over the stdout object because there is no schema
# to drift against: no `hookEventName` to omit, no per-event difference between
# `permissionDecision` and a top-level `decision`. Nothing is printed to stdout,
# because anything there would be parsed as a decision object.
kit_deny() {
  printf '%s\n' "$1" >&2
  exit 2
}
