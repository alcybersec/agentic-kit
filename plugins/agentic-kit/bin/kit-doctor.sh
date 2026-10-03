#!/usr/bin/env bash
# Fire every guard with a payload it MUST refuse, and report which ones did.
#
# Why this exists. Every hook in this kit exits 0 when it cannot do its job: no
# jq, no lock, an unparseable lock, a renamed or deleted script. That is the
# correct default for a plugin installed machine-wide (design spec §4.3) and it
# means a DISARMED guard is indistinguishable from a correctly inert one from the
# outside. Nothing else in the kit can tell you which you have.
#
# Exit 0 when every check passed or was skipped for a stated reason; 1 otherwise.
# Read-only: it writes nothing outside a temporary directory it removes.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$PWD}"
plugin="${BASH_SOURCE[0]%/*}/.."
lock="$root/.claude/kit.lock.json"
fails=0
probe=""
tmp=$(mktemp -d) || { echo "kit-doctor: cannot create a temporary directory"; exit 1; }
trap 'rm -rf "$tmp"' EXIT

say()  { printf '%-34s %-7s %s\n' "$1" "$2" "${3:-}"; }
bad()  { fails=$((fails + 1)); say "$1" "FAIL" "$2"; }
ok()   { say "$1" "ok" "${2:-}"; }
skip() { say "$1" "skip" "$2"; }
# Prints, never fails: for findings whose remedy is a judgement call. A FAIL that
# cannot be cleared is a FAIL people learn to scroll past.
note() { say "$1" "note" "$2"; }

printf '%-34s %-7s %s\n' "CHECK" "RESULT" "DETAIL"
printf '%s\n' "-------------------------------------------------------------------------"

# --- preconditions --------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  bad "jq on PATH" "absent -- EVERY hook in this kit exits 0 without it, silently"
  echo
  echo "Nothing else can be checked: install jq and re-run."
  exit 1
fi
ok "jq on PATH" "$(jq --version 2>/dev/null)"

if [ ! -f "$lock" ]; then
  bad ".claude/kit.lock.json" "absent -- the kit is not installed in $root"
  echo
  echo "Run the installer, or re-render: kitgen render --profile .claude/kit.yaml --out ."
  exit 1
fi
if [ "$(jq -r 'type' "$lock" 2>/dev/null)" != "object" ]; then
  bad ".claude/kit.lock.json" "not a JSON object -- every hook is inert"
  exit 1
fi
ok ".claude/kit.lock.json" "readable"

# §5.1: the lock is generated FROM kit.yaml, so a newer yaml means hand-edited drift.
if [ -f "$root/.claude/kit.yaml" ] && [ "$root/.claude/kit.yaml" -nt "$lock" ]; then
  bad "lock is current" "kit.yaml is newer than kit.lock.json -- hooks read the lock, so your edit is not in effect. Re-render."
else
  ok "lock is current"
fi

# --- each guard must refuse a payload it is supposed to refuse -------------
# run_guard <label> <script> <payload-json> [argv...]
run_guard() {
  local label="$1" script="$2" payload="$3"; shift 3
  if [ ! -f "$script" ]; then
    bad "$label" "script missing: $script"
    return
  fi
  local out rc
  # A herestring, not `printf | bash`. A guard that refuses early exits without
  # draining stdin, the writer then dies of SIGPIPE, and `pipefail` would report 141
  # instead of the guard's own 2 -- turning a correct refusal into "neither allow nor
  # block", at random, under load. The same idiom cost the stop-check gate a false
  # block; see hooks/lib/kitlock.sh.
  out=$(CLAUDE_PROJECT_DIR="$root" bash "$script" "$@" <<<"$payload" 2>&1)
  rc=$?
  case "$rc" in
    2) if [ -n "${out//[[:space:]]/}" ]; then
         ok "$label" "refused, and said why"
       else
         bad "$label" "refused with no message -- the agent is told nothing"
       fi ;;
    0) bad "$label" "ALLOWED a payload that must be refused -- this guard is not protecting you" ;;
    *) bad "$label" "exit $rc (neither allow nor block): ${out%%$'\n'*}" ;;
  esac
}

run_guard "pre-bash-guard / sweep" "$plugin/hooks/pre-bash-guard.sh" \
  "$(jq -nc --arg c "$root" '{tool_name:"Bash",tool_input:{command:"git add -A"},cwd:$c}')"

secret=$(jq -r '.secrets[0]? // empty | strings' "$lock" 2>/dev/null)
if [ -z "$secret" ]; then
  skip "pre-file-guard / secret" "the profile lists no secrets, so there is nothing to refuse"
else
  run_guard "pre-file-guard / secret" "$plugin/hooks/pre-file-guard.sh" \
    "$(jq -nc --arg c "$root" --arg p "$root/${secret#./}" \
        '{tool_name:"Read",tool_input:{file_path:$p},cwd:$c}')"
