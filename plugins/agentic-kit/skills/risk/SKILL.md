---
name: risk
description: Add or update a row in the project risk register.
argument-hint: <one-line risk statement>
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.

Open `spine.risks`. Take the next unused `R-NNN` — **never reuse a number**, including for a closed
risk, because task notes and gate bundles cite them.

The register is a table with seven columns, in this order: **ID, Risk, Likelihood, Impact,
Mitigation, Owner, Status**. Write exactly seven cells in that order. Read the table's header row
first; if it does not match, stop and report the mismatch rather than guessing a mapping.

- **ID** — `R-NNN`.
- **Risk** — a falsifiable statement.
- **Likelihood**, **Impact** — Low / Med / High.
- **Mitigation** — what is being done, or the trigger for doing it.
- **Owner** — the role accountable for the mitigation.
- **Status** — open, mitigating, or closed (with the evidence that closed it).

Rules:

- A risk closes on **evidence**, not on time passing. Cite what closed it.
- If the risk has already fired, say how many times and when. A recurrence count is the finding.
- If an existing row covers it, update that row instead of adding a near-duplicate.
