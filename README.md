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

If you would rather write the profile by hand, start from
**`plugins/agentic-kit/examples/kit.yaml`** — a commented worked example, kept valid by a test that
loads and renders it. The schema is §5 of the design document, the three fixtures under
`plugins/agentic-kit/kitgen/tests/fixtures/*/profile.yaml` are further examples, and `model.py` rejects
every malformed profile with a message naming the field.

**If your project gitignores `.claude/` and `CLAUDE.md`** — a reasonable choice, and one of the
repositories this kit was built against does exactly that — then nothing the kit renders is committed.
Every worktree needs its own render, another machine gets none of it, and `memory: project` is
per-checkout rather than shared. `/kit-doctor` detects it and says so; there is nothing to fix if that
is what you want.

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

`/kit-upgrade` does this for you in three steps that report before they change anything: inspect
(orphans, living documents missing sections the templates now render, a role with no design section),
re-render, verify.

### Moving a kit to another checkout, and the state that will not survive it

`.claude/` is gitignored in many projects. Where it is, two things live there that exist **nowhere
else**:

- `.claude/kit.yaml` — the profile. The roster and the ownership map: the one part of an install a
  tool cannot reconstruct, because it was your decision.
- `.claude/agent-memory/**` — what each role has learned. On a real milestone this is the most
  valuable thing in the directory, and the roles write files there you never asked for.

**`git worktree remove` deletes both without a word**, and so does deleting the directory. That is
not a bug in git; it is what untracked means. Archive before you move:

```bash
tar czf ~/kit-state-$(date +%Y%m%d).tar.gz .claude      # verify it before you trust it:
tar xzf ~/kit-state-*.tar.gz -C /tmp/verify && diff -r /tmp/verify/.claude .claude
```

Then, in the destination checkout:

```bash
tar xzf ~/kit-state-*.tar.gz -C . .claude/kit.yaml .claude/agent-memory
uv run --project <kitgen> kitgen render --profile .claude/kit.yaml --out . --force --merge
```

`--force` is required and safe here: the render **keeps** every document the project has written and
every role memory, naming them on stderr (`keeping 15 existing file(s) the project owns`), and
rewrites only the role cards, the lock and the manifest. Without `--force` it exits 3 and writes
nothing, because those files already exist — read that refusal as confirmation, not an obstacle.

**Order matters when the spine is tracked but `.claude/` is not.** The spine documents under `docs/`
are ordinary tracked files; the kit's own config is not. So commit the spine in the source checkout
*first*. Render into the destination before merging, and the scaffolding it writes becomes untracked
files at the same paths the merge then wants — the merge aborts with *"untracked working tree files
would be overwritten"*. Commit, merge, then render.

### The ownership map, and what must stay unowned

The roster and its path ownership map are the one thing `/kit-init` cannot decide for you, and the
rules below are checked before the profile is accepted, so it is worth knowing them before you are
asked.

- **No two roles' globs may overlap**, and overlap is decided on **literal directory prefixes**. So
  `app/**/*.py` for one role against `app/**/*.tsx` for another is **rejected**: extension-partitioned
  ownership of a single tree is refused by design, because the guard would then depend on a filename
  to say who may touch a directory. Split by directory, or share it unowned.
- **Eight roles is the cap.** Each one costs a boundary and a handoff. Beyond that, fold into the
  nearest of architect / backend / frontend / data / devops.
- **Never give one role all of `tests/**`.** The kit mandates test-first, so a role that cannot write
  a test cannot do its job. Give `qa` the integration and e2e subtrees, the veto role its floor tier,
  and leave **`tests/unit/**` unowned**.
- **`docs/gates/**` and the contracts file stay unowned.** A gate bundle is written by two roles at
  once; a contract is written by whoever implements it first.

Unowned is legal and deliberate — it is what keeps the guard usable. An unowned path crosses nobody's
boundary and every role may write it.

