#!/usr/bin/env bash
# PreToolUse/Read,Edit,Write,NotebookEdit guard. Denies the paths named in
# kit.lock.json "secrets", matched relative to the project root.
#
# Redundant with the Read/Edit deny rules in .claude/settings.json on purpose: this reads
# the lock at call time and explains which pattern matched. It is not a containment
# boundary. Path logic lives in lib/kitlock.sh (shared with the ownership guard).
set -uo pipefail
# Resolve the library relative to this script, not ${CLAUDE_PLUGIN_ROOT}: under
# `set -u` an unset variable would error before the inertness check could run.
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init

path=$(kit_in '.tool_input.file_path | strings')
[ -n "$path" ] || exit 0

kit_candidates "$path" "$(kit_in '.cwd | strings')" || exit 0   # outside the project

# A committed *.example / *.sample / *.template / *.dist file is not the secret --
# it is the very thing the deny message below tells the agent to read instead, so
# blocking it recommended a path this guard refused.
kit_drop_templates || exit 0

patterns=$(jq -r '.secrets[]? | strings' "$KIT_LOCK" 2>/dev/null)
if kit_match_glob "$patterns"; then
  kit_deny "Blocked: ${KIT_MATCHED_REL} matches the secret path pattern '${KIT_MATCHED}' (profile \"secrets\" in .claude/kit.yaml). Do not read, edit or print it. If you need the file's shape, use the committed .example template (e.g. .env.example); if you need a value, ask the user to supply it."
fi
exit 0
