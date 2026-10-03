---
name: next-task
description: Advance the dispatch loop one step — take the next unblocked task from the plan, dispatch its owning role, validate the handoff, update the plan.
disable-model-invocation: true
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.
Take every path below from the lock rather than assuming one. Only the Orchestrator runs this.

**Before dispatching, check the usage pause.** If `~/.claude/kit-usage.json` exists, is newer than
`usage.stale_after_s` seconds, and shows a window at or over its threshold in `usage` — a threshold of
`0` means that window is deliberately unguarded — do not dispatch. Park instead: record the in-flight
task in `spine.plan` under `## Active` with what is done and what remains, then say in one line that
you paused, which window, and how work resumes. The `usage-gate` hook refuses the dispatch anyway if
you miss this; checking first is the difference between stopping cleanly and being stopped.

Do **not** invent a resume mechanism. For a reset under 24 hours away Claude Code continues an
interrupted task by itself, which is why `five_hour_pct` ships at `0`. For a reset further out it does
not, and the honest answer is the plan entry plus telling the user that `/rate-limit-options` can arm a
wait that counts down past 24 hours while the session stays open.

No such file means there is nothing to check: an API key never reports a rate limit, and a status line
without `bin/kit-usage-probe.sh` wired in reports nothing either.

1. Read `spine.plan`. Confirm the Next task is unblocked — every task it depends on is in Completed.
2. Read its block in `spine.strategy` §11 and the owner's card in `.claude/agents/<owner>.md`.
3. Add a row to the plan's Active table (Task, Owner, Dispatched, Worktree), then spawn the owner with
   the Agent tool (role name as the agent type). Pass the task block verbatim, the design section
   references, and the instruction to end with `/handoff`. **Pass paths, not pasted documents.**
   Include the atomic-commit rule. If you are dispatching more than one agent in this message, or this
   agent's scope overlaps an in-flight peer, set `isolation: "worktree"` (see `orchestrating`).
4. On return, check the handoff against the task's Acceptance. If the note claims tests without
   pasting the command and its result, run `toolchain.test` yourself and cite your own output.
5. If accepted, edit `spine.plan`: move the task from Active to Completed (Task, Owner, Branch,
   Evidence, Completed), advance Next task, unblock downstream. If not, record the gap under Active
   and re-dispatch **once** with the gap named. After a second failure, stop and report to the user.
6. If every task feeding a gate is complete, tell the user the gate is ready and **stop**. Do not
   start `/gate-check` without confirmation.
7. If anything surfaced that outlives this task, run `/risk` for it.
