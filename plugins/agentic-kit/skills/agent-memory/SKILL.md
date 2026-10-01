---
name: agent-memory
description: How to keep a role's durable memory — one fact per file with a linked index, so the next session does not rediscover it.
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.

Your memory is `.claude/agent-memory/<your role>/` (your role is the name on your agent card).
`MEMORY.md` is the index; each fact is its own file beside it.

**Write a fact when** something cost you real time to discover and would cost the next session the
same: a tool that reported success while doing nothing, an endpoint quirk, a constraint the code
does not state, a test that passes for the wrong reason.

**Do not write** what the repository already records — structure, git history, or anything in
`CLAUDE.md`. A fact that duplicates the tree is noise that dilutes the index.

Format, one file per fact:

```markdown
# <Title — the finding, not the topic>

<The fact, stated so it can be checked. What was observed, what was expected, what the tell is.>

Related: [[other-fact-slug]]
```

Then one line in `MEMORY.md`, newest last:

```markdown
- [Title](slug.md) — the hook: what is surprising, in a clause.
```

Titles carry the finding: "a guessed URL is not a measurement" beats "URL notes". `[[slug]]` links
use the filename without its extension. Before adding, scan the index for a fact that already
covers it and extend that one instead.
