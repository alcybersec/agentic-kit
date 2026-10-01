# Agentic Kit — Design

**Date** 2026-09-30 · **Status** approved (brainstorm) · **Supersedes** nothing

## 1. Problem

Four Claude Code kits exist across `JobOps`, `companion`, `study-helper-project` (StudyAIO) and
`321_project` (arbitrage). They work, and they have diverged into two families:

| | JobOps / companion | StudyAIO / arbitrage |
|---|---|---|
| Shape | Orchestrator + 9–11 role agents with file-path ownership, gates, risk register, ADRs, handoff notes, task IDs (`M0-S1-DO-001`) | Single-agent CLAUDE.md: conventions, architecture rules, `rules/*.md`, slash commands |
| Docs spine | `docs/plan/README.md`, `strategy.md`, `decisions.md`, `risk-register.md`, `design.md`, `CONTRACTS.md` | `docs/PRD.md`, `PROGRESS.md`, `architecture.md` |
| Process skills | `/next-task`, `/gate-check`, `/handoff`, `/new-adr` | `/implement`, `/plan-next`, `/status`, `/review-code` |
| Agent memory | `.claude/agent-memory/<agent>/MEMORY.md`, linked index, 126 files in JobOps | none |
| Hooks | pre-file-guard, pre-bash-guard, MCP navigate/click guards, subagent-stop-check | none |

Shared DNA in all four: a session-start load order; a docs spine that is the source of truth for
"what is next"; pragmatic TDD with named test tiers; contract-first; non-regressing floors; forge
discipline; observability shipped with the feature; an explicit "what you never do" list;
evidence-over-prose handoffs.

Every improvement to that DNA currently has to be made four times, and in practice is not. The
goal is one kit, droppable into any project at any stage, carrying the DNA — with the
project-specific parts generated rather than copied.

## 2. Goals

- One versioned kit, improved in one place, reaching every project.
- Installable into a **greenfield** project (no code; documentation such as a PRD may already exist)
  and **retrofittable** into a project already mid-flight.
- The orchestrator model always: role agents with path ownership, gates, risk register, handoff
  protocol. Not a tiered lite/full split.
- Portable beyond this homelab: no rule hard-codes GitLab, this user, or these hosts. Everything
  environment-specific is an interview answer.
- Existing hard-won project knowledge is never discarded by a retrofit.

## 3. Non-goals

- No MCP server in this scope. The renderer is designed so one can wrap it later (§6.4), but
  nothing is built or deployed to MetaMCP. Revisit only if a non-Claude-Code caller appears.
- No migration of the four existing projects as a deliverable. Two are retrofitted **in worktrees**
  as the acceptance test for M2; adopting the result on their real branches is a separate decision.
- No attempt to generate a full milestone task graph from a PRD (§7.4).
- No tiered lite mode.

## 4. Architecture

### 4.1 Single entry point: a Claude Code plugin

The kit ships as a plugin, `agentic-kit`, from a marketplace hosted in the same repository. It is
the only mechanism; there is no second channel.

Rationale, having established what each channel can physically carry:

- MCP serves tools, resources and prompts. It **cannot** deliver a skill, a hook or a subagent —
  a `PreToolUse` hook is a local executable, and a skill is a file a session reads from disk. An
  MCP-only design therefore forces skills and hooks to be written into every repository, which is
  the per-project drift the update model rejects.
- A plugin ships commands, agents, skills, hooks, scripts **and** MCP servers. A plugin skill runs
  locally with filesystem access and can carry the renderer as a bundled script, so it is strictly
  more capable than a remote MCP server for this job: no round-trips, no manifest hand-off, and it
  works offline or when the MCP gateway is down.

Cost accepted: two commands once per machine.

**Rejected — MetaMCP-only.** Zero install and callable from any MCP client, but forces the drift
model for skills and hooks.

**Rejected — both channels.** MCP as a zero-install entry point plus the plugin for the local half.
Two mechanisms for one job; the only thing it buys over plugin-only is callability from non-Claude-Code
clients, which is not a current requirement.

### 4.2 The keystone: `.claude/kit.yaml`

