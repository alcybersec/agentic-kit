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

```
/kit-init
```

That is the whole of it. The skill detects what can be detected — name, toolchain, forge and CI file
from the git remote, secrets from `.gitignore`, authoritative documents already in `docs/`, the
directory shape — then asks you, in at most two turns, for the two things it cannot know: **the role
roster with its path ownership map**, and **the floors** the veto role may block on. It writes
`.claude/kit.yaml`, dry-runs the render, renders, and finishes with `/kit-doctor`.

It stops if `.claude/kit.lock.json` already exists. Reinstalling over a live kit would re-interview you
and re-render a project that has accumulated work.

**On a project that already has a `CLAUDE.md` or a `.claude/settings.json`**, the render is run with
`--merge`, and nothing of yours is lost:

- `CLAUDE.md` keeps its content verbatim under `## Project-specific notes`, below the generated
  scaffolding, and a later re-merge refreshes the scaffolding without duplicating the notes.
- `.claude/settings.json` has its permission lists **unioned** — never replaced — so the result is
  never less restrictive than what you had. Keys the kit does not write are left alone. A
  `settings.json` that is not valid JSON is reported and left untouched rather than replaced.

Without `--merge` a render into such a project refuses with exit 3 and writes nothing, which is the
safe failure but a dead end; `/kit-init` passes it for you.

If you would rather write the profile by hand, the schema is §5 of the design document, the three
fixtures under `plugins/agentic-kit/kitgen/tests/fixtures/*/profile.yaml` are worked examples, and
`model.py` rejects every malformed profile with a message naming the field.

Exit codes are an interface (design §7.1b): `0` written, `1` verification failed and **nothing** was
written, `2` bad profile, `3` refused to overwrite and **nothing** was written, `4` the write failed
partway and the tree is incomplete.

### Re-rendering an installed kit

After editing `.claude/kit.yaml` — to add a role, change the ownership map, or adopt a new plugin
version:

```bash
uv run --project ~/Documents/coding/agentic-kit/plugins/agentic-kit/kitgen \
  kitgen render --profile .claude/kit.yaml --out . --dry-run --force --merge
```

Read the `overwrite`, `frozen` and `blocked` lists, then run it again without `--dry-run`. The same
command is in the *Kit* section of every generated `CLAUDE.md`, with `${CLAUDE_PLUGIN_ROOT}` in place
of the path.

`--force` replaces generated scaffolding and **keeps** what the project has written: `strategy.md`,
`design.md`, `decisions.md`, `CONTRACTS.md`, `risk-register.md`, `plan/README.md`, the adoption ADR
and every role's `MEMORY.md`. It lists both sets on stderr before writing.

It replaces the role cards and the lock, and — **unless you pass `--merge`** — `CLAUDE.md` and
`.claude/settings.json` too, since a profile change has to reach them. Pass `--merge` on any project
whose `CLAUDE.md` or `settings.json` you care about; `/kit-init` does.

Still M2: `/kit-upgrade`, which would diff a new plugin version's templates against the tree and offer
the stable-scaffolding changes as a patch (design §7.1a).

### Which model each role runs on

`roles[].model` in the profile, defaulting to `inherit`. What the fixtures ship, and what `/kit-init`
proposes:

| | Model | Why |
|---|---|---|
| Orchestrator | `inherit` | it is not dispatched — it *is* your session |
| `architect`, veto role | `opus` | judgement, and the veto role's misses are silent: an untested floor reads exactly like one that holds |
| implementing and wiring roles | `sonnet` | contract-first means they are dispatched against a recorded contract and stated acceptance criteria |

An Orchestrator on `opus` with implementers on `sonnet` is the normal shape, and a milestone is dozens
of dispatches, so this is the largest single cost lever here. `inherit` everywhere is the conservative
choice.

Nothing ships on `haiku`: the handoff protocol runs on honesty about test evidence, and a guard refusal
has to be read and routed rather than retried. Neither has been tested on a smaller model, so the kit
does not guess — it stays available for any non-veto role, and **the profile refuses it for the veto
role outright**.

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
| `/kit-init` | install the kit into a project (declines where one exists) |

## Pausing before a subscription limit runs out

The kit can stop dispatching work when the account's rate-limit window is nearly spent, and resume
itself when the window resets. Two thresholds, in the profile, defaulting to:

```yaml
usage:
  five_hour_pct: 90      # pause at 90% of the 5-hour window
  seven_day_pct: 95      # and 95% of the 7-day one
  stale_after_s: 900     # ignore a usage reading older than this
```

**It needs one line of wiring, because of where the data lives.** `rate_limits` reaches user code in
exactly one payload — the status line's — and no hook event carries it. So the status line is the
sensor:

```bash
# in your status line script, after you have read stdin into "$input":
printf '%s' "$input" | bash "$HOME/.claude/plugins/cache/agentic-kit/agentic-kit/<version>/bin/kit-usage-probe.sh"
```

The probe prints nothing, so it cannot disturb your layout; pass `--print` if you want a `5h 23% 7d 41%`
segment. It writes `~/.claude/kit-usage.json`, per account rather than per project, since a rate limit
is not a property of a repository. `/kit-doctor` reports whether the pause is **armed** and how old the
last reading is.

**Nothing to configure for an API key.** `rate_limits` appears only for claude.ai Pro and Max, so its
absence *is* the API-key case: no snapshot, no pause, no detection needed.

**What happens at the threshold.** The `usage-gate` hook refuses new dispatches — and only dispatches,
so the Orchestrator can still write down where the work stopped. Its message carries the protocol: park
the in-flight task in the plan first (durable), then schedule a one-shot `/next-task` for just after the
window's reset, then say so in one line. `/next-task` checks before dispatching, so the ordinary case is
a clean stop rather than a refusal.

**Two honest limits.** A scheduled task lives only in the session that created it, so the plan entry is
what carries the work across a session that ends — and `SessionStart` reports the in-flight task, so the
next session picks it up. And a reading older than `stale_after_s` is **ignored**: the status line stops
being invoked when a session is not rendering, and pausing on an hour-old number would stop work that
could have continued. This reduces overrun; it does not guarantee against it.

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
