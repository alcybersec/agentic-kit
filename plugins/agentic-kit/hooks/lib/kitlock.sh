# shellcheck shell=bash
# Shared hook preamble. Sourced, not executed.
#
# Contract: every hook in this plugin is INERT outside a kit project. A missing or
# unparseable .claude/kit.lock.json is the normal case — the plugin is installed
# machine-wide and most repositories are not kit projects.
#
# Every guard below ends in `exit 0`, silently: nothing on stdout or stderr.
#
# Exports: KIT_LOCK (path), KIT_INPUT (raw stdin), and kit_q() to query the lock.

kit_bail_ok() { exit 0; }

kit_init() {
  command -v jq >/dev/null 2>&1 || kit_bail_ok

  KIT_INPUT=$(cat 2>/dev/null) || kit_bail_ok
  [ -n "$KIT_INPUT" ] || kit_bail_ok
  printf '%s' "$KIT_INPUT" | jq -e 'type == "object"' >/dev/null 2>&1 || kit_bail_ok

  local root="${CLAUDE_PROJECT_DIR:-}"
  if [ -z "$root" ]; then
    root=$(printf '%s' "$KIT_INPUT" | jq -r '.cwd // empty | strings' 2>/dev/null)
  fi
  if [ -z "$root" ] || [ ! -d "$root" ]; then kit_bail_ok; fi

  KIT_LOCK="$root/.claude/kit.lock.json"
  [ -f "$KIT_LOCK" ] || kit_bail_ok
  jq -e 'type == "object"' "$KIT_LOCK" >/dev/null 2>&1 || kit_bail_ok

  export KIT_INPUT KIT_LOCK
}

# kit_q <jq-filter> — query the lock, empty string when absent
kit_q() { jq -r "$1 // empty" "$KIT_LOCK" 2>/dev/null; }

# kit_in <jq-filter> — query the hook payload
kit_in() { printf '%s' "$KIT_INPUT" | jq -r "$1 // empty" 2>/dev/null; }

# kit_deny <reason> — block the tool call, per the Claude Code hook contract
kit_deny() {
  jq -nc --arg m "$1" \
    '{hookSpecificOutput: {permissionDecision: "deny"}, systemMessage: $m}' >&2
  exit 2
}