Universal skills and hooks can only stay universal if the project describes itself in a
machine-readable file. `kit.yaml` is that file, and it doubles as the kit's presence marker.

### 4.3 Global-plugin inertness rule (normative)

Once installed, the plugin's hooks fire in **every** project on the machine, including repositories
that are not kit projects.

> Every hook and every process skill MUST read `<project>/.claude/kit.lock.json` first, and MUST exit
> 0 (hooks) or decline with a one-line explanation (skills) when it is absent or unparseable.

The project root is `${CLAUDE_PROJECT_DIR}` when set, otherwise the `.cwd` field of the hook's stdin
payload. A missing lock is the normal case, not an error. This is covered by a test (§9.3).

### 4.4 Renderer purity rule (normative)

`kitgen.render` MUST be a pure function `(answers, project_facts) -> dict[path, content]`. It MUST
NOT read the project tree, write files, or call out. Detection and writing live in the skills that
call it. This is what makes the output testable, and what keeps a future MCP wrapper small.

## 5. `kit.yaml` schema (normative)

```yaml
kit_version: 1.0.0                 # the plugin version that last wrote this file
rendered_on: '2026-09-30'          # ISO date, supplied by the caller -- render() must stay pure (§4.4)
project:
  name: StudyAIO
  slug: studyaio
  summary: "Local-first dockerized AI study workspace."
forge:
  kind: gitlab                     # gitlab | github | none
  remote: git@192.168.1.174:alcybersec/StudyAIO.git
  cli: glab                        # glab | gh | none
  ci: .gitlab-ci.yml               # path or directory; null when kind is none
  mirror: github                   # optional: a push-mirror that is NOT the tracker
  exclusive: true                  # when true, the other forge's CLI is blocked
attribution:
  mention_assistant_in_commits: false
spine:
  plan: docs/plan/README.md
  strategy: docs/strategy.md
  design: docs/design.md
  decisions: docs/decisions.md
  risks: docs/risk-register.md
  contracts: docs/CONTRACTS.md
  inherited: [docs/PRD.md, docs/PRD_v2.md]     # authoritative, pre-existing, never rewritten
load_order:                        # what the orchestrator reads on the first turn
  - {path: docs/plan/README.md, mode: full}
  - {path: docs/strategy.md,    mode: sections, sections: ["2","3","5","6","11"]}
  - {path: docs/decisions.md,   mode: full}
  - {path: docs/risk-register.md, mode: full}
  - {path: docs/design.md,      mode: on_demand}
milestones:
  prefix: M
  id_format: "{milestone}-S{sprint}-{OWNER}-{nnn}"
  outline: [{id: M0, name: Foundations}, {id: M1, name: Ingest}]
roles:
  - name: data
    description: "SQLAlchemy models, Alembic migrations, repositories."
    owns: ["services/app/app/models/**", "services/app/alembic/**"]
    handoff_extra: ["MIGRATION:", "PII COLUMNS:"]
    tools: [Read, Write, Edit, Glob, Grep, Bash]
    veto: false
  - name: safety
    description: "Floors, threat model, safety test tier."
    owns: ["tests/safety/**"]
    handoff_extra: ["FLOOR DELTA:", "VETO:"]
    veto: true
floors:
  - "tests/safety/** is append-only"
  - "no plaintext credentials in the tree"
test_tiers: {unit: 80, integration: 70, floor: 95}
toolchain:
  pm: uv
  test: "uv run pytest"
  format: "ruff format"
  lint: "ruff check"
  types: "mypy"
secrets: ["./.env", "./secrets/**", "./config/profile.yaml"]
observability: true                # when true, the "ships with the feature" rule and handoff line apply
```

### 5.1 The generated lock sidecar

`kitgen` writes `.claude/kit.lock.json` alongside `kit.yaml`: the same profile, resolved, as JSON.

- `kit.yaml` is the human-facing source of truth and may carry comments.
- `kit.lock.json` is generated and is what **hooks and skills read**, so the runtime path needs only
  `jq` — present essentially everywhere — rather than `yq`, which is not. The kit is meant to be
  shareable, so a hook must not depend on a tool the recipient may lack.
