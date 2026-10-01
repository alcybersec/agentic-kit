#!/usr/bin/env bash
# PreToolUse/Bash guard. Makes the atomic-commit, destructive-command and
# forge-exclusivity rules executable instead of advisory.
#
# Matches COMMAND STRINGS, so it is not a sandbox (design spec 6.2): it stops
# reflexive mistakes by a cooperative agent, not a determined one.
set -uo pipefail
set -f   # never let an unquoted word expand as a pathname glob
# Resolve the library relative to this script, not ${CLAUDE_PLUGIN_ROOT}: under
# `set -u` an unset variable would error before the inertness check could run.
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init

cmd=$(kit_in '.tool_input.command')
[ -n "$cmd" ] || exit 0

forge_kind=$(kit_q '.forge.kind')
forge_cli=$(kit_q '.forge.cli')
exclusive=$(kit_q '.forge.exclusive')
other=""
if [ "$exclusive" = "true" ]; then
  case "$forge_kind" in
    gitlab) other="gh" ;;
    github) other="glab" ;;
  esac
fi

ONLY="Commit explicit paths with 'git add <path>' and 'git commit --only <path> -m ...'."
skipq=""    # closing quote we are waiting for inside a commit message
is_commit=0

# Does a (possibly quote-opening) value leave a quote unterminated?
qopen() {
  local v="$1" q="${1:0:1}"
  case "$q" in
    \"|\') if [ "${#v}" -eq 1 ] || [ "${v: -1}" != "$q" ]; then skipq="$q"; fi ;;
  esac
}

check_commit() {
  local a expect=0 i c
  for a in "$@"; do
    if [ -n "$skipq" ]; then
      case "$a" in *"$skipq") skipq="" ;; esac
      continue
    fi
    if [ "$expect" -eq 1 ]; then expect=0; qopen "$a"; continue; fi
    case "$a" in
      --all) kit_deny "Blocked: 'git commit --all' commits whatever is modified, including other sessions' files. $ONLY" ;;
      --message|--file|--author|--date|--template|--reuse-message|--reedit-message) expect=1 ;;
      --*=*) qopen "${a#*=}" ;;
      --*) ;;
      -?*)
        for ((i = 1; i < ${#a}; i++)); do
          c="${a:i:1}"
          case "$c" in
            a) kit_deny "Blocked: 'git commit -a' commits whatever is modified, including other sessions' files. $ONLY" ;;
            m|F|C|c|t)
              if [ $((i + 1)) -lt ${#a} ]; then qopen "${a:i+1}"; else expect=1; fi
              break ;;
          esac
        done ;;
    esac
  done
}

check_segment() {
  local -a w
  read -ra w <<< "$1"
  local i=0 n=${#w[@]}
  # Peel env assignments and transparent wrappers off the front.
  while [ "$i" -lt "$n" ]; do
    if [[ "${w[i]}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then i=$((i + 1)); continue; fi
    case "${w[i]##*/}" in
      sudo|env|command|exec|nohup|time|nice|builtin)
        i=$((i + 1))
        while [ "$i" -lt "$n" ] && [[ "${w[i]}" == -* ]]; do i=$((i + 1)); done ;;
      *) break ;;
    esac
  done
  [ "$i" -lt "$n" ] || return 0
  local bin="${w[i]##*/}"
  local -a args=("${w[@]:i+1}")

  if [ -n "$other" ] && [ "$bin" = "$other" ]; then
    kit_deny "Blocked: this project's forge is ${forge_kind}; use '${forge_cli}', not '${other}'."
  fi

  local a
  case "$bin" in
    git)
      # Skip git's global options: -C <dir>, -c <k=v>, --git-dir=..., --no-pager.
      while [ "${#args[@]}" -gt 0 ]; do
        case "${args[0]}" in
          -C|-c|--git-dir|--work-tree|--namespace) args=("${args[@]:2}") ;;
          -*) args=("${args[@]:1}") ;;
          *) break ;;
        esac
      done
      [ "${#args[@]}" -gt 0 ] || return 0
      local sub="${args[0]}"; args=("${args[@]:1}")
      case "$sub" in
        add)
          for a in "${args[@]}"; do
            case "$a" in
              -A|--all|.|./|-[!-]*A*)
                kit_deny "Blocked: 'git add ${a}' stages every change in the tree, including other sessions' files. $ONLY" ;;
            esac
          done ;;
        commit) is_commit=1; check_commit "${args[@]}" ;;
        stash)
          kit_deny "Blocked: 'git stash' -- restoring a stash has itself leaked a peer agent's working tree into a commit. If foreign files appear in git status, stop and report to the Orchestrator; otherwise commit your own paths with 'git commit --only <path>'." ;;
        push)
          for a in "${args[@]}"; do
            case "$a" in
              --force|-f|+*|-[!-]*f*)
                kit_deny "Blocked: force push ('${a}'). It can destroy a peer session's commits. Ask the user, or use --force-with-lease, which refuses when the remote has moved." ;;
            esac
          done ;;
        reset)
          for a in "${args[@]}"; do
            [ "$a" = "--hard" ] && kit_deny "Blocked: 'git reset --hard' discards uncommitted work that may not be yours. Use 'git restore <path>' on a file you own, or ask the user."
          done ;;
      esac ;;
    rm)
      local rec=0 frc=0
      for a in "${args[@]}"; do
        case "$a" in
          --recursive) rec=1 ;;
          --force) frc=1 ;;
          --*) ;;
          -?*) case "$a" in *r*|*R*) rec=1 ;; esac
               case "$a" in *f*) frc=1 ;; esac ;;
        esac
      done
      if [ "$rec" -eq 1 ] && [ "$frc" -eq 1 ]; then
        kit_deny "Blocked: recursive forced 'rm'. Delete named files individually, and ask the user for anything broader."
      fi ;;
    docker|docker-compose)
      local sawdown=0 vol=0
      if [ "$bin" = "docker" ] && [ "${args[0]:-}" != "compose" ]; then return 0; fi
      for a in "${args[@]}"; do
        case "$a" in
          down) sawdown=1 ;;
          --volumes|-v) vol=1 ;;
        esac
      done
      if [ "$sawdown" -eq 1 ] && [ "$vol" -eq 1 ]; then
        kit_deny "Blocked: 'compose down -v' deletes named volumes, i.e. the data. Use 'docker compose down' alone."
      fi ;;
  esac
}

