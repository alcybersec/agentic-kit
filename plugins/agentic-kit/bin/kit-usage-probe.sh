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
# `${HOME:-...}`, not `${HOME}`: under `set -u` an unset HOME aborts the script, and
# the abort is not silent -- it prints "HOME: unbound variable" to stderr, which the
# documented wiring puts straight into the user's status line. hooks/usage-gate.sh
# paid for this lesson on 2026-10-03; the sensor half had not learned it.
out="${CLAUDE_KIT_USAGE_FILE:-${HOME:-/nonexistent}/.claude/kit-usage.json}"
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
# `2>/dev/null` BEFORE the output redirect, and the order is the whole point: bash
# applies redirections left to right, so with `> "$tmp" 2>/dev/null` the failure of
# `> "$tmp"` is reported while stderr is still the real one, and bash prints
# "No such file or directory" into whatever the probe rides on -- the status line.
# Silencing stderr first means the failed redirect has nowhere to complain, and the
# `if` still sees the non-zero status. Do not "tidy" these back into source order.
if printf '%s\n' "$snapshot" 2>/dev/null > "$tmp"; then
  mv -f -- "$tmp" "$out" 2>/dev/null || rm -f -- "$tmp" 2>/dev/null || true
fi

if [ "$want_print" -eq 1 ]; then
  printf '%s' "$snapshot" | jq -r '
    [ (if .five_hour then "5h \(.five_hour.used_percentage | floor)%" else empty end),
      (if .seven_day then "7d \(.seven_day.used_percentage | floor)%" else empty end) ]
    | join(" ")' 2>/dev/null || true
fi
exit 0