- The lock is the kit's **presence marker** for §4.3.
- `mtime(kit.yaml) > mtime(kit.lock.json)` means hand-edited drift: skills warn and point at
  `/kit-upgrade`; hooks ignore it and use the lock.

### 5.2 Constraints the verifier enforces

- `roles[].owns` globs MUST NOT overlap between roles.
- Every `roles[].name` MUST have a `.claude/agents/<name>.md` and a row in CLAUDE.md's agent table.
- Exactly one role MAY carry `veto: true`; if any floors exist, exactly one MUST.
- `floors` MUST be non-empty.
- `spine.inherited` paths MUST exist on disk.
- `forge.cli` MUST match `forge.kind` (`gitlab`→`glab`, `github`→`gh`, `none`→`none`), and
  `forge.kind` MUST be one of `gitlab`, `github`, `none`.
- `forge.mirror`, when set, MUST differ from `forge.kind`: a mirror is by definition not the tracker.
- `spine`, `toolchain`, `milestones` and `attribution` MUST carry all of their keys. A typo here would
  otherwise survive validation and surface as a Jinja2 `StrictUndefined` failure at render time,
  which is neither a `ConfigError` nor actionable.
- `observability` MUST be a real boolean. It is never coerced — YAML `"false"` is a string, and
  coercing it would write `true` into the lock while the human reads `"false"` in `kit.yaml`.
- Ownership globs MUST be **normalised**: repository-root-relative, with no leading `./`, no `//` and
  no `../`. Overlap is decided on literal path prefixes, so `./src/**` and `src/**` would compare as
  disjoint while overlapping in fact — and §5's `secrets: ["./.env"]` establishes the leading-`./`
  convention in the same file, which makes the mistake a natural one. A non-normalised glob is
  rejected rather than silently rewritten.
- Role entries MUST carry no unknown keys. A misspelled `handoff_extra` would otherwise load as an
  empty list, and §9.1's per-role handoff check passes vacuously on an empty list — so the role card
  would render with no handoff lines and nothing downstream would notice.
- Ownership globs MUST be directory-rooted. Overlap is decided on literal directory prefixes, so a
  glob whose first segment is wild has no prefix and is treated as overlapping everything: that makes
  extension-partitioned ownership of a shared tree (`app/**/*.py` vs `app/**/*.tsx`) invalid by
  design.

## 6. Plugin contents

```
agentic-kit/
├── .claude-plugin/marketplace.json
├── plugins/agentic-kit/
│   ├── .claude-plugin/plugin.json
│   ├── skills/
│   │   ├── kit-install/SKILL.md      greenfield installer
│   │   ├── kit-retrofit/SKILL.md     brownfield installer
│   │   ├── kit-upgrade/SKILL.md      re-render and diff
│   │   ├── orchestrating/SKILL.md    dispatch doctrine
│   │   ├── next-task/SKILL.md
│   │   ├── gate-check/SKILL.md
│   │   ├── handoff/SKILL.md
│   │   ├── new-adr/SKILL.md
│   │   ├── risk/SKILL.md
│   │   ├── plan-status/SKILL.md
│   │   └── agent-memory/SKILL.md
│   ├── hooks/
│   │   ├── hooks.json
│   │   ├── pre-bash-guard.sh
│   │   ├── pre-file-guard.sh
│   │   ├── post-edit-format.sh
│   │   └── subagent-stop-check.sh
│   └── kitgen/
│       ├── pyproject.toml
│       ├── src/kitgen/{__init__,detect,interview,render,verify,cli}.py
│       ├── templates/*.j2
│       └── tests/
├── docs/
└── README.md
```

Hook commands use `bash "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.sh"`, matching the convention used by
the official marketplace plugins.

### 6.1 Universal process skills