# Read/Edit denies already cover the file commands Claude Code recognizes in Bash
# (cat, head, tail, sed, tee) and redirection targets. This check is for the
# REMAINDER: readers it does not recognize (xxd, base64, strings) and interpreters.
#
# Match per WORD, anchored. An unanchored substring match over the whole command
# would block `cat .env.example` -- and a per-word match alone would still block
# `cp .env.example .env`, whose destination word IS the secret path. That copy is
# the remediation the deny message recommends, so a template-to-secret `cp` is
# exempted explicitly (it reads nothing secret).
mapfile -t secrets < <(jq -r '.secrets[]? | strings' "$KIT_LOCK" 2>/dev/null)
root="${KIT_LOCK%/.claude/kit.lock.json}"

check_secrets() {
  [ "${#secrets[@]}" -gt 0 ] || return 0
  local -a w ops=()
  read -ra w <<< "$1"
  if [ "${w[0]##*/}" = "cp" ]; then
    local x
    for x in "${w[@]:1}"; do [[ "$x" == -* ]] || ops+=("$x"); done
    if [ "${#ops[@]}" -eq 2 ]; then
      case "${ops[0]}" in *.example|*.sample|*.template|*.dist) return 0 ;; esac
    fi
  fi
  local word tok pattern pat
  while IFS= read -r word; do
    tok="$word"
    while :; do
      case "$tok" in
        ./*) tok="${tok#./}" ;;
        "$root"/*) tok="${tok#"$root"/}" ;;
        *) break ;;
      esac
    done
    [ -n "$tok" ] || continue
    for pattern in "${secrets[@]}"; do
      pat="${pattern#./}"
      [ -n "$pat" ] || continue
      # shellcheck disable=SC2254  # the pattern is a glob on purpose
      case "$tok" in
        $pat)
          kit_deny "Blocked: this command names '${pattern}', a secret path in this project's kit lock. Never read, copy or print it; if you need its shape, read the .example template instead." ;;
      esac
    done
  done < <(printf '%s\n' "$1" | tr -s ' \t\n"'"'"'()=,;|&<>`' '\n')
}

# Segment on ; | & newline ( ) and backtick, so a command merely *mentions* a
# rule inside an argument is not blocked, while $(...) and && chains are inspected.
while IFS= read -r seg; do
  [ -n "${seg//[[:space:]]/}" ] || continue
  check_segment "$seg"
  check_secrets "$seg"
done < <(printf '%s\n' "$cmd" | tr ';|&\n()`' '\n')

if [ "$is_commit" -eq 1 ] && [ "$(kit_q '.attribution.mention_assistant_in_commits')" != "true" ]; then
  if printf '%s' "$cmd" | grep -qiE 'claude|anthropic'; then
    kit_deny "Blocked by attribution policy: this project does not name the assistant in commit messages. Remove the Co-Authored-By / 'Claude' / 'Anthropic' text and commit again."
  fi
fi

exit 0
