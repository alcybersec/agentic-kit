---
name: plan-status
description: Read-only grounding — current milestone, next task, open gates, open risks, and any kit drift.
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.

Read `spine.plan` and `spine.risks`. Report in at most six lines: current milestone, next task ID
and owner, anything Active or Blocked, open gates, and the count of open risks plus any that have
fired more than once.

If `.claude/kit.yaml` is newer than `.claude/kit.lock.json`, add one line: the profile was
hand-edited and the lock is stale — re-render with `/kit-upgrade` (an installer skill that ships
separately; if it is not available, say the lock needs regenerating).

Change nothing. This skill only reads.