| Skill | Behaviour |
|---|---|
| `next-task` | Read `spine.plan`, take the next unblocked task, read its block in `spine.strategy` §11, dispatch the owning role with the task block and role card, validate the returned handoff against acceptance, run the named tests if evidence is missing, update the plan. Stop and report after a second failed attempt. |
| `gate-check <id>` | Write `docs/gates/<id>/{functional,tests,floors,operational,summary}.md`. Floors dimension is produced by the veto role and can BLOCK. Verdict PASS / CONDITIONAL / BLOCK; conditions carry an owner and a deadline task ID. |
| `handoff` | Emit the structured note. Role-specific lines come from `roles[].handoff_extra`. Evidence over prose: the test command and its last line, never a claim without a run. |
| `new-adr <title>` | Scaffold `docs/adr/NNNN-<slug>.md`, append to `spine.decisions` index. |
| `risk` | Add or update a row in `spine.risks`. |
| `plan-status` | Read-only grounding: milestone, next task, open gates, open risks. |
| `agent-memory` | The `.claude/agent-memory/<role>/MEMORY.md` convention: one fact per file, a one-line linked index entry per fact, `[[wikilinks]]` between facts. |
| `orchestrating` | Dispatch doctrine: pass paths not pasted documents; `git commit --only <path>`; `isolation: "worktree"` when 2+ agents are dispatched in one message or scopes overlap; worktree merge protocol; never `git stash` for recovery. |

### 6.2 Hooks — prose made executable

All four existing kits state these rules in English. The record shows English was not enough:
companion's R-013 (cross-session staging-boundary leak) fired **four times** as a written rule, and
the same worktree lesson is recorded twice in this user's notes.

| Hook | Event | Blocks |
|---|---|---|
| `pre-bash-guard` | PreToolUse/Bash | `git add -A`, `git add .`, `git commit -a`, `git stash`; the non-chosen forge CLI when `forge.exclusive`; `rm -rf`, `docker compose down -v`, `git push --force`/`-f`, `git reset --hard`; a `git commit -m` message matching `/claude|anthropic|co-authored-by:.*claude/i` when `attribution.mention_assistant_in_commits` is false |
| `pre-file-guard` | PreToolUse/Read,Edit,Write | any `.tool_input.file_path` matching `secrets` |
| `post-edit-format` | PostToolUse/Edit,Write | — runs `toolchain.format` on the edited file |
| `subagent-stop-check` | SubagentStop | a subagent returning with no handoff note |

Every one exits 0 when the lock is absent (§4.3).

**Hook I/O contract**, confirmed against the official `plugin-dev/hook-development` examples: the
payload arrives as JSON on stdin (`.tool_name`, `.tool_input.command`, `.tool_input.file_path`,
`.cwd`); exit 0 allows; exit 2 blocks and feeds stderr back to Claude. Blocking hooks emit
`{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "<reason>"}` on stderr,
naming the rule and the allowed alternative.

### 6.3 Forge neutrality (normative)

No rule names a forge. `forge.kind` is an interview answer and the guard enforces the chosen one:
with `kind: gitlab, exclusive: true` the `gh` CLI is blocked; with `kind: github` `glab` is blocked;
with `kind: none` neither is. The rendered CLAUDE.md states the chosen forge's CLI, CI file and the
rule not to propose the other's CI system. `mirror` names a push-mirror that is not the tracker:
fetching from it is allowed, opening issues or PRs on it is not.

### 6.4 Future MCP wrapper

Because `render` is pure (§4.4), an MCP server exposing `kit_bootstrap`/`kit_retrofit` in two stages
(`plan` returns the detection spec, interview and facts schema; `render` returns the manifest) is a
thin wrapper over the same package. Out of scope here; the purity rule is what keeps it cheap.

## 7. Rendered project files

Written into the target repository:

```
CLAUDE.md
.claude/kit.yaml
.claude/kit.lock.json
.claude/settings.json
.claude/agents/orchestrator.md
.claude/agents/<role>.md                 one per role
.claude/agent-memory/<role>/MEMORY.md    one stub per role
docs/plan/README.md
docs/strategy.md
docs/design.md
docs/decisions.md
docs/risk-register.md
docs/CONTRACTS.md
docs/adr/0001-adopt-agentic-kit.md
```

