---
name: new-adr
description: Scaffold a numbered ADR and add it to the decisions index. Orchestrator or architect only.
argument-hint: <kebab-case title>
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.

**Who may run this:** the Orchestrator, or the `architect` role. `architect` owns `docs/adr/**`;
every other role is blocked from writing there, including the veto role, so a role that needs an ADR
(for example to weaken a floor) asks the Orchestrator or `architect` to author it. If you are any
other role, decline in one line, name that route, and stop.

1. Find the highest `docs/adr/NNNN-*.md` and take the next number, zero-padded to four.
2. Write `docs/adr/<NNNN>-$ARGUMENTS.md` (get today's date from `date +%F`):

```markdown
# ADR <NNNN> — <Title>

**Status** Proposed · **Date** <today>

## Context
What forces this decision. Include the constraint that makes the obvious answer wrong.

## Decision
What we are doing, in the active voice.

## Consequences
What this costs, what it forecloses, and what has to change if we reverse it.

## Alternatives considered
Each with the reason it lost. An alternative with no stated reason was not considered.
```

3. Append a row to the `## ADR index` table in `spine.decisions`, matching its columns:
   `| [<NNNN>](adr/<NNNN>-$ARGUMENTS.md) | <Title> | Proposed |` (link relative to that file).
4. Status stays **Proposed** until the user accepts it. Do not write Accepted on your own.
