---
name: orchestrating
description: Dispatch doctrine for the Orchestrator role — how to brief a subagent, when worktree isolation is mandatory, and how to validate what comes back.
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.
This is doctrine for the Orchestrator. A role agent that is not dispatching others has no use for it.

## Briefing

Pass the task block verbatim, the role card path, and **file paths, never pasted documents** — a
pasted document is a copy that goes stale and costs context twice.

Every brief repeats the atomic-commit rule: commit with `git commit --only <path>`, explicit paths.
Never `git add -A`, `git add .`, or `git commit -a`.

## Worktree isolation is mandatory when

- Two or more agents are dispatched in the same message.
- A dispatched agent's scope overlaps an in-flight peer's tree.
- An agent will edit files a peer may stage.

Set `isolation: "worktree"` on the Agent call. Agents sharing one working tree share one index, and
a shared index is the whole cause of cross-agent staging leaks. Disjoint file lists do **not** make
a shared tree safe.

On return from a worktree agent: verify the handoff and the commit SHA against acceptance,
cherry-pick onto the trunk, remove the worktree, and record both SHAs in the handoff note.

**Never** recover with `git stash`. Restoring a stash has itself moved a peer's working tree into the
wrong commit. If foreign files appear in `git status`, stop and report.

## Validation

A handoff without a pasted command and its last line is not evidence — run `toolchain.test`
yourself. Accept, or record the gap and re-dispatch once with the gap named; after a second failure,
stop and report to the user rather than trying a third time.