`.claude/settings.json` carries the permission allow-list derived from `toolchain`, the deny-list
derived from `secrets` plus the destructive set, and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH: "1"`.

### 7.1 `spine.inherited` is never rewritten

Pre-existing authoritative documentation (a PRD, an architecture doc, a technical plan) is recorded
in `spine.inherited` and **referenced** by `docs/design.md`, never restated or edited.

### 7.2 Brownfield preservation rule (normative)

`kit-retrofit` MUST NOT discard existing `CLAUDE.md` content. Existing content is lifted **verbatim**
into a `## Project-specific notes` section of the new CLAUDE.md. Rationale: that text holds findings
that cost real time — JobOps records that `glab config get host` answered correctly from the git
remote while the config file still said `gitlab.com`, which is precisely the failure the rule exists
to prevent. A generated file must not overwrite it.

### 7.3 Brownfield back-fill

`kit-retrofit` reads progress-shaped documents (`PROGRESS.md`, `CHANGELOG.md`, `ROADMAP.md`, a `docs/`
milestone list) and git history to populate the Completed section of `spine.plan`, so the task graph
does not propose work that is already done.

### 7.4 The task graph arrives partial, on purpose

`docs/strategy.md` is rendered complete for its **operating model**: ownership map, gates, floors,
test tiers, TDD policy, handoff protocol, dispatch loop. Its task graph (§11) is rendered with
**milestone 0 fully expanded** — entry conditions plus scaffolding tasks — and later milestones as
one-line outline entries. Expanding the next milestone's tasks is an orchestrator action at gate
time, which is how JobOps actually behaves. Generating a full M0–M6 graph from a PRD would be
inventing work.

## 8. Detection and interview

### 8.1 Detection (run locally by the installing skill)

Collected into `project_facts`: git remotes and their hosts; whether a commit exists; top-level tree;
source directories (`src/*`, `services/*`, `src/modules/*`, `apps/*`, `packages/*`); language and
package manager from lockfiles; test runner, formatter, linter, type checker from config files; CI
files; compose files; migration directories; existing `docs/**` filenames; existing `.claude/**`;
existing `CLAUDE.md`/`AGENTS.md`; candidate secret paths.

### 8.2 Greenfield vs brownfield

The discriminator is **whether source code exists**, not whether documentation exists. A new project
folder holding only a PRD is greenfield. `kit-install` therefore derives the role roster from the
architecture described in the documentation; `kit-retrofit` derives it from the directories that exist.

### 8.3 Interview

At most **five turns**, because the twelve items below are grouped rather than asked one by one:

| Turn | Items |
|---|---|
| 1 | Bulk confirmation of everything detected: summary, stack, toolchain, secrets, authoritative docs (1, 9, 11, 12) |
| 2 | Forge kind, remote, mirror, exclusivity, and commit attribution (2, 3) |
| 3 | Role roster (5) |
| 4 | Path ownership per role (6) |
| 5 | Floors, test tiers, observability, milestone scheme (4, 7, 8, 10) |

A turn whose every item was detected unambiguously is skipped. Only genuinely undecidable items are
asked individually.

| # | Asked | Default |
|---|---|---|
| 1 | Project summary and stack | drafted from README/PRD |
| 2 | Forge kind, canonical remote, mirror, exclusivity | detected from remotes; asked when two remotes exist |
| 3 | Mention the assistant in commit messages | no |
| 4 | Milestone prefix, ID format, milestone outline | `M`, `{milestone}-S{sprint}-{OWNER}-{nnn}`, outline from the PRD |
| 5 | Role roster | proposed (§8.4) |
| 6 | Path ownership per role | proposed from detected or planned layout; must partition |
| 7 | **Floors** | **none — blocking, see below** |
| 8 | Test tiers and thresholds | unit 80 / integration 70 / floor 95 |
| 9 | Secret paths | detected |
| 10 | Observability in scope | yes |
| 11 | Which pre-existing docs are authoritative | detected |
| 12 | Toolchain commands | detected |

**Floors are the one question with no default and no inference.** They are the project's
non-regressing invariants, they scope the veto role, and they become `strategy.md` §6 and a deny
rule. The installer MUST block on the user's answer rather than guess.

