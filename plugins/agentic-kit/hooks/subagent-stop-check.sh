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

# The harness re-fires this hook after a block; blocking again only burns turns until
# its own cap (CLAUDE_CODE_STOP_HOOK_BLOCK_CAP). Its guidance: succeed while this is true.
[ "$(kit_in '.stop_hook_active')" != "true" ] || exit 0

# Source 1 (primary): the subagent's final message, handed over directly. No transcript
# shape to assume, and it is the text the agent actually ended on.
# Source 2: the subagent's OWN transcript (agent_transcript_path). `transcript_path` is the
# PARENT session's and is only a last resort: it can satisfy or fail the check on the
# orchestrator's words rather than the subagent's.
text=$(kit_in '.last_assistant_message | strings')
if [ -z "$text" ]; then
  transcript=$(kit_in '.agent_transcript_path | strings')
  { [ -n "$transcript" ] && [ -f "$transcript" ]; } || transcript=$(kit_in '.transcript_path | strings')
  [ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

  # The assistant's own text, one real line per line. JSONL entries are reduced to the
  # text blocks of assistant messages, so a note carried as an escaped-newline string is
  # un-escaped, and neither the dispatch prompt (user) nor a note typed into a file by a
  # tool call (tool_use) counts. A line that is not JSON passes through as-is. Two entry
  # shapes are handled: {role,content:str} (tested) and {message:{role,content:[{type:
  # text}]}} (assumed from Claude Code's format, UNVERIFIED against a live transcript).
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
fi

# Header at the start of a line (markdown bold or heading marks tolerated); the
# separator may be an em dash, en dash or hyphen. The ID must be real, so the
# format described as "TASK <ID> — ..." does not satisfy it.
if printf '%s\n' "$text" | grep -qE '^[[:space:]*#]*TASK [A-Za-z0-9._-]+ (—|–|-) (COMPLETE|PARTIAL|BLOCKED)'; then
  exit 0
fi

kit_deny "No handoff note in this subagent's output, so the task is not finished. Run /handoff now and emit the note as plain text, starting a line with: TASK <ID> — COMPLETE (or PARTIAL or BLOCKED), then OUTPUTS: (files changed), TESTS: (the exact command and its last line of output), FLOORS, DOWNSTREAM, NOTES, plus any role-specific lines. A note without a pasted test run is not accepted as evidence."
