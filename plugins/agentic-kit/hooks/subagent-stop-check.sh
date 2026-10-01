#!/usr/bin/env bash
# SubagentStop. A task is not finished until it has emitted a handoff note.
# Blocks on absence, so it is deliberately lenient about spelling: a false
# positive blocks work that was in fact complete.
set -uo pipefail
# Resolve the library relative to this script, not ${CLAUDE_PLUGIN_ROOT}: under
# `set -u` an unset variable would error before the inertness check could run.
# Pure parameter expansion, no `dirname`: PATH may hold nothing at all.
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init

transcript=$(kit_in '.transcript_path')
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

# The assistant's own text, one real line per line. JSONL entries are reduced to
# the text blocks of assistant messages, so a note carried as an escaped-newline
# string is un-escaped, and neither the dispatch prompt (user) nor a note typed
# into a file by a tool call (tool_use) counts as an emitted note. A line that is
# not JSON passes through as-is, so a plain-text transcript is still searched.
text=$(jq -R -r '
  . as $l | (try ($l | fromjson) catch null) as $o
  | if ($o | type) != "object" then $l
    else
      (($o.role // $o.message.role) // "") as $role
      | if $role != "assistant" then empty
        else ($o.content // $o.message.content // empty)
          | if type == "string" then .
            elif type == "array" then .[] | select(type == "object" and .type == "text") | .text | strings
            else empty end
        end
    end' "$transcript" 2>/dev/null) || text=""

# Header at the start of a line (markdown bold or heading marks tolerated); the
# separator may be an em dash, en dash or hyphen. The ID must be real, so the
# format described as "TASK <ID> — ..." does not satisfy it.
if printf '%s\n' "$text" | grep -qE '^[[:space:]*#]*TASK [A-Za-z0-9._-]+ (—|–|-) (COMPLETE|PARTIAL|BLOCKED)'; then
  exit 0
fi

kit_deny "No handoff note in this subagent's output, so the task is not finished. Run /handoff now and emit the note as plain text, starting a line with: TASK <ID> — COMPLETE (or PARTIAL or BLOCKED), then OUTPUTS: (files changed), TESTS: (the exact command and its last line of output), FLOORS, DOWNSTREAM, NOTES, plus any role-specific lines. A note without a pasted test run is not accepted as evidence."