`kitgen verify` adds **advice** about unowned code: the shallowest directory holding source that no
role owns, because that is where a floor nobody is accountable for tends to live. It is advice, never
an error, and never changes the exit code. It does **not** report `tests/unit` or anything inside one,
since leaving that unowned is what the installer told you to do — a tool advising you to undo another
tool's instruction is worse than silence.

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
| `/kit-upgrade` | bring an installed kit up to the current plugin: inspect, re-render, verify |

## Usage limits: what Claude Code already does, and what the kit adds

**Read this before configuring anything.** When a usage limit stops Claude mid-task, Claude Code waits
in the open session and continues the task itself after the reset — on by default for an interactive
claude.ai session, v2.1.234 or later. That is genuinely unattended and the kit should not, and does not,
try to replace it.

It has one gap, and the kit covers exactly that gap:

| Window | Who handles it | Why |
|---|---|---|
| **5-hour** | **Claude Code.** The kit ships `five_hour_pct: 0` — never pause. | Hitting the limit arms the wait-and-continue. Pausing *before* the limit means it never arms, so a preemptive stop here buys clean task boundaries and **costs you the automatic resume**. |
| **7-day** | **The kit**, at 95%. | Claude Code does not start that wait on its own for a reset more than 24 hours away, and a weekly limit can reset days out. Being interrupted mid-task there leaves a role's work half-done with nothing to resume it. |

```yaml
usage:
  five_hour_pct: 0       # 0 = never pause; let Claude Code's own wait handle it
  seven_day_pct: 95      # pause here, because nothing auto-resumes a multi-day wait
  stale_after_s: 900     # ignore a usage reading older than this
```

Set `five_hour_pct` to 90 if you would rather have clean task boundaries than an unattended resume.
That is a real preference, not a mistake.

### What the kit's pause does

The `usage-gate` hook refuses **new dispatches only**, so a task already running can ride into the limit
and be continued automatically, while no *new* task is started that cannot be finished. The
Orchestrator keeps the file tools, because the thing it must do next is record where the work stopped.
Its message carries the protocol: write the plan entry first (that is the durable half), then — for a
reset beyond 24 hours — tell you that nothing will resume it by itself, and that `/rate-limit-options`
can arm a wait that does count down past 24 hours while the session stays open.

### Wiring, because of where the data lives

`rate_limits` reaches user code in exactly one payload — the status line's — and no hook event carries
it. So the status line is the sensor. Create this shim **once**; it resolves the installed plugin at run
time, so it survives upgrades, which a path into the versioned cache does not:

```bash
cat > ~/.claude/kit-usage-probe.sh <<'SHIM'
#!/usr/bin/env bash
# Stable entry point for agentic-kit's status-line usage probe.
# Resolves the newest installed copy at run time; silent if none is installed.
set -uo pipefail
newest=""
for d in "$HOME"/.claude/plugins/cache/agentic-kit/agentic-kit/*/bin/kit-usage-probe.sh; do
  [ -f "$d" ] || continue
  [ -z "$newest" ] || [ "$d" -nt "$newest" ] || continue
  newest="$d"
done
[ -n "$newest" ] || exit 0
exec bash "$newest" "$@"
SHIM
chmod +x ~/.claude/kit-usage-probe.sh
```

Newest by **mtime**, not version string: install time is the right meaning of "the one you are using",
and it avoids sorting `1.10.0` against `1.9.0`. Then one line in your status line:

```bash
# after you have read stdin into "$input":
bash "$HOME/.claude/kit-usage-probe.sh" <<<"$input" >/dev/null 2>&1 || true
```

A **herestring, not a pipe.** The probe exits before reading stdin when `jq` is missing, so
`printf ... | bash probe.sh` leaves the writer holding a SIGPIPE, and under a status line's
`set -o pipefail` that pipeline reports 141 — measured, not theorised. The same idiom has cost
this kit two working guards, which is why `test_shell_hygiene` forbids it in every shipped
script; the wiring line should not ask you to do what the kit refuses to do itself.

The redirect and the `|| true` are belt and braces: the probe prints nothing and returns 0 on
every path it is meant to take, and a sensor still should not be *able* to disturb the line it
rides on. `--print` gives a `5h 23% 7d 41%` segment if you want one.