fi

jq -nc '{role:"assistant",content:"done, nothing to hand back"}' > "$tmp/t.jsonl"
run_guard "subagent-stop-check" "$plugin/hooks/subagent-stop-check.sh" \
  "$(jq -nc --arg c "$root" --arg t "$tmp/t.jsonl" \
      '{cwd:$c,agent_transcript_path:$t,last_assistant_message:"done"}')"

# post-edit-format never blocks by design, so "refused" is the wrong test: it must
# run the formatter and stay silent.
fmt=$(jq -r '.toolchain.format // empty | strings' "$lock" 2>/dev/null)
if [ -z "$fmt" ]; then
  skip "post-edit-format" "no toolchain.format in the lock"
elif ! command -v "${fmt%% *}" >/dev/null 2>&1; then
  bad "post-edit-format" "toolchain.format is '${fmt}' but '${fmt%% *}' is not on PATH -- every edit silently formats nothing"
else
  # A real, deliberately unformatted file, so a formatter that runs leaves a mark.
  printf 'x = [1,2]\n' > "$tmp/probe.py"
  probe=$(jq -nc --arg c "$root" --arg p "$tmp/probe.py" \
            '{tool_name:"Edit",tool_input:{file_path:$p},cwd:$c}')
  out=$(CLAUDE_PROJECT_DIR="$root" bash "$plugin/hooks/post-edit-format.sh" \
          <<<"$probe" 2>&1)
  rc=$?
  if [ "$rc" -ne 0 ] || [ -n "${out//[[:space:]]/}" ]; then
    bad "post-edit-format" "must exit 0 silently; got exit $rc, output: ${out%%$'\n'*}"
  elif [ "$(cat "$tmp/probe.py")" != "x = [1,2]" ]; then
    ok "post-edit-format" "${fmt%% *} ran and reformatted the probe"
  else
    ok "post-edit-format" "exits 0 silently; ${fmt%% *} left the probe unchanged"
  fi
fi

# A guard script left behind by a render from before 2026-10-02, when it was written
# into the project. Nothing invokes it now -- which is exactly the problem: a file
# that looks like an enforcement hook and never runs invites the belief that ownership
# is enforced from here. One `rm` clears it, so it is a FAIL rather than a note.
if [ -f "$root/.claude/hooks/ownership-guard.sh" ]; then
  bad "no leftover guard script" ".claude/hooks/ownership-guard.sh is from a render before plugin 1.1.0 and is never invoked now -- the guard ships with the plugin. Delete it."
else
  ok "no leftover guard script"
fi

# The profile pins the kit version it was rendered against; the plugin has its own. A
# difference is not breakage -- `kit_version` is a profile field, so re-rendering does
# not change it -- but after a release that altered the generated files it means the
# tree is stale. A note, because the remedy is a decision about the profile.
plugin_ver=$(jq -r '.version // empty | strings' "$plugin/.claude-plugin/plugin.json" 2>/dev/null)
kit_ver=$(jq -r '.kit_version // empty | strings' "$lock" 2>/dev/null)
if [ -n "$plugin_ver" ] && [ -n "$kit_ver" ] && [ "$plugin_ver" != "$kit_ver" ]; then
  note "kit version" "profile pins ${kit_ver}, installed plugin is ${plugin_ver} -- generated files may predate the plugin. Re-render, and set kit_version in .claude/kit.yaml if you did not mean to pin it."
elif [ -n "$kit_ver" ]; then
  ok "kit version" "$kit_ver"
fi

# --- the per-role ownership guard ------------------------------------------
# A plugin hook since 2026-10-02, reading the role from the payload's `agent_type`
# rather than from $1 in a role card's frontmatter registration. So there is no
# per-project script to find, and nothing to be registered: what has to be checked is
# that the guard refuses a cross-role edit, and that no card still carries a stale
# frontmatter block pointing at the script the old design rendered.
guard="$plugin/hooks/ownership-guard.sh"
mapfile -t roles < <(jq -r '.roles[]?.name | strings' "$lock" 2>/dev/null)
if [ "${#roles[@]}" -lt 2 ]; then
  skip "ownership-guard" "fewer than two roles, so no cross-boundary edit exists"
