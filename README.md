# agentic-kit

A drop-in Claude Code kit for the orchestrator development model: role agents with exclusive
file-path ownership, milestone gates, a risk register, handoff notes carrying pasted test evidence,
per-role agent memory, and guard hooks that make the rules executable rather than advisory.

**Status: M1.** The kit, the renderer, the verifier and the guards are complete and tested. The
interview-driven installer skills are M2 and **do not exist yet**, so the first `.claude/kit.yaml`
is written by hand today — see *Install into a project* below.

## Install the plugin

```bash
claude plugin marketplace add git@192.168.1.174:alex/agentic-kit.git
claude plugin install agentic-kit@agentic-kit
```

That host is reachable on the LAN and over the tailnet; `gitlab.home.aleksanlab.me` resolves to it
for the web UI and API, while git itself uses the IP. From a machine that cannot reach it, or while
developing the kit itself, point the marketplace at the working copy instead:

```bash
claude plugin marketplace add /home/alex/Documents/coding/agentic-kit
claude plugin install agentic-kit@agentic-kit
```

Once per machine. **The plugin is inert in any repository without `.claude/kit.lock.json`** — every
hook reads that file first and exits 0 when it is absent or unparseable, and every skill declines.
Installing it machine-wide does not change how you work in projects that do not use it.

That inertness has a consequence worth knowing: a *disarmed* guard and a correctly inert one look
identical from outside, because both exit 0. **`/kit-doctor`** is the only thing that tells them
apart — it fires each guard with a payload that must be refused and reports which actually refused it.
Run it after any change under `.claude/` and after updating the plugin.

## Install into a project

The three installer skills (`/kit-install` greenfield, `/kit-retrofit` mid-project, `/kit-upgrade`)
are **M2**. Until they ship, write the profile and render it:

1. Copy a starting profile from `plugins/agentic-kit/kitgen/tests/fixtures/*/profile.yaml` — pick the
   one whose shape matches your repo (`greenfield_prd`, `python_monolith`, `services_layout`) — to
   `.claude/kit.yaml` and edit it. The schema is §5 of the design document, and
   `plugins/agentic-kit/kitgen/src/kitgen/model.py` rejects every malformed profile with a message
   naming the field.
2. Render:

```bash
uv run --project ~/Documents/coding/agentic-kit/plugins/agentic-kit/kitgen \
  kitgen render --profile .claude/kit.yaml --out . --dry-run
```

   Read the manifest, the clashes and anything under `blocked`, then run it again without
   `--dry-run`.

3. `/kit-doctor`, to confirm the guards actually fire in this project.

Exit codes are an interface (design §7.1b): `0` written, `1` verification failed and **nothing** was
written, `2` bad profile, `3` refused to overwrite and **nothing** was written, `4` the write failed
partway and the tree is incomplete.

### Re-rendering an installed kit

`--force` replaces generated scaffolding and **keeps** what the project has written: `strategy.md`,
`design.md`, `decisions.md`, `CONTRACTS.md`, `risk-register.md`, `plan/README.md`, the adoption ADR
and every role's `MEMORY.md`. It lists both sets on stderr before writing.

It **does** replace `CLAUDE.md`, `.claude/settings.json`, the role cards and the lock — a profile
change has to reach them. So back up a hand-curated `CLAUDE.md` first; preserving it is `/kit-retrofit`'s
job (M2, design §7.2).

## Day to day

| Skill | For |
|---|---|
| `/next-task` | advance the dispatch loop one step (Orchestrator only) |
| `/plan-status` | read-only grounding: milestone, next task, open gates, open risks, kit drift |
| `/handoff` | the structured note that ends every task |
| `/gate-check <id>` | the milestone gate: five dimensions, two files, a veto that cannot be overridden |
| `/new-adr <title>` | scaffold an ADR and index it |
| `/risk <statement>` | add or update a row in the register |
| `/agent-memory` | the per-role memory convention |
| `/orchestrating` | dispatch doctrine: worktrees, path-not-paste, atomic commits |
| `/kit-doctor` | prove the guards are firing |

## What the guards do, and what they do not

`pre-bash-guard` blocks staging sweeps, destructive git, the non-chosen forge CLI, outward-facing
forge write verbs, and commands naming a secret path. `pre-file-guard` blocks reading or editing a
secret. `post-edit-format` runs the project formatter on the edited file. `subagent-stop-check`
blocks a subagent that finishes without a handoff note. A rendered per-role guard enforces path
ownership.

They match **file paths and command strings**, so none of them is a sandbox: an interpreter reaches
past all of them, and the per-role guard is *skipped entirely* until the workspace is trusted — a
`-p` session never counts as trusted. Design §6.2 is explicit about every limit; read it before
relying on any of this as a boundary. These are nudges with good messages for a cooperative agent,
not containment.

## Forge neutrality

Nothing assumes GitLab or GitHub. `forge.kind` is a profile field — `gitlab`, `github` or `none` —
and the guard enforces whichever you chose, blocking the other's CLI when `forge.exclusive` is set.
With `none`, no forge rule is rendered at all. Adding a third forge is a template branch plus one
entry in `CLI_FOR_FORGE`.

## Development

```bash
cd plugins/agentic-kit/kitgen
uv run pytest                      # the whole suite, including the shell guards
python ../../../scripts/check_plan_sync.py   # templates still match the plan
claude plugin validate ../..               # manifests
```

`kitgen.render` is a pure function from a profile to `{path: content}`. It reads nothing from the
project tree, writes nothing, and never reads the clock — `rendered_on` is a profile field for that
reason. That purity is what makes the output testable and what would keep a future MCP wrapper small.

Design: `docs/2026-09-30-agentic-kit-design.md`. Build plan:
`docs/superpowers/plans/2026-09-30-agentic-kit-m1.md`. Post-build audit and its fixes:
`docs/2026-10-01-m1-audit-and-fix-plan.md`.