### 8.4 Role roster derivation

Always present: `architect`, `devops`, `qa`, and a veto role named `safety`. Added when detected:
`data` (migrations or ORM present), `frontend` (a JS/TS application directory). Domain roles are
proposed one per top-level source directory — which is how `adapters`/`llm`/`resume`/`apply-browser`
and `ml-services`/`image-voice` arose in the two existing orchestrator kits. The user confirms,
renames, merges or drops. Ownership globs are generated from the directories and must partition.

## 9. Verification and testing

### 9.1 Cross-reference verifier (`kitgen.verify`)

Runs against a rendered manifest, before anything is written:

- CLAUDE.md agent table rows == `.claude/agents/*.md` files == `kit.yaml roles[].name`.
- `roles[].owns` globs are pairwise non-overlapping and, on brownfield, every **detected source
  directory** is owned by exactly one role. Detected source directories exclude anything matched by
  `.gitignore`, plus `node_modules/`, `data/`, `.venv/`, build and cache directories: a tree can hold
  directories no role should own, and requiring coverage of those would make the check unsatisfiable.
- `/handoff`'s role-specific lines == the union of `roles[].handoff_extra`.
- `strategy.md` ownership table == `kit.yaml roles[].owns`.
- `settings.json` deny entries cover every `secrets` path.
- Every `load_order` and `spine` path is either rendered in this manifest or exists on disk.
- Exactly one veto role; `floors` non-empty.

### 9.2 Renderer tests

Golden-file tests over three fixtures: a greenfield project with a PRD only; a Python monolith with
migrations; a polyrepo-shaped `services/*` layout. Golden tests assert **structure and
cross-references**, not prose, so template wording can change without churning fixtures. Every
`kit.yaml` constraint in §5 gets a negative test.

### 9.3 Inertness test

A fixture directory with no `kit.yaml`: every hook exits 0 and emits nothing; every process skill
declines. This guards the whole-machine blast radius of a globally installed plugin.

### 9.4 Acceptance tests

- **M1** — `kitgen` renders a complete manifest for all three fixtures; verifier green; inertness
  green.
- **M2** — `321_project` and `study-helper-project` are each retrofitted **in a git worktree**; in
  each, `/plan-status` and `/next-task` run against the generated spine, `/gate-check` produces a
  bundle, and the pre-existing CLAUDE.md content is present verbatim in `## Project-specific notes`.

## 10. Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-01 | Globally installed hooks interfere with non-kit repositories | §4.3 inertness rule + §9.3 test |
| R-02 | Retrofit discards hard-won project knowledge | §7.2 preservation rule, verified in the M2 acceptance test |
| R-03 | Floors guessed rather than asked, making the veto role decorative | §8.3 blocking question; `floors` non-empty is a verifier constraint |
| R-04 | First-turn token cost of a full orchestrator plus a six-document load order | `load_order` carries per-document `mode`: `full`, `sections`, `on_demand` |
| R-05 | Ownership globs overlap, so two roles edit the same file | verifier constraint, partition check |
| R-06 | `kitgen` requires `uv`; hooks require `jq` | `uv` 0.12.7 and `jq` 1.6 confirmed on devbox; check the laptop before M2 acceptance. Hooks deliberately avoid `yq` (§5.1) |
| R-07 | Generated task graph invents work | §7.4 — M0 only, later milestones as outline |
| R-08 | Kit improvements silently diverge from installed projects | `kit-upgrade` re-renders and diffs; `kit_version` recorded in every `kit.yaml` |

## 11. Milestones

**M1 — the kit.** `kit.yaml` schema, templates, the eight universal process skills, the four hooks,
`kitgen` with `render` and `verify`, the three fixtures, golden and negative tests, the inertness
test, the marketplace and plugin manifests. Acceptance per §9.4.

**M2 — the installers.** `kit-install`, `kit-retrofit`, `kit-upgrade`; detection; the five-turn
interview; the brownfield preservation and back-fill passes. Acceptance per §9.4.
