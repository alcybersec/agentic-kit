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

- No MCP server in this scope. The renderer is designed so one can wrap it later (§6.5), but
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
machine-readable file. `kit.yaml` is that file. **The presence marker, however, is
`.claude/kit.lock.json`** — corrected 2026-10-02, because §5.1 and every hook and skill in the
implementation test the lock, not the yaml. The two are written together, so the distinction only
shows when something goes wrong, which is exactly when it matters: a project with a `kit.yaml` and no
lock is one where rendering failed partway or the lock was deleted, and in that state every guard is
correctly inert and every skill correctly declines. A marker that answered "installed" there would
make the kit claim protection it was not providing.

### 4.3 Global-plugin inertness rule (normative)

Once installed, the plugin's hooks fire in **every** project on the machine, including repositories
that are not kit projects.

> Every hook and every process skill MUST read `<project>/.claude/kit.lock.json` first, and MUST exit
> 0 (hooks) or decline with a one-line explanation (skills) when it is absent or unparseable.

The project root is `${CLAUDE_PROJECT_DIR}` when set, otherwise the `.cwd` field of the hook's stdin
payload. A missing lock is the normal case, not an error. This is covered by a test (§9.3).

### 4.4 Renderer purity rule (normative)

`kitgen.render` MUST be a pure function `render(cfg: KitConfig) -> dict[path, content]`. It MUST
NOT read the project tree, write files, call out, or read the clock — `rendered_on` is a profile field
for that reason. (Corrected 2026-10-02: this read `(answers, project_facts) -> …` and no such
signature was ever implemented. Detection produces the profile; the renderer only ever sees it.) Detection and writing live in the skills that
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
critical: []                       # optional: paths only the veto role may change, whoever owns them
```

### 5.1 The generated lock sidecar

`kitgen` writes `.claude/kit.lock.json` alongside `kit.yaml`: the same profile, resolved, as JSON.

- `kit.yaml` is the human-facing source of truth and may carry comments.
- `kit.lock.json` is generated and is what **hooks and skills read**, so the runtime path needs only
  `jq` — present essentially everywhere — rather than `yq`, which is not. The kit is meant to be
  shareable, so a hook must not depend on a tool the recipient may lack.
- The lock is the kit's **presence marker** for §4.3.
- Because the generated `settings.json` denies `Edit` on itself and on `kit.lock.json`, **no skill may
  rewrite either with the Edit tool.** `/kit-upgrade` must regenerate them by invoking the `kitgen`
  CLI, whose subprocess writes permission rules never see. `kit.yaml` is deliberately left editable:
  it is the human-facing source of truth, and hand-editing it is the drift signal above, not an error.
- `mtime(kit.yaml) > mtime(kit.lock.json)` means hand-edited drift: skills warn and point at
  `/kit-upgrade`; hooks ignore it and use the lock.

### 5.2 Constraints the verifier enforces

- `roles[].owns` globs MUST NOT overlap between roles.
- Every `roles[].name` MUST have a `.claude/agents/<name>.md` and a row in CLAUDE.md's agent table.
- Exactly one role MAY carry `veto: true`; if any floors exist, exactly one MUST.
- `floors` MUST be non-empty.
- `spine.inherited` paths MUST exist on disk. *(Checked by `verify()` only when it is given a
  `project_root`; with none it cannot look, and treating "absent from the manifest" as absent would
  make every clean render verify dirty — §9.1.)*
- `forge.cli` MUST match `forge.kind` (`gitlab`→`glab`, `github`→`gh`, `none`→`none`), and
  `forge.kind` MUST be one of `gitlab`, `github`, `none`.
- `forge.mirror`, when set, MUST differ from `forge.kind`: a mirror is by definition not the tracker.
- `spine`, `toolchain`, `milestones` and `attribution` MUST carry all of their keys. A typo here would
  otherwise survive validation and surface as a Jinja2 `StrictUndefined` failure at render time,
  which is neither a `ConfigError` nor actionable.
- Every `toolchain` value MUST be a non-empty command string. An empty one renders the permission rule
  `Bash(:*)`, whose meaning depends on how the host parses an empty prefix — plausibly
  match-everything, which would silently void the deny list it sits beside.
- Secret paths are denied for `Read` **and** `Edit`, and for nothing else. Per the permissions
  documentation a `Read` deny "also blocks the Edit and Write tools on the same path, including
  creating a new file there", while "NotebookEdit isn't covered, so add an `Edit` deny rule" — so the
  pair is the complete closure over every file tool. A `Write(path)` rule is **accepted but never
  consulted, and warns at startup**, so emitting one is strictly worse than omitting it.
- `secrets` patterns MUST begin `./` (enforced 2026-10-02, fix F1). They reach **two matchers with
  different owners**: the kit's hooks, which are root-anchored and match the whole candidate path, and
  the `Read()`/`Edit()` deny rules in `settings.json`, whose matching is Claude Code's. The two agree
  on the `./` form and need not on any other — a bare `secrets/**` is root-anchored in the hook and may
  match at any depth in the deny rule, so the layers would protect different sets of files while the
  profile named one. Rejected rather than rewritten, as with `owns`. Within the hooks, patterns are
  **root-anchored and matched whole**, like `owns` globs. `./.env` covers the
  repository root only — a nested `sub/.env` needs `./**/.env` — and `./secrets/**` covers the files
  under that directory but not a read of the directory entry itself, which exposes filenames. Both are
  traps for whoever authors a profile by hand, so the interview should prefer `./**/<name>` for any
  secret that can appear at more than one depth. As with `owns`, matching is case-sensitive: on a
  case-insensitive volume `.ENV` reaches a file that `./.env` names, and the kit does not pretend
  otherwise (§5.2).
- The observability rule binds a role **within the paths it owns** (clarified 2026-10-02, decision 1).
  Read as "every role instruments the shared observability module", it is unsatisfiable for any role
  that does not own that module — on a real roster, most of them. A shared metric registry or log
  schema is an interface, so it is a `CONTRACTS.md` entry and contract-first already covers it: the
  owning role adds the field on request.
- `observability` MUST be a real boolean. It is never coerced — YAML `"false"` is a string, and
  coercing it would write `true` into the lock while the human reads `"false"` in `kit.yaml`.
- Ownership globs MUST be **normalised**: repository-root-relative, forward-slashed, with no leading
  `/`, no `.`, `..` or empty segment, and no backslash. Overlap is decided on literal path prefixes,
  so any unnormalised spelling of the same path compares as disjoint while overlapping in fact —
  `./src/**` against `src/**`, `/src/**` against `src/**`, a bare `.` against anything. §5's
  `secrets: ["./.env"]` establishes the leading-`./` convention in the same file, and detection can
  report an absolute path or the repository root as `.`, so both spellings are reachable. The check is
  per path **segment**, not a list of forbidden substrings, and a non-normalised glob is rejected
  rather than silently rewritten. A leading dot in a segment *name* (`.github/workflows/**`,
  `.gitlab-ci.yml`) is not a `.` segment and is valid.

  Case folding is deliberately **not** applied. `Src/**` and `src/**` name the same directory on a
  case-insensitive volume and different ones on ext4; normalising would be wrong on Linux, so the
  kit treats them as distinct and does not pretend otherwise.
- Role entries MUST carry no unknown keys. A misspelled `handoff_extra` would otherwise load as an
  empty list, and §9.1's per-role handoff check passes vacuously on an empty list — so the role card
  would render with no handoff lines and nothing downstream would notice.
- `critical` is **optional** and defaults to empty. Each entry carries the same normalisation rule as
  an `owns` glob — which also rules out a leading `./`, since `.` is a rejected segment — because the
  ownership guard matches both with the same code. A `critical` path deliberately **may** sit inside
  another role's owned tree: it is not ownership, it is a refusal that outranks ownership, so the
  overlap check does not apply to it.
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
| `gate-check <id>` | Write `docs/gates/<id>/summary.md` (Functional, Tests, Operational, Milestone additions, Verdict, and the Floors verdict by reference) and `docs/gates/<id>/floors.md`, authored by the veto role itself. Verdict PASS / CONDITIONAL / BLOCK; conditions carry an owner and a deadline task ID. **Two files, decided 2026-10-02 (decision 4):** the five dimensions are the discipline and are unchanged, but four of them arrive as handoff notes the Orchestrator must paste as evidence anyway, so a five-file bundle was ceremony — `summary.md` restated the other four. Floors keeps its own file because it can BLOCK, and a verdict the veto role writes itself cannot be softened in synthesis. |
| `handoff` | Emit the structured note. Role-specific lines come from `roles[].handoff_extra`. Evidence over prose: the test command and its last line, never a claim without a run. |
| `new-adr <title>` | Scaffold `docs/adr/NNNN-<slug>.md`, append to `spine.decisions` index. |
| `risk` | Add or update a row in `spine.risks`. |
| `plan-status` | Read-only grounding: milestone, next task, open gates, open risks. |
| `kit-doctor` | Run `bin/kit-doctor.sh`: fire every guard with a payload it must refuse and report which ones did, plus `jq`, the lock's readability, lock-vs-profile freshness, the formatter's presence on PATH, and whether each role card registers the ownership guard. Added 2026-10-01 (fix 1.2). It exists because §4.3's inertness rule makes a **disarmed** guard and a **correctly inert** one indistinguishable: everything exits 0, and Claude Code reads any non-2 exit as "continue". Nothing else in the kit can tell the two apart. Exit 0 all-clear, 1 otherwise, and it states the two things no script can check — workspace trust and Bash. |
| `agent-memory` | The `.claude/agent-memory/<role>/MEMORY.md` convention: one fact per file, a one-line linked index entry per fact, `[[wikilinks]]` between facts. |
| `orchestrating` | Dispatch doctrine: pass paths not pasted documents; `git commit --only <path>`; `isolation: "worktree"` when 2+ agents are dispatched in one message or scopes overlap; worktree merge protocol; never `git stash` for recovery. |

### 6.2 Hooks — prose made executable

All four existing kits state these rules in English. The record shows English was not enough:
companion's R-013 (cross-session staging-boundary leak) fired **four times** as a written rule, and
the same worktree lesson is recorded twice in this user's notes.

| Hook | Event | Blocks |
|---|---|---|
| `pre-bash-guard` | PreToolUse/Bash | `git add -A`, `git add .`, `git commit -a`, `git stash`; the non-chosen forge CLI when `forge.exclusive`; `rm -rf`, `docker compose down -v`, `git push --force`/`-f`, `git reset --hard`; a `git commit -m` message matching `/co-authored-by:.*(claude\|anthropic)\|generated (with\|by).*(claude\|anthropic)\|🤖/i` when `attribution.mention_assistant_in_commits` is false |
| `pre-file-guard` | PreToolUse/Read,Edit,Write,NotebookEdit | any `.tool_input.file_path` matching `secrets`, by its own name **and** by its `realpath` target, so a symlink and a `..` traversal are both caught |
| `post-edit-format` | PostToolUse/Edit,Write | — runs `toolchain.format` on the edited file, and **never fails a tool call** |
| `ownership-guard` | PreToolUse/Edit,Write,NotebookEdit,MultiEdit | a role writing a path another role owns, a `critical` path, or any of the files enforcement itself depends on. Role from the payload's `agent_type`; no `agent_type` (the Orchestrator) or an unknown one exits 0. See §6.4 |
| `subagent-stop-check` | SubagentStop | a subagent returning with no handoff note, read from `last_assistant_message`, the subagent's own `agent_transcript_path`, or a `SubagentHandback` call's `input` — any one of the three satisfies it |

Every one exits 0 when the lock is absent (§4.3).

**`post-edit-format` never blocks, and formats a fixed extension set.** It is a `PostToolUse` hook, so
the edit has already happened: a formatter that is missing, non-zero, slow or noisy is a formatting
problem, not a policy breach, and converting it into a failed tool call would be strictly worse than an
unformatted file. It exits 0 unconditionally — verified against a formatter that exits non-zero, does
not exist, is the empty string, writes to stderr, is a bare `*`, and hangs until `timeout` kills it.

It formats `py ts tsx js jsx go rs rb java kt css scss` only. A `prettier` project would want `.md`,
`.json` and `.yaml`, and a `gofmt` or `ruff format` pointed at `.md` would error or mangle the file — so
the right fix is a `toolchain.format_extensions` key set during the interview, not a wider default
inside a hook. Recorded as an M2 item rather than guessed at here.

**Where the deny list stops.** It covers what a cooperative agent plausibly does *by reflex* and
cannot undo: the staging sweep, the force push, the hard reset, the working-tree wipe
(`git checkout -- .`, `git restore .`, `git clean`), the volume-deleting `down -v`, and deleting a
remote branch. Each is listed in every spelling, because `Bash(x:*)` means `Bash(x *)` and the space
is part of the rule — `Bash(git commit -a:*)` does **not** match `git commit -am "wip"`.

Deliberately **not** denied: `git push --force-with-lease`, which refuses when the remote has moved
and is the safe alternative the `--force` deny steers toward; `git branch -D`, recoverable from the
reflog and required by the orchestrator's own worktree-merge protocol; and `git rebase`, which is
legitimate on a trunk-based one-task-per-branch model. None of those three is in `allow` either, so
they prompt. A rule earns its place by being both irreversible and reflexive; "destructive" alone
would grow this list without end.

**What the permission file and these hooks do NOT guarantee.** Both `.claude/settings.json` rules and
these hooks match on **command strings**, so neither is a sandbox:

- A command routed through an allow-listed interpreter is unconstrained. `toolchain.pm` becomes
  `Bash(uv:*)` so that ordinary work does not prompt, and `uv run python -c "…"` therefore matches no
  deny rule however destructive its argument.
- **`pre-file-guard` is not a second boundary, and it was wrong of this document to imply otherwise.**
  It duplicates `settings.json`'s secret denies deliberately, but an agent with shell access can edit
  `kit.lock.json` or the hook script as easily as `settings.json`, so it adds no containment. Its two
  real jobs are that it reads the lock at **call time**, so a `secrets` change takes effect without a
  re-render, and that it **explains itself** — naming the pattern that matched and pointing at the
  committed `.example` template, where a deny rule gives a bare refusal.
- Path denies reach further into Bash than one might expect, and `cat ./.env` **is** blocked: they
  apply "to file commands Claude Code recognizes in Bash, such as `cat`, `head`, `tail`, `sed`, and
  `tee`, and to the targets of Bash redirections such as `> file` and `< file`". The residual gap is
  narrower and specific — a reader Claude Code does not recognise (`xxd`, `base64`, `strings`), a
  command that does not name the file (`grep -r TOKEN .`), and any interpreter. `pre-bash-guard`'s
  secret check exists for exactly that remainder, not because path denies are blind to shell.
- The hooks exempt a committed `*.example`, `*.sample`, `*.template` or `*.dist` file from the secret
  match (added 2026-10-01, fix 0.7: a `./secrets/**` pattern swallowed `secrets/prod.yaml.example`, so
  the deny message recommended a path the same guard refused). **The deny rules do not**, and cannot:
  `Read(./secrets/**)` covers the template too, deny is evaluated before allow, and no negation is
  available to carve an exception. So in a project whose `secrets` cover a directory, the template is
  readable to the hooks and still refused by the permission layer. Keep project templates outside the
  secret directory — `./.env.example` beside `./.env` is unaffected, since `./.env` does not match it.
- Exclusive file-path ownership **is** enforced, by the per-role guard in §6.4 — but only against the
  file tools. A role can still reach another role's tree through Bash (`sed -i`, a script), because
  that guard matches `Edit|Write|NotebookEdit|MultiEdit` and not command strings.
- **Plugin hooks DO fire for a subagent's tool calls** — verified on a live install, 2026-10-02.
  This was the sharpest open question: if they fired only for the main agent, `pre-bash-guard` and
  `pre-file-guard` would protect the Orchestrator and nothing else. They fire. A `qa` subagent's
  `git commit` carrying a `Co-Authored-By` line was refused by `pre-bash-guard` with the attribution
  message, and that rule is the one guard with **no** deny-rule duplicate, so the block can only have
  come from the hook. The docs agree: *"Hooks from settings files, managed policy settings, and plugins
  also run inside subagents."* The payload carries `agent_id` and `agent_type`, and `agent_type` is the
  subagent's frontmatter `name` — observed as `"qa"`. See §6.4 for what that makes possible.
- **An untrusted workspace drops `permissions.allow` and keeps `permissions.deny`** (verified
  2026-10-02). Claude Code's own warning names the list: *"Ignoring 20 permissions.allow entries from
  .claude/settings.json: this workspace has not been trusted"* — and the rendered file held exactly 20
  allow entries against 31 deny entries, so the denies were retained. The practical shape of an
  untrusted checkout is therefore: **secret denies still bite, conveniences do not** (every allowed
  toolchain command starts prompting), and the frontmatter ownership guard is absent. The remedy is in
  the warning: accept the trust dialog once, or set
  `projects["<path>"].hasTrustDialogAccepted: true` in `~/.claude.json`.
- **`--safe-mode` disables the kit entirely**, not partially (confirmed 2026-10-02): it starts with
  "CLAUDE.md, skills, installed plugins, hooks, MCP servers, custom commands and agents … disabled".
  That is the unambiguous case — nothing of the kit is present, so nothing can half-apply.
- **The ownership guard no longer depends on workspace trust** (resolved 2026-10-02). It was
  registered from the project's own `.claude/agents/` frontmatter, which an untrusted checkout and
  every `-p` session skip — so it was absent exactly where this document claimed enforcement. It is a
  plugin hook now (§6.4) and fires in both. What is still true: `--safe-mode` disables installed
  plugins, so nothing of the kit runs there at all.
- **Inert by design and broken are indistinguishable from the outside.** Every hook exits 0 when `jq`
  is missing, when the lock is absent or unparseable, or when the script itself has been renamed or
  deleted — and Claude Code treats any non-2 exit as "continue". That is the right default for a
  machine-wide plugin (§4.3), and it means a silently disarmed guard looks exactly like a correctly
  inert one. `/kit-doctor` exists to tell them apart by firing each guard with a payload that must be
  refused and reporting which actually refused it.

What the deny list does have going for it is precedence: "deny rules from any scope are evaluated
before allow rules", and a hook cannot loosen them — "Claude Code evaluates deny and ask rules
regardless of what a PreToolUse hook returns". So a deny rule is the strongest instrument here; there
are simply fewer things it can express than its wording suggests.

**Where `pre-bash-guard`'s matcher stops, concretely.** It segments the command on `; | & ( )` and
newlines, peels wrapper prefixes and environment assignments, and tests each segment. That leaves a
known, tested set of spellings it does not catch:

| Spelling | Why |
|---|---|
| `bash -c "git add -A"`, `sh -c '…'` | the command is inside a quoted string, not a segment |
| `xargs git add -A` | `xargs` builds its argv at run time |
| `git add -A\` (trailing backslash) | the token is `-A\`, not `-A` |
| `cat "$(echo .e)nv"` | the path is constructed at run time — unfixable in principle |
| `git commit -F msg.txt` | the hook does not read file contents |

And one false positive it accepts in exchange: `echo "a; git stash now"` is blocked, because the
segmenter is not quote-aware and sees `git stash now` after the `;`. Note `echo 'a; git add -A'`
happens to pass, but only by luck — the closing quote sticks to the last word, making it `-A'` — so
the escape is an accident of spelling, not a rule. Making the segmenter quote-aware means writing a
shell parser inside a `PreToolUse` hook, which costs more than it buys for a layer that is not a
containment boundary.

These are pinned by `test_known_matcher_limits`, which asserts the *current* behaviour so that closing
one becomes a deliberate decision rather than an accident, and so nobody reads the list above as
coverage.

The honest claim is that this layer stops **accidents and drift by a cooperative agent** — the
staging sweep, the force push, the volume-deleting `down -v`, the wrong forge CLI, the credential
read reached for without thinking. It is not a containment boundary and must never be described as
one. Containment needs the agent to run somewhere it cannot reach what matters.

**The SubagentStop payload is not the PreToolUse payload**, and getting this wrong silently inverts the
handoff gate. Verified against the Claude Code binary, which constructs it with
`hook_event_name: "SubagentStop"`, `stop_hook_active`, `agent_id`, **`agent_transcript_path`**,
`agent_type` and `last_assistant_message`:

- **Read `agent_transcript_path`, never `transcript_path`.** Both are present — the latter arrives with
  the base fields and points at the **parent session's** transcript. A hook reading it inspects the
  orchestrator's conversation instead of the subagent's, so the check passes because the *orchestrator*
  discussed a handoff note while the subagent emitted nothing. A gate that passes on the wrong evidence
  is worse than no gate, because §9 of the generated `strategy.md` tells the Orchestrator to trust it.
  No test catches this, since tests construct their own payloads and the wrong field name is consistent
  across plan, code and fixture.
- **Prefer `last_assistant_message`.** The payload hands over the subagent's final text directly, which
  removes any assumption about transcript JSONL shape and is what the agent actually ended on.
- **Honour `stop_hook_active`.** The harness's own guidance: *"For Stop/SubagentStop hooks, check
  `stop_hook_active` in the input and return success while it's true."* Without it, an agent that cannot
  produce a note is blocked repeatedly until the harness's cap (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`,
  default 8) intervenes — eight wasted turns, surfacing as the subagent looping rather than as a clear
  failure.
- **The note must appear in *either* source, not the first available one.** Checking
  `last_assistant_message` and only falling back when it is empty blocks a note that genuinely exists
  whenever the agent adds a closing remark after emitting it — "Done." after the note is entirely
  ordinary, and the gate would refuse a finished task. The subagent transcript is still read before the
  parent's, so the false negative above stays closed.
- **A third source: the `SubagentHandback` call in the transcript** (added 2026-10-01, fix 1.5). That
  tool is force-granted in auto mode on v2.1.271+, overriding `tools` and `disallowedTools`, and a
  subagent handing back through it carries its report in the call's `input` — so the note is in neither
  source above, and a task that was in fact finished gets blocked for not emitting one. The hook reads
  every string leaf of that call's `input` rather than one named field: the field name is not something
  it can pin, and an unexpected schema must not become a false block. **Only** `SubagentHandback` is
  read this way; a note typed into a file by a `Write` call still does not count, because the
  Orchestrator has not been handed it.

**What this gate can promise, and what it cannot.** Because `stop_hook_active` makes the hook succeed on
the retry, **it can only ever block once**: an agent that never produces a note is nudged a single time
and then allowed to stop. That is the harness's intended Stop-hook semantics rather than a defect, but it
means the hook *prompts for* a handoff note and cannot *force* one. Validating the handoff remains the
Orchestrator's job, which the generated `strategy.md` §9 already requires — "a note without a pasted run
is not evidence and the Orchestrator re-runs the tests itself." Nobody reading this hook should conclude
the note is guaranteed.

**Hook I/O contract**, confirmed against the official `plugin-dev/hook-development` examples: the
payload arrives as JSON on stdin (`.tool_name`, `.tool_input.command`, `.tool_input.file_path`,
`.cwd`); exit 0 allows; exit 2 blocks and feeds stderr back to Claude. Blocking hooks emit
`{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "<reason>"}` on stderr,
naming the rule and the allowed alternative.

### 6.2b What the hooks cost, and why (measured 2026-10-02)

Every hook sits on the hot path of a tool call, so this is a design constraint and not an
afterthought. Measured on devbox, 20 runs each, against a floor of ~20 ms for `bash -c` plus one `jq`:

| Tool call | Hooks that fire | Non-kit repo | Kit project |
|---|---|---|---|
| Bash | `pre-bash-guard` | 23 ms | **108 ms** (was 193) |
| Read | `pre-file-guard` | 22 ms | **93 ms** (was 127) |
| Edit / Write | `pre-file-guard`, `ownership-guard`, `post-edit-format` | 70 ms | **299 ms** (was 528) |
| Grep, Glob, Task, WebFetch | none | 0 | 0 |

**The rule that gets it there: one `jq` pass per input, never one per question.** The guards asked jq
up to fourteen separate questions each — `kit_q` and `kit_in` are a process per call — which cost 308 ms
on an `Edit` in the ownership guard alone. `kit_read_nul` reads a whole fixed-order record from a single
`jq -j`, and `test_shell_hygiene.py` holds every hook to at most two jq invocations and bans `kit_q`
and `kit_in` inside one.

Fields are **NUL-delimited, not newline-delimited**. The first single-pass version read line by line and
silently truncated `$cmd` at its first newline, so a `git commit -m` message — which spans lines by
definition — stopped being checked for attribution. A list field travels as one value with newlines
inside it, which is already the format `kit_match_glob` expects.

**The remaining floor is `kit_init`**: ~40 ms of its own, two jq calls to validate the payload and the
lock, shared by every hook. Going below ~95 ms per hook means moving that correctness gate into each
hook, which is how the kit acquired a third path matcher once already. Not worth it.

In a repository with no `.claude/kit.lock.json` every hook exits at the lock check, so the cost is pure
process startup and nothing in the kit can reduce it.

### 6.2a What `claude plugin validate` does and does not catch

Established empirically by corrupting a copy of the plugin, because the answer decides which checks the
test suite has to own:

| Defect | Validator |
|---|---|
| `hooks.json` is invalid JSON | **fails** — *"At runtime this breaks the entire plugin load"* |
| an unknown hook event name | **warns** — *"unknown hook event; entry ignored at runtime"* |
| a `command` naming a script that does not exist | **passes silently** |
| no `version` in `plugin.json` | warns |

The third row is the dangerous one, and it is the same shape as the `agent_transcript_path` bug: a hook
wired to a renamed or missing script never fires, every test that invokes the script directly still
passes, and nothing complains. So `test_hooks_json.py` owns that check —
`test_every_referenced_script_exists_and_is_executable` is load-bearing, not decorative. The event set
is pinned for the same reason, since a typo there only warns.

A clean `claude plugin validate` therefore means the manifest parses and the events are real. It does
**not** mean the hooks fire. That needs a live session with the plugin installed, which is Task 17.

### 6.3 Forge neutrality (normative)

**No *hardcoded* forge**, which is not the same as no rule naming one — the original wording
overstated it (corrected 2026-10-01). `settings.json`'s allow-list and `pre-bash-guard`'s
exclusivity check both name `glab` and `gh` literally, and must: the two CLIs do not share a noun
(`mr` against `pr`), so a verb-level rule cannot be written without branching on the kind. What the
rule means is that nothing in the kit *assumes* a forge, every forge-specific string derives from
`forge.kind`, and `kind: none` renders no forge rule at all. Adding a third forge is a template
branch plus a `CLI_FOR_FORGE` entry, not a rewrite.

`forge.kind` is an interview answer and the guard enforces the chosen one:
with `kind: gitlab, exclusive: true` the `gh` CLI is blocked; with `kind: github` `glab` is blocked;
with `kind: none` neither is. The rendered CLAUDE.md states the chosen forge's CLI, CI file and the
rule not to propose the other's CI system. `mirror` names a push-mirror that is not the tracker:
fetching from it is allowed, opening issues or PRs on it is not.

**The CLI is allowed by read verb, not wholesale** (added 2026-10-01, fix 1.4). `Bash(<cli>:*)`
pre-approved `mr create`, `mr merge` and `issue close` along with everything else, so an agent could
open and merge its own merge request without a prompt — while the generated CLAUDE.md tells it that
outward-facing actions are the user's. `settings.json` now allows only `list`, `view`, `diff`,
`checks`/`status` and `auth status`, and `pre-bash-guard` denies `create|close|reopen|merge|delete|`
`approve|revoke|edit|update|note|comment` on `issue|mr|pr|release` with the reason and the remedy:
put the title, body and target branch in the handoff note. Anything in neither list simply prompts.

### 6.4 Per-role ownership guard

`plugins/agentic-kit/hooks/ownership-guard.sh` ships **with the plugin** and is registered in
`hooks/hooks.json` for `Edit|Write|NotebookEdit|MultiEdit`. It takes the role from the payload's
**`agent_type`**, which Claude Code sets to the subagent's frontmatter `name` — the role name for a kit
role card.

*(Changed 2026-10-02. It used to be rendered into the project and registered by each role card's
frontmatter `hooks:` block with the role as `$1`. Frontmatter hooks are skipped until the workspace is
trusted and a `-p` session never counts as trusted, so the guard was **absent** in a fresh clone and in
every non-interactive run while this section claimed ownership was enforced. A live install confirmed
that plugin hooks fire inside a subagent even in an untrusted checkout, and that `agent_type` arrives
on `Edit` and `Write` payloads alike — observed as `"safety"` and `"qa"`.)*

Two rules now follow from the payload rather than from a registration choice:

- **No `agent_type` is the main thread**, which is the Orchestrator: it owns no paths and legitimately
  writes the dispatch state, the register and the gate bundles. Never guarded, structurally.
- **An `agent_type` naming no role in the lock** — `Explore`, `general-purpose`, a project's own
  subagent — exits 0. An ownership map describes the roles it lists and nothing else.

Because the guard now sits beside `lib/kitlock.sh`, it **sources** the matcher instead of inlining it.
The inlined copy and the two tests that policed it for drift are gone: there is no copy to drift.

It blocks a path **only when another role owns it**. An unowned path crosses nobody's boundary and is
allowed; without that rule the guard would block `Makefile`, `pyproject.toml`, `README.md` and the
docs spine, and be switched off within a day. Validated against a 70-case corpus over all three
fixtures before implementation.

Refused for every role regardless of the map: another role's `agent-memory`, any `.claude/agents/**`
card, `spine.plan` (subagents emit a handoff note instead), and **`spine.strategy` and `spine.risks`**.

Amended 2026-10-01 (fix 0.5) — the list above stopped short of the files enforcement itself depends on.
Also refused for every role: **`.claude/hooks/*`**, **`.claude/kit.yaml`**, **`.claude/kit.lock.json`**,
**`.claude/settings.json`**, and every path in **`spine.inherited`**. The first four are the same
argument as `strategy.md` carried one step further: one `Edit` of the guard, or of the lock it reads the
ownership map from, disarms ownership for every role at once — a shorter route to self-expansion than
rewriting the rulebook, and the original list left it open. `spine.inherited` holds the documents the
project arrived with: a role that may rewrite the PRD can make any task compliant by editing what
compliance means. `settings.json` mirrors the deny for `hooks/**`, `agents/**`, `settings.json` and the
lock, which binds the Orchestrator too — all four are generated, so a hand edit is overwritten by the
next render regardless. `kit.yaml` is deliberately **not** mirrored: it is the one file a legitimate
change to the kit edits, and a session-wide deny would leave nobody able to add a role.

Those last two matter for the same reason `settings.json` denies `Edit` on itself: a role agent could
otherwise rewrite §6 — the floors it is bound by — or its own §2 ownership row, which is
self-expansion by the shortest possible route. `spine.decisions`, `spine.contracts` and `spine.design`
stay writable: `design.md` invites per-role sections, and the contract-first rule requires the
implementing role to record a contract before building against it.

A project-wide `Edit` deny in `settings.json` is the wrong instrument for this, because the
Orchestrator legitimately writes the dispatch state, the register and the §11 expansions. Only a
role-scoped guard can distinguish them.

**Critical paths** (added 2026-10-02, decision 1). Ownership is directory-granular: a kill switch, a
permission table or a migration guard lives with the code that reads it, so the role that must guard it
cannot own the directory, and claiming the single file is an ownership overlap. `critical: [paths]` in
the profile resolves this narrowly — every role is refused those paths, **including the one that owns
the surrounding tree**, and the veto role is allowed them **even though it owns nothing around them**.
Checked before the ownership map in both directions.

This was chosen over general more-specific-wins precedence, which would have meant reworking
`_overlaps`, the guard's match loop (it refuses on the first other-role match; ranking would require
collecting every match and ordering by prefix length) and `verify._covers`. The failure mode of a
precedence bug is *silently widening* access, which is the one thing this guard exists to prevent, and
one file does not justify that risk. If a second use case appears, revisit.

**Who may author an ADR.** `architect` owns `docs/adr/**` in every generated roster, so no other role
can file one — including the veto role, whose own §6 requires an ADR to weaken a floor. `/new-adr` is
therefore an Orchestrator-or-`architect` skill, and §6 says so rather than leaving it to be discovered.

**Not registered on the orchestrator**, which owns no paths and legitimately writes the dispatch
state, the risk register and the gate bundles.

**It could stop depending on workspace trust** (opportunity recorded 2026-10-02, not yet implemented).
A live install showed that plugin-level `hooks.json` hooks fire inside subagents and that the payload
carries **`agent_type`**, which is the subagent's frontmatter `name` and therefore the role name —
observed as `"qa"`. The guard currently learns its role from `$1`, passed by the role card's frontmatter
`hooks:` block, which is exactly what workspace trust skips. Reading `agent_type` from the payload
instead would let the guard ship in the plugin's `hooks.json`, where it fires regardless of trust and in
a `-p` session. Two consequences fall out rather than being arranged: a payload with **no**
`agent_type` is a main-agent call, so "not registered on the orchestrator" becomes structural; and an
`agent_type` that matches no role in the lock (`Explore`, `general-purpose`) must exit 0, so the guard
constrains only the roles the profile describes. The rendered copy's reason for existing — "the plugin
may not be installed in the target project" — inverts once the plugin is the thing providing the hook.
Worth doing; it closes the one real hole in this guard's coverage.

**Where this guard does not run.** As a plugin hook it no longer depends on workspace trust, so the
earlier limit — absent in a fresh clone and in every `-p` session — is closed. What remains: it matches
the **file tools only**, so Bash reaches past it (§6.2), and it is gone entirely under `--safe-mode`,
which disables installed plugins. It was never a containment boundary and still is not. `/kit-doctor`
reports whether it actually refused a cross-role edit, and whether it correctly left the main thread
alone — a guard that blocks the Orchestrator would stop the one agent that must write the plan.

It is rendered rather than shipped in the plugin because a project's role card cannot reference
`${CLAUDE_PLUGIN_ROOT}`; the side benefit is that ownership enforcement survives in a checkout where
the plugin is not installed.

**Hazard worth stating:** if one role owns a broad test tree, every other role is blocked from
writing tests while the kit mandates test-first. §8.4 therefore says test paths should be owned by
whoever owns the code under test, or left unowned.

### 6.5 Future MCP wrapper

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

### 7.1a Which spine documents may be re-rendered

`/kit-upgrade` (M2) re-renders templates and diffs them against the repo, so each spine document needs
a classification before that is written, not after:

| Document | Class |
|---|---|
| `strategy.md` §1–§10 | **stable scaffolding** — every line derives from the profile; safe to re-render and diff |
| `strategy.md` §11 | **mixed** — §1–§10 regenerate, the task graph is hand-expanded at gate time |
| `design.md`, `decisions.md`, `CONTRACTS.md`, `risk-register.md` | **living** — generated headings only; the content below them is hand-written and a diff is noise |
| `plan/README.md` | **generate-once** — it is pure state after the first task, so a re-render *deletes* the dispatch record |
| `adr/0001-adopt-agentic-kit.md` | **generate-once** — it stamps `rendered_on` and `kit_version`; re-rendering restamps an *Accepted* ADR with a later install's date, falsifying the record it exists to preserve |

`kitgen` therefore declares `GENERATE_ONCE` and `LIVING` beside `SINGLETONS`, with
`render.is_preserved()` as the single answer to "must an existing copy of this path survive?" — the two
sets plus every path under `.claude/agent-memory/`, matched by prefix because the roster is per-profile.
The CLI **never** overwrites anything it reports — `--force` included. (Amended 2026-10-01, fix 0.3:
until then only the two generate-once paths were held back, so `--force` restored the empty scaffold
over all five living documents and every role's memory, and this table described an intention the code
did not implement.) `--force` means "replace the generated scaffolding", not "discard
history", so regenerating a generate-once file is a deliberate manual act: delete it first. The CLI
reports on stderr which files it kept, naming each, so the skip is never silent.

**On-disk drift is not detected in M1.** `kitgen verify` re-renders from the profile and checks
internal consistency plus the presence of `spine.inherited` docs; it does not compare the rendered
manifest against what is actually on disk, so a hand-edited or corrupted `CLAUDE.md` passes. That
comparison is `/kit-upgrade`'s job in M2, and it needs this classification to do it: a difference in
*stable scaffolding* is drift to offer as a patch, a difference in a *living* document is expected and
must be left alone, and a *generate-once* file is never compared at all.

### 7.1b The CLI's exit codes are an interface

M2's installing skills branch on these, so they are normative:

| Code | Meaning |
|---|---|
| 0 | the kit was written, or a dry run completed |
| 1 | verification found problems; **nothing was written** |
| 2 | the profile is bad — unparseable, missing a field, a scalar where a mapping belongs, an unreadable file, or a malformed `--rendered-on` |
| 3 | refused to overwrite existing files; **nothing was written** |
| 4 | the write failed partway, so the tree is **incomplete**; a plain retry will refuse with 3, and recovery is to fix the cause and re-run with `--force` |

**Advisories are not problems.** `kitgen.advise()` prints `advice: …` lines on stderr and **never**
affects the exit code (added 2026-10-02, decision 3). A roster above §8.4's ceiling, a role owning no
path, or a role holding no task in an expanded graph are all valid configurations worth a second look;
reporting them through code 1 would tell a calling skill that nothing was written.

`--dry-run` **writes nothing and returns the code the real run would return** — including 3 when the
tree has clashes and 1 when verification fails. It is a predictor, not a separate verdict: a preview
that reports 0 where the real run reports 1 is worse than no preview. Its stdout carries the manifest,
the clashes that would cause a refusal, and the generate-once files that would be kept, so a caller can
act on the detail without re-deriving it.

Codes 1 and 3 guarantee an untouched tree. Code 4 does not, and is the only state where the kit can be
half-installed: the CLI is not atomic, and its stderr names the file that failed and the files already
written so the caller can tell how far it got. Collapsing a write failure into 1 would tell a skill
that verification failed when in fact a partial kit is on disk.

**Clashes and blockers are distinct, and `--force` clears only the first** (amended 2026-10-01, fix 0.4).
A *clash* is a regular file where the manifest wants a file: `--force` overwrites it, subject to §7.1a.
A *blocker* is something in the way that cannot be written through and that `--force` must **not**
remove, because removing it means deleting a path the kit does not own:

| Blocker | What fails |
|---|---|
| a non-directory where a parent directory must be created (including a *broken symlink*, which `exists()` reports as absent) | `mkdir` |
| a directory where a file must be written | `write_text` |

Both are detected in the preflight and return **3** with an untouched tree, whether or not `--force` was
given, and are named on stderr once per obstruction rather than once per blocked path. Before the fix
they were invisible to the preflight, so `--dry-run --force` predicted **0** for a run that exited **4**
having already written fourteen files including the lock — the precise failure the paragraph above says
a preview must never produce. `--dry-run` reports them under a `blocked` key.

Code 4 therefore now means a write that failed for a reason the preflight cannot see: a read-only
directory, a full disk, a revoked permission mid-run.

### 7.2 Brownfield preservation rule (normative)

**This binds `kit-retrofit`, which is M2. M1 does not implement it** (recorded 2026-10-02.) The only
install path M1 ships is `kitgen render`, and `CLAUDE.md` is generated scaffolding there: `--force`
replaces it. Fix 0.3 made the five living spine documents and all agent memory safe, and deliberately
did not extend that to `CLAUDE.md`, because a profile change that never reaches it leaves the root
context describing a project the kit no longer configures. So **do not point `kitgen render --force` at
a repository with a curated `CLAUDE.md`** until the retrofit skill exists; `--force` now lists every
file it will overwrite, and `CLAUDE.md` appears in that list.

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
non-regressing invariants, they scope the veto role, and they become `strategy.md` §6. They do **not**
become permission rules: a floor is an invariant ("the safety tier is append-only", "p99 under
200 ms"), not a command string, and nothing in the rendered `settings.json` reads `floors`. The installer MUST block on the user's answer rather than guess. **The installer is M2**, so nothing enforces this in M1 (recorded 2026-10-02): `kitgen` requires `floors` to be non-empty and says nothing about where its content came from, and a profile written by hand can carry a floor nobody agreed to.

### 8.4 Role roster derivation

**Two directories have fixed meanings and must not be assigned carelessly.** `docs/adr/**` is
deliberately owned by `architect` in every generated roster, which is why `/new-adr` is an
Orchestrator-or-`architect` skill — no other role can file one, including the veto role whose own §6
requires an ADR to weaken a floor. `docs/gates/**` must be left **unowned**: `/gate-check` has the veto
role write `floors.md` there while the Orchestrator writes `summary.md`, and the per-role guard (§6.4)
permits that only because an unowned path crosses nobody's boundary. A roster that claimed
`docs/gates/**` for one role would block the veto role from authoring its own verdict — the one thing
decision 4 kept a separate file for — and `critical` is not the answer either: the veto role must write
there, but so must the Orchestrator. Neither path is a `spine` key, so neither is configurable — the
skills and the templates both hardcode them, and they agree.

**Test paths need deliberate ownership.** The per-role guard (§6.4) blocks a role from writing a path
another role owns, so giving one role a broad `tests/**` prevents every other role from writing tests
— while the kit mandates test-first for logic. Either give each role the test subtree for its own
code, or leave test paths unowned. Do not give one role the whole tree unless tests really are that
role's exclusive job.

**Ceiling: eight roles** (decided 2026-10-02, decision 3). §8.4's derivation rule produced twelve on a
real repository. The cost of a role is not context — a subagent loads only its own card, ~2.3 KB — it is
coordination: another boundary, another handoff, another row in every ownership table, and one more way
for a task to land on someone who cannot write the path it needs. Above eight, fold domain roles into
the nearest of `architect` / `backend` / `frontend` / `data` / `devops` unless they genuinely own
distinct trees. `services_layout` sits at exactly eight and is the intended upper shape, not a warning.

The number is the weaker half of the rule. The stronger half: **a role must own at least one path and,
once the task graph is expanded past M0, must hold at least one task.** `kitgen.advise()` reports both,
plus the ceiling, as **advice on stderr that never changes the exit code** — §7.1b's codes are an
interface M2 branches on, and a questionable roster is not "nothing was written". The no-task check is
deliberately silent until the graph is expanded: the generated M0 table assigns work to `architect`,
`devops`, `qa` and the veto role only, so at install every domain role correctly has none, and advice
nobody can act on is advice nobody reads.

Always present: `architect`, `devops`, `qa`, and a veto role named `safety`. Added when detected:
`data` (migrations or ORM present), `frontend` (a JS/TS application directory). Domain roles are
proposed one per top-level source directory — which is how `adapters`/`llm`/`resume`/`apply-browser`
and `ml-services`/`image-voice` arose in the two existing orchestrator kits. The user confirms,
renames, merges or drops. Ownership globs are generated from the directories and must partition.

## 9. Verification and testing

### 9.1 Cross-reference verifier (`kitgen.verify`)

Runs against a rendered manifest, before anything is written:

- CLAUDE.md agent table rows == `.claude/agents/*.md` files == `kit.yaml roles[].name`.
- `roles[].owns` globs are pairwise non-overlapping. *(Implemented in `KitConfig.validate()`, not in
  `verify()`: a profile that overlaps never renders.)*
- **M2.** On brownfield, every **detected source directory** is owned by exactly one role. Detected
  source directories exclude anything matched by `.gitignore`, plus `node_modules/`, `data/`, `.venv/`,
  build and cache directories: a tree can hold directories no role should own, and requiring coverage
  of those would make the check unsatisfiable. **Not implemented in M1** (recorded 2026-10-02): it
  needs detection, which means reading the project tree, which `verify()` does only for the presence of
  `spine.inherited` paths. It belongs to the retrofit skill that does the detecting.
- Each role's `handoff_extra` lines appear in **that role's own agent card**. *(Corrected
  2026-10-02: this said "`/handoff`'s role-specific lines == the union of `roles[].handoff_extra`",
  describing a check that cannot exist — `/handoff` is a static skill shipped with the plugin and
  cannot list per-project lines. The card is where they are rendered, and where the subagent reads
  them, so the card is what is checked.)*
- `strategy.md` ownership table == `kit.yaml roles[].owns`.
- `settings.json` deny entries cover every `secrets` path.
- Every `load_order` and `spine` path is either rendered in this manifest or exists on disk.
- Exactly one veto role; `floors` non-empty.
- Every role named as an owner in the strategy §11 task table exists in `roles[]`. The M0 table names
  `architect`, `devops`, `qa` and the veto role, so a profile missing one renders a task assigned to
  nobody.
- The veto role owns at least one path.
- `milestones.outline` is non-empty. `strategy.md` and `plan/README.md` both index `outline[0]`, so an
  empty list surfaces as a Jinja `UndefinedError` rather than a `ConfigError` — the exact failure mode
  §5.2 exists to prevent.
- The role that owns `forge.ci` is the role the CI-wiring task row names.
- Any M0 row that directs a write into "a path `<role>` owns per §2" names a role that owns at least
  one path. Both encode the same lesson: a generated task row instructing a write the assigned role
  cannot make is unexecutable, and it was found twice by rendering rather than by any test.

  An earlier draft of this bullet demanded that every role named in the M0 table own a *test* path.
  That was wrong: `architect` and `devops` own no test path in any of the three fixtures and none of
  them needs one, because each row now routes its write into a path its own role holds. The literal
  check would have failed all three clean renders — the worst outcome for a verifier, since a tool
  that reports phantom problems stops being read. A veto role owning nothing cannot build the floor tier that
  the M0 gate requires — and if every test path belongs to another role, the ownership guard (§6.4)
  blocks that task outright, which is why §11's M0 entry conditions make the tier's home an explicit
  decision rather than an assumption.

### 9.2 Renderer tests

Golden-file tests over three fixtures: a greenfield project with a PRD only; a Python monolith with
migrations; a polyrepo-shaped `services/*` layout. Golden tests assert **structure and
cross-references**, not prose, so template wording can change without churning fixtures. Every
`kit.yaml` constraint in §5 gets a negative test.

### 9.3 Inertness test

A fixture directory with no `.claude/kit.lock.json`: every hook exits 0 and emits nothing; every
process skill declines. (Corrected 2026-10-02: this said `kit.yaml`. The lock is what the code reads,
and the suite tests the lock's absence, an unparseable lock, a zero-byte lock, and a lock that is a
directory.) This guards the whole-machine blast radius of a globally installed plugin.

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
