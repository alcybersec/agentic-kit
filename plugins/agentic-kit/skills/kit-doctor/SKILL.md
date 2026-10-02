---
name: kit-doctor
description: Check that this project's kit guards are actually firing — runs each hook against a payload it must refuse and reports which ones did.
---

Read `.claude/kit.lock.json` in the project root (`$CLAUDE_PROJECT_DIR`, else the working directory) before anything else. If it is absent or is not valid JSON, decline in one line — "Not a kit project: no readable `.claude/kit.lock.json`" — and stop: do not scaffold, do not guess paths, do not continue from memory.

Run the script and report its output:

```
bash "${CLAUDE_PLUGIN_ROOT}/bin/kit-doctor.sh"
```

It exits 0 when every check passed or was skipped for a stated reason, and 1 otherwise. Do not
paraphrase the table — show it, then act on the failures.

**Why this is not redundant with "the hooks are installed".** Every hook in this kit exits 0 when it
cannot do its job: no `jq`, no lock, an unparseable lock, a renamed or deleted script. That is
deliberate — the plugin is installed machine-wide and most repositories are not kit projects — and it
means a **disarmed** guard and a **correctly inert** one look identical from outside. The script tells
them apart the only way available: it fires each guard with a payload that must be refused and checks
that it was.

**What each failure means.**

| Failure | What it means | What to do |
|---|---|---|
| `jq on PATH: absent` | every hook in the kit is inert, silently | install `jq`; nothing else is enforced until then |
| `kit.lock.json: absent` | the kit is not installed here | run the installer, or re-render from `.claude/kit.yaml` |
| `kit.lock.json: not a JSON object` | same as absent, but looks installed | re-render; do not hand-edit the lock |
| `lock is current: kit.yaml is newer` | someone edited the profile and never re-rendered, so hooks are enforcing the old one | re-render, then re-run this check |
| `ALLOWED a payload that must be refused` | that guard is not protecting the project | compare the script against the plugin's copy; re-render to restore it |
| `refused with no message` | it blocks but tells the agent nothing, so the agent cannot comply | the deny path lost its reason; re-render |
| `exit N (neither allow nor block)` | the script is erroring out, which Claude Code reads as "continue" | run it by hand and read the error |
| `still register the guard in frontmatter` | the card is from a render before 2026-10-02 and points at a script nothing writes any more; a hook with a missing script exits non-2, which Claude Code reads as "continue" | re-render |
| `the main thread was refused` | the guard is blocking the Orchestrator, which must write the plan, the register and the gate bundles | a payload with no `agent_type` must exit 0; report it, do not work around it |
| `toolchain.format is '<x>' but '<x>' is not on PATH` | every edit silently formats nothing | install it, or correct `toolchain.format` and re-render |

**What the script cannot check, and it says so in its own output.** Every guard here matches file
paths or command strings, so an interpreter reaches past all of them, and `--safe-mode` disables
installed plugins entirely. Workspace trust is no longer on this list: the ownership guard became a
plugin hook on 2026-10-02 and fires in an untrusted checkout and in `-p` sessions, both verified. What
trust still costs you is `permissions.allow` — the denies are kept, so secrets stay blocked while every
allowed toolchain command starts prompting. Report these when the output shows them; they are the
honest limits of the enforcement, not a caveat to bury.

Finish with one line: `kit-doctor: N checks, M failed` and, if `M > 0`, the single most important
remedy from the table.