**Nothing to configure for an API key.** `rate_limits` appears only for claude.ai Pro and Max, so its
absence *is* the API-key case: no snapshot, no pause, no detection needed.

### Two prerequisites for unattended operation, both checked by `/kit-doctor`

- **Accept the trust dialog in the project.** An untrusted workspace has every `permissions.allow` entry
  ignored, so a continued turn after a reset stalls on the first command it needs. The deny rules and
  all the hooks work either way — what trust buys is the ability to keep going without you.
- **Leave `autoContinueAtUsageLimit` alone.** It is on by default; turning it off removes the mechanism
  the 5-hour window relies on, and the kit deliberately leaves that window unguarded.

`/kit-doctor` reports whether the pause is **armed**, how old the last reading is, whether the workspace
is trusted, and whether auto-continue has been turned off.

**One honest limit.** A reading older than `stale_after_s` is **ignored**: the status line is not invoked
when a session is not rendering, and pausing on an hour-old number would stop work that could have
continued. This reduces overrun; it does not guarantee against it.

## What the guards do, and what they do not

`pre-bash-guard` blocks staging sweeps, destructive git, the non-chosen forge CLI, outward-facing
forge write verbs, and commands naming a secret path. `pre-file-guard` blocks reading or editing a
secret. `post-edit-format` runs the project formatter on the edited file. `subagent-stop-check`
blocks a subagent that finishes without a handoff note. `ownership-guard` enforces path ownership,
reading the role from the hook payload's `agent_type` — so it refuses a cross-role edit and allows
the main thread, which has no `agent_type` and *is* the Orchestrator.

All of them are **plugin** hooks. That matters for two things people get wrong:

- **Workspace trust does not disable them.** Plugin hooks fire in an untrusted checkout and in `-p`
  sessions. What trust costs is `permissions.allow`, which an untrusted workspace ignores entirely
  while keeping `permissions.deny` — so your secrets stay blocked and every toolchain command starts
  prompting. `/kit-doctor` reports trust for exactly that reason: it is the difference between a
  session that can continue unattended and one that stalls on its first command.
- **Nothing per-role is rendered into the project.** Up to plugin 1.1.0 the guard was a script at
  `.claude/hooks/ownership-guard.sh` registered from each role card's frontmatter. It is not, any
  more. If you find that file in a project it is dead, it is never invoked, and `/kit-doctor` and
  `/kit-upgrade` both flag it — a file that looks like an enforcement hook and runs never is worse
  than no file.

They match **file paths and command strings**, so none of them is a sandbox: an interpreter reaches
past all of them. Design §6.2 is explicit about every limit; read it before relying on any of this as
a boundary. These are nudges with good messages for a cooperative agent, not containment.

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
shellcheck -x -S warning $(find ../../../plugins -name '*.sh')   # every shipped script
```

`.gitlab-ci.yml` runs all of that except `claude plugin validate`, which needs the Claude Code CLI;
CI checks the manifests structurally instead and says so in a comment. Both homelab runners are
`run_untagged: false`, so every job carries `tags: [homelab, docker]` — an untagged job there queues
for ever rather than failing.

`jq` and `shellcheck` are installed from apt in CI, not pip, and the pipeline asserts `jq` is on
`/usr/bin`. The hook tests hand their subprocesses `PATH=/usr/bin:/bin` and nothing else — that is
the point of them, since it proves a guard works in a stripped environment — so a tool in
`/usr/local/bin` is invisible to them, and a hook that cannot find `jq` exits 0 in silence. The
refusal tests would fail with no indication why.

`kitgen.render` is a pure function from a profile to `{path: content}`. It reads nothing from the
project tree, writes nothing, and never reads the clock — `rendered_on` is a profile field for that
reason. That purity is what makes the output testable and what would keep a future MCP wrapper small.

Design: `docs/2026-09-30-agentic-kit-design.md`. Build plan:
`docs/superpowers/plans/2026-09-30-agentic-kit-m1.md`. Post-build audit and its fixes:
`docs/2026-10-01-m1-audit-and-fix-plan.md`.
