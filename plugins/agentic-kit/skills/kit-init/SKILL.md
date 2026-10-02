---
name: kit-init
description: Install the kit into this project — detect what can be detected, ask only what cannot, write .claude/kit.yaml, render, and verify. Works on an empty repo or one with years of code.
disable-model-invocation: true
argument-hint: (no arguments)
---

Read `.claude/kit.lock.json` first. **If it exists, stop**: this project already has a kit. Say so in
one line and point at the re-render command in `CLAUDE.md`'s *Kit* section, or `/kit-doctor` if
something seems wrong. Do not reinstall over a live kit.

Only the user runs this. Never dispatch a subagent to do any of it: the whole point is that the user
decides the roster and the ownership map, and a subagent cannot answer for them.

## 1. Detect, and show your evidence

Run these and read them yourself. Do **not** ask the user anything you can answer here.

```bash
ls -a; git remote -v; git log --oneline -5 2>/dev/null | head -5
cat .gitignore 2>/dev/null | head -40
ls docs 2>/dev/null; ls -d .github/workflows .gitlab-ci.yml 2>/dev/null
cat pyproject.toml package.json Cargo.toml go.mod composer.json 2>/dev/null | head -60
git ls-files | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -30
```

From that, fill in as much as you can:

| Field | Where it comes from |
|---|---|
| `project.name`, `slug`, `summary` | the directory, the README's first heading and first sentence, `pyproject`/`package.json` name and description |
| `forge.kind`, `remote`, `ci` | `git remote -v` — a `gitlab` host means `gitlab` and `cli: glab`; `github.com` means `github` and `cli: gh`; **no remote means `kind: none`, `cli: none`, `ci: null`, `remote: null`**. `ci` is the workflow file that exists, not the one you would create |
| `forge.mirror` | a second remote on the *other* forge. Otherwise `null` |
| `toolchain` | the package manager's own config. `pm`/`test`/`format`/`lint`/`types` as the project really runs them — read the scripts table or the dev dependencies, do not invent a stack |
| `secrets` | every secret-shaped line in `.gitignore` (`.env`, `secrets/`, `*.pem`), as `./`-prefixed patterns. `./.env` and `./secrets/**` are the common pair |
| `spine.inherited` | documents that already exist and are authoritative: a PRD, an architecture note, a spec. **Only files that exist**; the renderer verifies them on disk |
| `milestones.outline` | from a roadmap if there is one, else a single `M0 Foundations` |
| the directory table | candidate role boundaries — this is the input to turn 2 below, not an answer |

`toolchain.format` must be a command that takes **one file**: the post-edit hook appends the edited
path. `black`, not `black .` — the profile is rejected otherwise, with that reason.

## 2. Ask, in at most two turns

Use `AskUserQuestion`. Group everything; do not ask one field at a time. Everything you detected is
shown for confirmation, not asked again.

**Turn 1 — the roster and the boundaries.** Propose a roster from the directory table and say which
paths each role would own. Always include `architect`, `devops`, `qa` and a veto role (`safety` by
convention). Add `data` if there are migrations or an ORM, `frontend` if there is a JS/TS app
directory, and one domain role per genuinely separate service tree. **Cap at eight**: each role costs
a boundary and a handoff, and §8.4 folds the rest into the nearest of
architect / backend / frontend / data / devops. Say what you are proposing and why, then let the user
correct it — this is the one decision that matters most and the one you are least able to make alone.

Rules the map must satisfy, so check them before you ask:

- No two roles' globs may overlap. Overlap is decided on literal directory prefixes, so
  `app/**/*.py` against `app/**/*.tsx` is **invalid** — extension-partitioned ownership of one tree
  is rejected by design.
- Do not give one role all of `tests/**`: that blocks every other role from writing a test while the
  kit mandates test-first. Give `qa` the integration and e2e subtrees, the veto role its floor tier,
  and leave `tests/unit/**` unowned.
- Leave unowned anything no role should hold. An unowned path crosses nobody's boundary and is
  writable by all, which is what keeps the guard usable.
- `docs/gates/**` and the contracts file stay unowned. The first is written by two roles at a gate;
  the second is written by whoever implements a contract first.

**Turn 2 — the floors and the rest.** The floors (what must never regress — the one thing the veto
role can block on, so it must come from the user and not from you), the test tier thresholds,
whether observability applies, commit attribution, and any `critical` paths: single files only the
veto role may change, wherever they sit in the ownership map.

## 3. Write the profile

Write `.claude/kit.yaml` yourself, with comments explaining the non-obvious choices — it is the
human-facing source of truth and may carry comments; the lock beside it is what hooks read.

Then **dry-run**, and read the output rather than assuming:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/kitgen" kitgen render \
  --profile .claude/kit.yaml --out . --dry-run
```

Exit 2 means the profile is wrong and the message names the field — fix it and run again. Exit 1 means
the rendered kit is internally inconsistent. Exit 3 lists `clashes`; exit 0 with a non-empty `blocked`
means something is in the way that `--force` will not clear.

## 4. Render, preserving what the project already has

**If `CLAUDE.md` or `.claude/settings.json` exists, you MUST pass `--merge`.** Without it the render
refuses (exit 3) rather than destroying them, which is the safe failure — but `--merge` is the correct
answer, not a workaround:

- `CLAUDE.md` keeps its content under `## Project-specific notes`, below the generated scaffolding.
  §7.2 is normative about this: that text holds findings that cost real time.
- `.claude/settings.json` has its permission lists **unioned**, never replaced, and every key the kit
  does not write is left alone.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/kitgen" kitgen render \
  --profile .claude/kit.yaml --out . --merge
```

Read the `merged …` lines on stderr back to the user: they say exactly what was kept and what was
added. If settings.json could not be parsed the kit says so and leaves it alone — tell the user, and
do not try to repair their file.

## 5. Verify, and say what is still needed

Run `/kit-doctor` and show its table. Then tell the user, in no more than five lines:

1. **Accept the trust dialog in this folder** (or set
   `projects["<path>"].hasTrustDialogAccepted: true` in `~/.claude.json`). Until then Claude Code
   ignores every `permissions.allow` entry, so each toolchain command prompts. The deny rules and the
   hooks work either way.
2. The spine documents are scaffolding with headings and no content yet — §11 of the strategy
   document (`spine.strategy`) is the task graph, and it is expanded at each gate, not now.
3. `/next-task` starts the dispatch loop; `/plan-status` is the read-only view.
4. Anything `/kit-doctor` flagged.
5. That `.claude/kit.yaml` is theirs to edit, and a re-render is the command in `CLAUDE.md`.

Do not start work. Installing the kit and using it are separate acts, and the user may want to read
what you generated first.
