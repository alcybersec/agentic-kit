---
name: gate-check
description: Run a formal gate check for a milestone and write the evidence bundle under docs/gates/<id>/.
disable-model-invocation: true
argument-hint: <milestone id, e.g. M1>
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.
Take the spine paths, `floors`, `test_tiers` and the veto role (the entry in `roles[]` with
`veto: true`) from the lock. Only the Orchestrator runs this.

Gate: $ARGUMENTS. If no milestone id was given, decline in one line and ask for one.

1. Create `docs/gates/$ARGUMENTS/` with `functional.md`, `tests.md`, `floors.md`,
   `operational.md` and `summary.md`.
2. **Functional** — for every task of this milestone in `spine.strategy` §11, cite the handoff note
   and its acceptance evidence. Any miss is a BLOCK, not a note.
3. **Tests** — dispatch the `qa` role: coverage per tier against `test_tiers`, the pipeline result
   read **by job name** (when `forge.kind` is not `none`, through `forge.cli`), snapshot diffs. A
   `skipped` job behind a failed one is not a pass; it is a claim going stale, and it must be
   reported as such.
4. **Floors** — dispatch the veto role in review mode to write `floors.md` and a verdict, APPROVE or
   VETO. Include the threat-model delta. A VETO is not overridable here.
5. **Operational** — metrics and logs for anything new, runbook entries, rollback path, and backup
   coverage if the data model changed.
6. Apply the milestone's own gate additions from `spine.strategy` §11.
7. `summary.md`: PASS, CONDITIONAL, or BLOCK. Every condition carries an owner and a deadline task
   ID. Signers: Orchestrator, the veto role, and `architect` if a contract changed.
8. **Count the carried conditions.** If a condition has now survived two milestones, say so to the
   user in the summary and in your reply. A condition nobody tallies stops being one.
9. In `spine.plan`, replace the `## Open gates` placeholder with an entry for this gate pointing at
   `docs/gates/$ARGUMENTS/summary.md` and its verdict. On PASS, advance `spine.plan` and expand the
   next milestone's tasks in `spine.strategy` §11.

The bundle is an artefact: counts, codes, dates and hashes. No credential, host, token or personal
string reaches it.
