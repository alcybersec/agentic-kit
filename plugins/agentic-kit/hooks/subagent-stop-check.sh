#!/usr/bin/env bash
# SubagentStop. A task is not finished until it has emitted a handoff note.
# Blocks on absence, so it is deliberately lenient about spelling: a false
# positive blocks work that was in fact complete.
#
# WHAT THIS HOOK CAN PROMISE. It can only ever block ONCE: on the retry the harness
# sets stop_hook_active and this hook returns success (below). An agent that never
# produces a note is nudged a single time and then allowed to stop. That is the
# harness's intended Stop-hook semantics, not a defect, but it means the hook PROMPTS
# for a handoff note and cannot FORCE one. The Orchestrator remains responsible for
# validating the handoff (strategy.md section 9: a note without a pasted run is not
# evidence and the Orchestrator re-runs the tests itself).
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

# The note must appear in AT LEAST ONE source; block only when neither has it. "First
# source decides" would block a note emitted earlier whenever the agent adds any closing
# remark after it ("Done.").
#   1. last_assistant_message: the subagent's final message, handed over directly.
#   2. the subagent's OWN transcript (agent_transcript_path). `transcript_path` is the
#      PARENT session's and is only a fallback when the former is unreadable: it can
#      satisfy or fail the check on the orchestrator's words rather than the subagent's.
re='^[[:space:]*#]*TASK [A-Za-z0-9._-]+ (—|–|-) (COMPLETE|PARTIAL|BLOCKED)'
# Header at the start of a line (markdown bold or heading marks tolerated); the
# separator may be an em dash, en dash or hyphen. The ID must be real, so the
# format described as "TASK <ID> — ..." does not satisfy it.

msg=$(kit_in '.last_assistant_message | strings')
if [ -n "$msg" ] && printf '%s\n' "$msg" | grep -qE "$re"; then exit 0; fi

transcript=$(kit_in '.agent_transcript_path | strings')
{ [ -n "$transcript" ] && [ -f "$transcript" ]; } || transcript=$(kit_in '.transcript_path | strings')
if [ -z "$transcript" ] || [ ! -f "$transcript" ]; then
  # Nothing to read the transcript from: judge the message alone, or stay inert.
  [ -n "$msg" ] || exit 0
else
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
  if printf '%s\n' "$text" | grep -qE "$re"; then exit 0; fi
fi

kit_deny "No handoff note in this subagent's output, so the task is not finished. Run /handoff now and emit the note as plain text, starting a line with: TASK <ID> — COMPLETE (or PARTIAL or BLOCKED), then OUTPUTS: (files changed), TESTS: (the exact command and its last line of output), FLOORS, DOWNSTREAM, NOTES, plus any role-specific lines. A note without a pasted test run is not accepted as evidence."
