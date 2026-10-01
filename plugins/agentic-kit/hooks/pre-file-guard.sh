#!/usr/bin/env bash
# PreToolUse/Read,Edit,Write,NotebookEdit guard. Denies the paths named in
# kit.lock.json "secrets", matched relative to the project root.
#
# Deliberately redundant with the Read/Edit deny rules in .claude/settings.json: this
# reads the lock at call time, is a second layer if settings.json is rewritten, and
# says which pattern matched.
set -uo pipefail
# Resolve the library relative to this script, not ${CLAUDE_PLUGIN_ROOT}: under
# `set -u` an unset variable would error before the inertness check could run.
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init

path=$(kit_in '.tool_input.file_path | strings')
[ -n "$path" ] || exit 0

root="${KIT_LOCK%/.claude/kit.lock.json}"
cwd=$(kit_in '.cwd | strings')
[ -n "$cwd" ] || cwd="$root"

# kit_lexnorm <abs-path> — collapse //, /./ and /../ without touching the filesystem.
# Pure parameter expansion so a newline in the path cannot split it.
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

case "$path" in
  /*) abs="$path" ;;
  *)  abs="$cwd/$path" ;;
esac

# Two views of the same path: what it is called, and where it really points. A
# symlink named innocent.txt that targets .env must be caught by its target.
lex=$(kit_lexnorm "$abs")
cands=("$lex")
if command -v realpath >/dev/null 2>&1; then
  res=$(realpath -m -- "$abs" 2>/dev/null) && [ "$res" != "$lex" ] && cands+=("$res")
  root_res=$(realpath -m -- "$root" 2>/dev/null) || root_res="$root"
else
  root_res="$root"
fi
root_lex=$(kit_lexnorm "$root")

while IFS= read -r pattern; do
  [ -n "$pattern" ] || continue
  pat="${pattern#./}"
  for c in "${cands[@]}"; do
    rel=""
    case "$c" in
      "$root_lex"/*) rel="${c#"$root_lex"/}" ;;
      "$root_res"/*) rel="${c#"$root_res"/}" ;;
      *) continue ;;   # outside the project: not ours to police
    esac
    # shellcheck disable=SC2254  # the pattern is a glob on purpose; case anchors it
    case "$rel" in
      $pat) kit_deny "Blocked: ${rel} matches the secret path pattern '${pattern}' (profile \"secrets\" in .claude/kit.yaml). Do not read, edit or print it. If you need the file's shape, use the committed .example template (e.g. .env.example); if you need a value, ask the user to supply it." ;;
    esac
  done
done < <(jq -r '.secrets[]? | strings' "$KIT_LOCK" 2>/dev/null)

exit 0
