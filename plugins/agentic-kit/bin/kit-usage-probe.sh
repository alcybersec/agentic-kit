#!/usr/bin/env bash
# Status-line sensor for subscription rate limits. Writes a snapshot, prints NOTHING.
#
# WHY A STATUS LINE AND NOT A HOOK. `rate_limits` exists in exactly one payload Claude
# Code hands to user code: the status line's. No hook event carries it — not SessionStart,
# not PreToolUse, none. So the only way for the kit to know how much of a 5-hour or 7-day
# window is spent is to read it where it is offered and leave it somewhere a hook can
# find. This script is the sensor; hooks/usage-gate.sh is the actuator.
#
# WHY NO SUBSCRIPTION DETECTION. `rate_limits` "appears only for claude.ai Pro and Max
# subscribers". Its absence IS the API-key case, so there is nothing to detect: no
# rate_limits, no snapshot, no pause. The same shape as the kit's inertness rule.
#
# Each window is independently absent, and Claude Code drops one once its `resets_at`
# passes — so a missing window means "no limit in force", never "zero used".
#
# Wire it into your status line, which may already print other things:
#
#     input=$(cat)
#     printf '%s' "$input" | bash ~/.claude/plugins/.../bin/kit-usage-probe.sh
#     # ... then print your own line from "$input" as usual
#
# It writes ~/.claude/kit-usage.json (per ACCOUNT, not per project: a rate limit is not a
# property of a repository) and prints nothing, so it cannot disturb a status line's
# layout. Pass --print for a compact segment if you want one.
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
out="${CLAUDE_KIT_USAGE_FILE:-${HOME}/.claude/kit-usage.json}"
want_print=0
[ "${1:-}" = "--print" ] && want_print=1

input=""
IFS= read -r -d '' input 2>/dev/null || true
[ -n "$input" ] || exit 0

snapshot=$(printf '%s' "$input" | jq -c --argjson now "$(date +%s)" '
  if (.rate_limits | type) != "object" then empty
  else {
    read_at: $now,
    five_hour: (.rate_limits.five_hour // null),
    seven_day: (.rate_limits.seven_day // null)
  }
  | if (.five_hour == null and .seven_day == null) then empty else . end
  end' 2>/dev/null) || exit 0

if [ -z "$snapshot" ]; then
  # No windows in force: an API key, a gateway without limits, or before the session's
  # first API response. Remove any snapshot rather than leave a stale one behind — an old
  # reading is worse than none, because the gate would act on it.
  rm -f -- "$out" 2>/dev/null || true
  exit 0
fi

# Write via a temporary file in the same directory: the gate may read this at any moment
# and must never see a half-written object.
mkdir -p -- "${out%/*}" 2>/dev/null || true
tmp="${out}.$$"
if printf '%s\n' "$snapshot" > "$tmp" 2>/dev/null; then
  mv -f -- "$tmp" "$out" 2>/dev/null || rm -f -- "$tmp" 2>/dev/null || true
fi

if [ "$want_print" -eq 1 ]; then
  printf '%s' "$snapshot" | jq -r '
    [ (if .five_hour then "5h \(.five_hour.used_percentage | floor)%" else empty end),
      (if .seven_day then "7d \(.seven_day.used_percentage | floor)%" else empty end) ]
    | join(" ")' 2>/dev/null || true
fi
exit 0
