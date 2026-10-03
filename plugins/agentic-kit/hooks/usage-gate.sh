#!/usr/bin/env bash
# PreToolUse/Agent,Task. Stops the dispatch loop when the account's rate-limit window is
# nearly spent, and tells the Orchestrator how to park and when to come back.
#
# WHAT IT BLOCKS, AND WHAT IT DELIBERATELY DOES NOT. Only new dispatches. The Orchestrator
# keeps Read, Edit, Write and Bash, because the thing it must do next is record where the
# work stopped — a gate that blocked everything would prevent the parking it demands.
#
# WHERE THE NUMBERS COME FROM. `rate_limits` reaches user code in exactly one payload, the
# status line's; no hook event carries it. bin/kit-usage-probe.sh is the sensor and writes
# ~/.claude/kit-usage.json. So this gate is only as live as that wiring: with no snapshot
# it does nothing at all, which is also the correct behaviour for an API key, where
# `rate_limits` never appears. /kit-doctor reports whether the probe is wired.
#
# STALE READINGS FAIL OPEN. A snapshot older than `usage.stale_after_s` is ignored. The
# status line stops being invoked when a session is not rendering, and pausing autonomous
# work on a reading from an hour ago would stop work that could have continued. The cost
# of that choice is stated plainly: this gate reduces overrun, it does not guarantee
# against it.
set -uo pipefail
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init

# `${HOME:-...}`, not `${HOME}`: these hooks run under `set -u` with whatever environment
# the harness provides, and HOME is not guaranteed to be in it. The first version died on
# an unbound variable — which, being an exit code other than 2, Claude Code reads as
# "continue", so the gate would have been silently absent.
snap="${CLAUDE_KIT_USAGE_FILE:-${HOME:-/nonexistent}/.claude/kit-usage.json}"
[ -f "$snap" ] || exit 0

five_pct=""; seven_pct=""; stale_after=""
kit_read_nul five_pct seven_pct stale_after < <(jq -j '
  ((.usage.five_hour_pct? // 0) | tostring), "\u0000",
  ((.usage.seven_day_pct? // 95) | tostring), "\u0000",
  ((.usage.stale_after_s? // 900) | tostring), "\u0000"' "$KIT_LOCK" 2>/dev/null)

# One jq decides everything that needs arithmetic: whether the reading is fresh, which
# window is over its threshold, how far over, and when it resets.
verdict=""; window=""; used=""; resets=""
# One jq decides everything needing arithmetic: whether the reading is fresh, which window
# is over its threshold, how far over, and when it resets. `label` is a RESERVED WORD in
# jq, so the window's name is `$name` — the first draft used `$label` and failed to
# compile, which `2>/dev/null` turned into silence and a gate that never fired.
kit_read_nul verdict window used resets < <(jq -j \
  --argjson now "$(date +%s)" \
  --argjson stale "${stale_after:-900}" \
  --argjson five "${five_pct:-90}" \
  --argjson seven "${seven_pct:-95}" '
  def over($w; $limit; $name):
    # $limit == 0 disables the window entirely. The 5-hour window ships disabled because
    # the wait-and-continue that Claude Code runs itself picks an interrupted task back up
    # after a reset under 24 hours out, and pausing before the limit means it never arms.
    # (No apostrophes in here: this comment is inside a single-quoted jq program.)
    if $limit > 0 and ($w | type) == "object" and ($w.used_percentage // 0) >= $limit
    then {name: $name, used: $w.used_percentage, resets: ($w.resets_at // 0)}
    else empty end;
  def fields($a; $b; $c; $d): ($a, "\u0000", $b, "\u0000", $c, "\u0000", $d, "\u0000");
  if (($now - (.read_at // 0)) > $stale) then fields("stale"; ""; ""; "")
  else
    ([ over(.five_hour; $five; "5-hour"), over(.seven_day; $seven; "7-day") ]
     | sort_by(-.used)) as $hits
    | if ($hits | length) == 0 then fields("ok"; ""; ""; "")
      else fields("over"; $hits[0].name;
                  ($hits[0].used | floor | tostring);
                  ($hits[0].resets | tostring))
      end
  end' "$snap" 2>/dev/null)

[ "$verdict" = "over" ] || exit 0

when="unknown"
if [ "${resets:-0}" -gt 0 ] 2>/dev/null; then
  when=$(date -d "@$resets" '+%H:%M on %Y-%m-%d' 2>/dev/null || echo "epoch $resets")
fi

# How the user gets going again depends on how far off the reset is, and the difference is
# Claude Code's own behaviour, not the kit's: it starts a wait-and-continue by itself only
# for a reset less than 24 hours away.
far=0
if [ "${resets:-0}" -gt 0 ] 2>/dev/null; then
  [ $(( resets - $(date +%s) )) -gt 86400 ] && far=1
fi
if [ "$far" -eq 1 ]; then
  resume="Claude Code does NOT start its own wait-and-continue for a reset more than 24 hours away, so nothing will resume this by itself. Tell the user they can arm one now from /rate-limit-options (\"Wait here, then continue automatically\" keeps counting down past 24 hours, as long as this session stays open), or simply come back after ${when} and run /next-task — the plan entry above is what makes that possible."
else
  resume="This reset is less than 24 hours away, so if work had continued until the limit actually stopped it, Claude Code would have waited and picked the task up by itself. Stopping short of the limit is what prevents that, which is why five_hour_pct ships at 0. Tell the user they can resume with /next-task after ${when}, or lower this threshold to 0 to let future runs ride into the limit and be continued automatically."
fi

kit_deny "Paused: ${used}% of this account's ${window} limit is spent, at or past the ${window} threshold in the profile's \`usage\`. Starting another task now risks running out mid-task, which leaves a role's work half-done and unrecorded.

Do this, in order, and then stop:
  1. Record the state in the plan: move the in-flight task to '## Active' with what is done and what remains. This is the durable half — do it first, because it is what lets any later session pick the work up.
  2. ${resume}
  3. Say in one line that you have paused, which window, and how work resumes.

Do not retry this dispatch, and do not start the task yourself instead."
