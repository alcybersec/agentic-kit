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
tmp=$(mktemp -d) || { echo "kit-doctor: cannot create a temporary directory"; exit 1; }
trap 'rm -rf "$tmp"' EXIT

say()  { printf '%-34s %-7s %s\n' "$1" "$2" "${3:-}"; }
bad()  { fails=$((fails + 1)); say "$1" "FAIL" "$2"; }
ok()   { say "$1" "ok" "${2:-}"; }
skip() { say "$1" "skip" "$2"; }

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
  out=$(printf '%s' "$payload" | CLAUDE_PROJECT_DIR="$root" bash "$script" "$@" 2>&1)
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
  out=$(jq -nc --arg c "$root" --arg p "$tmp/probe.py" \
          '{tool_name:"Edit",tool_input:{file_path:$p},cwd:$c}' \
        | CLAUDE_PROJECT_DIR="$root" bash "$plugin/hooks/post-edit-format.sh" 2>&1)
  rc=$?
  if [ "$rc" -ne 0 ] || [ -n "${out//[[:space:]]/}" ]; then
    bad "post-edit-format" "must exit 0 silently; got exit $rc, output: ${out%%$'\n'*}"
  elif [ "$(cat "$tmp/probe.py")" != "x = [1,2]" ]; then
    ok "post-edit-format" "${fmt%% *} ran and reformatted the probe"
  else
    ok "post-edit-format" "exits 0 silently; ${fmt%% *} left the probe unchanged"
  fi
fi

# --- the rendered per-role ownership guard ---------------------------------
guard="$root/.claude/hooks/ownership-guard.sh"
mapfile -t roles < <(jq -r '.roles[]?.name | strings' "$lock" 2>/dev/null)
if [ ! -f "$guard" ]; then
  bad "ownership-guard present" "absent: $guard"
elif [ ! -x "$guard" ]; then
  bad "ownership-guard executable" "present but not +x, so it cannot run"
elif [ "${#roles[@]}" -lt 2 ]; then
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
      "$(jq -nc --arg c "$root" --arg p "$root/${victim#./}/probe.txt" \
          '{tool_name:"Edit",tool_input:{file_path:$p},cwd:$c}')" "${roles[0]}"
  fi
  # Registration is the other half: a working script nobody registers never runs.
  missing=""
  for r in "${roles[@]}"; do
    card="$root/.claude/agents/$r.md"
    [ -f "$card" ] || { missing="$missing $r(no card)"; continue; }
    grep -q 'ownership-guard.sh' "$card" || missing="$missing $r"
  done
  if [ -n "$missing" ]; then
    bad "ownership-guard registered" "not referenced by the card for:$missing"
  else
    ok "ownership-guard registered" "in all ${#roles[@]} role cards"
  fi
fi

# --- what no script can test from here ------------------------------------
echo
cat <<'NOTE'
Not checkable from a script, and both are real:

  * Workspace trust. The ownership guard is registered in each role card's
    frontmatter, and Claude Code SKIPS a subagent's frontmatter hooks until the
    folder is trusted -- a `-p` session never counts as trusted. The checks above
    prove the script refuses what it should; they cannot prove Claude Code ran it.
    Accept the trust prompt in this folder, and treat non-interactive runs as
    having no per-role ownership enforcement at all.

  * Bash. Every guard above matches file paths or command strings. A role can
    still reach another role's tree through an interpreter, and no hook here sees
    that. These are nudges with good messages, not a sandbox.
NOTE

echo
if [ "$fails" -eq 0 ]; then
  echo "kit-doctor: all checks passed."
else
  echo "kit-doctor: $fails check(s) FAILED -- the guards above are not protecting this project."
fi
exit $(( fails > 0 ))
