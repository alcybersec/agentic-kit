---
name: handoff
description: Emit the structured handoff note that ends every task. Subagents run this last; the Orchestrator validates it.
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.
Find your own role (the name on your agent card) in `roles[]` and append its `handoff_extra` lines.

Produce exactly:

```
TASK {ID} — COMPLETE | PARTIAL | BLOCKED
OUTPUTS:
  - <path>
CONTRACTS CHANGED: yes (<name> v<N> in <spine.contracts>) | no
TESTS: red={n} green={n} coverage={tier: %}
FLOORS: unaffected | touched (<which>) — result: <pass|fail>
OBSERVABILITY: <metrics and log fields added> | n/a
DOWNSTREAM: <unblocked task IDs>
NOTES: <deviations, follow-ups, requests to other owners>
```

Then your role's extra lines from `handoff_extra`.

**Contracts.** If `CONTRACTS CHANGED` is `yes`, the entry must already exist in `spine.contracts`
in the shape that file defines — do not invent another. Under `## Current`, one entry per contract:
a `### <name> v<N>` heading, a fenced block holding the shape, and a `Consumers:` line naming the
roles that depend on it. Under `## Change log`, one row: Date, Contract (the `<name>` from the
heading), Version, Change, Task. The `<name> v<N>` in your note must match that heading. If **another
role** owns `spine.contracts` in §2, do not edit it: put the proposed entry in NOTES, ask that role
(via the Orchestrator) to record it, and mark the task PARTIAL until it exists. If **no role** owns
it — the default, because contract-first requires the implementing role to record a contract before
building against it — write it yourself. The ownership guard applies the same rule: it blocks a path
only when another role owns it.

**Evidence over prose.** Paste the test command and its last line. Never write a green you did not
run. If you could not run it, say `TESTS: not run — <why>` and mark the task PARTIAL: an unverified
claim costs more than an honest gap.
