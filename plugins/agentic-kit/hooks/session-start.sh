#!/usr/bin/env bash
# SessionStart. Prints what a session needs to know about this kit, into context.
#
# Two problems this exists for.
#
# First, §5.1 defines a drift signal — mtime(kit.yaml) > mtime(kit.lock.json) means the
# profile was edited and never re-rendered — and until 2026-10-03 only `/kit-doctor`
# read it. So editing the profile and forgetting to re-render left every hook silently
# enforcing the OLD ownership map and the OLD secrets list, until somebody happened to
# run the doctor. A guarantee that holds only when you remember to check it is the same
# failure the ownership guard had with workspace trust.
#
# Second, the post-build audit found rules that reach no reader: the worktree-isolation
# rule lives in a card that never loads for the Orchestrator, §4 is not in `load_order`,
# and §10 can say a milestone is open while the plan file says "not yet entered". A
# session that states where it is cannot disagree with itself about it.
#
# Plain stdout: Claude Code adds a SessionStart hook's plain-text stdout to context, so
# there is no schema here to get wrong. Silent and exit 0 outside a kit project, like
# every other hook in this plugin.
set -uo pipefail
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init

root="${KIT_LOCK%/.claude/kit.lock.json}"
kit_version=""; plan=""; strategy=""; risks=""; m0=""; nroles=""
kit_read_nul kit_version plan strategy risks m0 nroles < <(jq -j '
  ((.kit_version? // "") | tostring), "\u0000",
  ((.spine.plan? // "") | tostring), "\u0000",
  ((.spine.strategy? // "") | tostring), "\u0000",
  ((.spine.risks? // "") | tostring), "\u0000",
  ((.milestones.outline[0].id? // "") | tostring), "\u0000",
  ((.roles | length) | tostring), "\u0000"' "$KIT_LOCK" 2>/dev/null)

lines=()

# Drift first: everything else is only true if the lock is current.
yaml="$root/.claude/kit.yaml"
if [ -f "$yaml" ] && [ "$yaml" -nt "$KIT_LOCK" ]; then
  lines+=("DRIFT: .claude/kit.yaml is newer than .claude/kit.lock.json. The hooks read the"
          "lock, so your profile edit is NOT in effect — the old ownership map and the old"
          "secrets list are still being enforced. Re-render before relying on either; the"
          "command is in CLAUDE.md's Kit section.")
fi

# A role card from an older render still registers a frontmatter hook pointing at a
# script no render writes any more, and a hook with a missing script fails OPEN.
if [ -f "$root/.claude/hooks/ownership-guard.sh" ]; then
  lines+=("STALE: .claude/hooks/ownership-guard.sh is left over from a render before plugin"
          "1.1.0 and is never invoked. Delete it; the guard ships with the plugin. Run"
          "/kit-doctor for the full picture.")
fi

# Where the project is. Read from the plan rather than asserted, so this cannot disagree
# with the file the Orchestrator actually dispatches from.
if [ -n "$plan" ] && [ -f "$root/${plan#./}" ]; then
  # One awk, no pipe: `… | grep -m1` is the SIGPIPE-under-pipefail trap this kit has
  # already paid for twice, and test_shell_hygiene caught it here the moment I wrote it.
  active=$(awk '/^## Active/{n=4; next}
                n-- > 0 && /^\| *[A-Za-z0-9]+-S[0-9]+-/{print; exit}' \
           "$root/${plan#./}" 2>/dev/null || true)
  if [ -n "$active" ]; then
    lines+=("In flight, per ${plan}: ${active}")
  else
    lines+=("Nothing in flight per ${plan}. /next-task takes the next unblocked task;"
            "/plan-status is the read-only view.")
  fi
fi

if [ -n "$risks" ] && [ -f "$root/${risks#./}" ]; then
  open_risks=$(grep -cE '^\|.*\| *open *\|' "$root/${risks#./}" 2>/dev/null || true)
  [ "${open_risks:-0}" -gt 0 ] && lines+=("Open risks in ${risks}: ${open_risks}.")
fi

[ "${#lines[@]}" -gt 0 ] || exit 0

printf 'agentic-kit %s — %s roles, milestone %s. You are the Orchestrator unless a role\n' \
  "${kit_version:-?}" "${nroles:-?}" "${m0:-?}"
printf 'card is active: plan and dispatch, do not write implementation code yourself.\n'
printf '%s\n' "${lines[@]}"
exit 0
