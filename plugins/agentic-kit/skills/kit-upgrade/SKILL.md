---
name: kit-upgrade
description: Bring an installed kit up to the current plugin — report what a re-render cannot tell you, then re-render, then verify.
disable-model-invocation: true
argument-hint: (no arguments)
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.

Only the user runs this. Three steps, in this order, and **report before you change anything**.

## 1. Inspect

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/kitgen" kitgen upgrade \
  --profile .claude/kit.yaml --root .
```

It changes nothing. Exit 0 means there is nothing to review; exit 1 means read its lines first. It
reports the three things a re-render cannot:

- **Orphans** — a file an earlier render wrote and this one does not. Relocating a `spine.*` path
  leaves the old document behind, and plugin 1.1.0 left a dead `.claude/hooks/ownership-guard.sh`
  that looked like an enforcement hook and ran never. **Show these to the user and let them decide.**
  Never delete one yourself: the renderer does not remove files on purpose, a renamed document may
  hold the project's work, and you cannot tell from the path which case you have.
- **A living document missing sections the template now renders.** `--force` refuses to touch those
  files by design, so new sections never appear by themselves. Offer to add the headings; leave the
  bodies to whoever owns the content.
- **A role with no section in the design document.** Adding a role is the commonest reason to
  re-render, and the new role would have nowhere to record its design.

## 2. Re-render

Only after the user has seen step 1. `--merge` whenever `CLAUDE.md` or `.claude/settings.json`
exists — which is always, on an installed kit:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/kitgen" kitgen render \
  --profile .claude/kit.yaml --out . --dry-run --force --merge
```

Read the `frozen`, `overwrite` and `blocked` lists back to the user, then run it again without
`--dry-run`. The living documents and every `MEMORY.md` are kept; the role cards, the lock,
`settings.json` and `CLAUDE.md` are rewritten, and `CLAUDE.md` keeps your content under
`## Project-specific notes`.

If `blocked` is not empty, stop and report it: something is in the way that `--force` will not
clear — a file the process cannot write, or a directory where a file belongs. Nothing has been
written in that case.

## 3. Verify

Run `/kit-doctor` and show its table. Then say, in no more than four lines: the version you came
from and went to, what you kept, what you changed, and anything still outstanding — orphans the user
has not yet decided about, headings not yet added, and whatever `/kit-doctor` flagged.

Do not start development work. Upgrading the kit and using it are separate acts.
