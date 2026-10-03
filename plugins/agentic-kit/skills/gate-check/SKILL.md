---
name: gate-check
description: Run a formal gate check for a milestone and write its evidence under docs/gates/<id>/.
disable-model-invocation: true
argument-hint: <milestone id, e.g. M1>
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.
Take the spine paths, `floors`, `test_tiers` and the veto role (the entry in `roles[]` with
`veto: true`) from the lock. Only the Orchestrator runs this.

Gate: $ARGUMENTS. If no milestone id was given, decline in one line and ask for one.

**Two files, not five.** `docs/gates/$ARGUMENTS/floors.md` is written by the veto role itself;
`docs/gates/$ARGUMENTS/summary.md` holds everything else as sections and is written by you. The five
dimensions are unchanged — they are what stops "the tests pass, ship it" — but four of them arrive as
handoff notes you must paste as evidence anyway, so they belong in one reviewable file. Floors keeps
its own: it can BLOCK, and a verdict the veto role writes itself cannot be softened in synthesis.

1. Create `docs/gates/$ARGUMENTS/`. Write `summary.md` with the headings `## Functional`,
   `## Tests`, `## Operational`, `## Milestone additions` and `## Verdict`, plus a `## Floors` section
   that states the verdict from `floors.md` and links to it. Do not restate the floors argument: it is
   not yours to summarise.
2. **Functional** — for every task of this milestone in `spine.strategy` §11, cite the handoff note
   and its acceptance evidence. Any miss is a BLOCK, not a note.
3. **Tests** — dispatch the `qa` role: coverage per tier against `test_tiers`, the pipeline result
   read **by job name** (when `forge.kind` is not `none`, through `forge.cli`), snapshot diffs. A
   `skipped` job behind a failed one is not a pass; it is a claim going stale, and it must be
   reported as such. Paste the command and its output, as everywhere else.
4. **Floors** — dispatch the veto role in review mode to write `floors.md` itself, ending with a
   verdict line, APPROVE or VETO, and the threat-model delta. A VETO is not overridable here, and you
   do not edit that file.
5. **Operational** — metrics and logs for anything new, runbook entries, rollback path, and backup
   coverage if the data model changed.
6. Apply the milestone's own gate additions from `spine.strategy` §11.
7. `## Verdict`: PASS, CONDITIONAL, or BLOCK. Every condition carries an owner and a deadline task
   ID. Signers: Orchestrator, the veto role, and `architect` if a contract changed.
8. **Count the carried conditions.** If a condition has now survived two milestones, say so to the
   user in the summary and in your reply. A condition nobody tallies stops being one.
9. In `spine.plan`, replace the `## Open gates` placeholder with an entry for this gate pointing at
   `docs/gates/$ARGUMENTS/summary.md` and its verdict. On PASS, advance `spine.plan` and expand the
   next milestone's tasks in `spine.strategy` §11.
10. **On PASS, archive this milestone's Completed rows.** Move them out of `spine.plan` into
    `<plan directory>/archive/$ARGUMENTS.md`, and leave one line in `## Completed` naming the
    milestone, the task count and the archive file. `spine.plan` is read **in full** at the start of
    every session, so every row that stays is a cost paid on every prompt for work that is finished.
    Do not archive the row of a task whose gate has not passed, and do not archive `## Active`,
    `## Blocked` or `## Open gates` — those are current state, not history.

The bundle is an artefact: counts, codes, dates and hashes. No credential, host, token or personal
string reaches it.