else
  # The first path the SECOND role owns, edited by the FIRST role: a refusal by
  # construction, whatever the roster is.
  victim=$(jq -r --arg r "${roles[1]}" \
    '.roles[] | select(.name==$r) | .owns[0]? // empty | strings' "$lock" 2>/dev/null)
  victim="${victim%%\**}"; victim="${victim%/}"
  if [ -z "$victim" ]; then
    skip "ownership-guard" "${roles[1]} owns no path to test against"
  else
    run_guard "ownership-guard / cross-role" "$guard" \
      "$(jq -nc --arg c "$root" --arg p "$root/${victim#./}/probe.txt" --arg a "${roles[0]}" \
          '{tool_name:"Edit",tool_input:{file_path:$p},cwd:$c,agent_id:"d0",agent_type:$a}')"
  fi
  # The main thread must NOT be guarded: the Orchestrator owns no paths and writes the
  # dispatch state, the register and the gate bundles. A payload with no `agent_type`
  # standing in for it.
  if [ -f "$guard" ]; then
    out=$(CLAUDE_PROJECT_DIR="$root" bash "$guard" 2>&1 <<<"$(jq -nc --arg c "$root" \
            --arg p "$root/${victim:-src}/probe.txt" \
            '{tool_name:"Edit",tool_input:{file_path:$p},cwd:$c}')")
    if [ $? -eq 0 ]; then
      ok "orchestrator is unguarded" "a payload with no agent_type is allowed"
    else
      bad "orchestrator is unguarded" "the main thread was refused; it writes the plan and the register"
    fi
  fi
  # A card from an older render would point at a script no render writes any more, and a
  # hook whose script is missing exits non-2 — which Claude Code reads as "continue".
  stale=""
  for r in "${roles[@]}"; do
    card="$root/.claude/agents/$r.md"
    [ -f "$card" ] || { stale="$stale $r(no card)"; continue; }
    grep -q 'ownership-guard' "$card" && stale="$stale $r"
  done
  if [ -n "$stale" ]; then
    bad "role cards are current" "these still register the guard in frontmatter, which the plugin now does:$stale -- re-render"
  else
    ok "role cards are current" "none registers a frontmatter hook"
  fi
fi

# --- the autonomous pause -------------------------------------------------
# The gate is only as live as the status-line probe that feeds it: `rate_limits` reaches
# user code in exactly one payload and no hook carries it. An unwired probe means the
# pause never fires, and that is indistinguishable from a healthy kit without this check.
snap="${CLAUDE_KIT_USAGE_FILE:-${HOME:-/nonexistent}/.claude/kit-usage.json}"
if [ ! -f "$snap" ]; then
  # Two very different causes look identical from here, so name which one it is: an API
  # key reports no rate limits at all and there is nothing to pause for, while a broken
  # status-line wiring means the pause is disarmed and nothing else would say so.
  if [ -x "${HOME:-/nonexistent}/.claude/kit-usage-probe.sh" ]; then
    note "usage pause" "the shim at ~/.claude/kit-usage-probe.sh exists but no reading has arrived at ${snap}. Either this account has no subscription rate limits (an API key reports none, and there is nothing to pause for), or the shim is not called from your status line yet — see the README."
  else
    note "usage pause" "not wired: ~/.claude/kit-usage-probe.sh does not exist, so no reading can arrive and the pause cannot fire. The README has the one-time shim. Skip it deliberately if this account uses an API key."
  fi
else
  age=$(( $(date +%s) - $(jq -r '.read_at // 0' "$snap" 2>/dev/null || echo 0) ))
  stale=$(jq -r '.usage.stale_after_s // 900' "$lock" 2>/dev/null)
  windows=$(jq -r '[ (if .five_hour then "5h \(.five_hour.used_percentage | floor)%" else empty end), (if .seven_day then "7d \(.seven_day.used_percentage | floor)%" else empty end) ] | join(" ")' "$snap" 2>/dev/null)
  if [ "$age" -gt "${stale:-900}" ]; then
    note "usage pause" "last reading is ${age}s old, past usage.stale_after_s=${stale}. The gate ignores a stale reading and fails OPEN, so the pause will not fire until the status line runs again."
  else
    ok "usage pause" "armed; last reading ${age}s ago (${windows:-no windows in force})"
  fi
fi

# --- what no script can test from here ------------------------------------
echo
cat <<'NOTE'
Not checkable from a script, and all three are real:

  * Bash. Every guard above matches file paths or command strings. A role can
    still reach another role's tree through an interpreter, and no hook here sees
    that. These are nudges with good messages, not a sandbox.

  * --safe-mode disables installed plugins, so in that mode none of this runs.
    Nothing half-applies, which is the one thing to be glad of about it.

  * Workspace trust no longer hides the ownership guard -- it became a plugin hook
    on 2026-10-02 and fires in an untrusted checkout and in `-p` sessions. What
    trust still costs is permissions.allow: the deny rules are kept, so secrets
    stay blocked, while every allowed toolchain command starts prompting. Accept
    the trust dialog once, or set
    projects["<this path>"].hasTrustDialogAccepted: true in ~/.claude.json.
NOTE

echo
if [ "$fails" -eq 0 ]; then
  echo "kit-doctor: all checks passed."
else
  echo "kit-doctor: $fails check(s) FAILED -- the guards above are not protecting this project."
fi
exit $(( fails > 0 ))
