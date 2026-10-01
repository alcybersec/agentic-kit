# M1 audit findings and fix plan

**Date** 2026-10-01 · **Branch** `m1-kit` · **State at audit** 489 tests passing, 13/13 templates in
sync, `claude plugin validate` clean, Tasks 1–15 complete, Tasks 16–17 (acceptance, live install) not
started.

**How to use this file.** It is the single source of truth for the post-build audit. Part 2 is the
executable plan; Part 3 is the evidence behind it. Work Phase 0 downward. Every finding carries a
verification status: **[V]** means the controller reproduced it directly in this session, **[R]**
means an auditor reported it and it was not independently re-run.

---

## Part 1 — Verdict and root causes

**The engine is correct; the product is not usable end to end.** Five independent audits agree. The
machinery that was built was built well: the model, renderer, verifier and CLI hold up, the hard-won
findings during the build (the SubagentStop payload, the Read/Edit deny closure, the validator's
blind spot, the matcher limits) all survive re-verification, and `cli.py` is genuinely well pinned at
an 88% mutation kill rate.

What is missing was never in M1's acceptance criteria: **a way in, preservation of existing work, and
enforcement that actually fires.**

Sixty-odd findings collapse to four root causes and two severe one-offs.

### RC1 — `--force` has no concept of "living" content
`GENERATE_ONCE` holds two paths. Five spine documents and every `MEMORY.md` accumulate project
content and are silently overwritten. §7.1a already classifies them as *living*; the code ignores its
own classification. The orphan state is the worst outcome: `docs/adr/0002-*.md` survives on disk while
`decisions.md`'s index is blanked, so the project reads as though nothing was ever recorded. `CLAUDE.md`
instructs the user to re-render after every plugin update.

### RC2 — the hook output contract is wrong, in one shared place
Claude Code reads a hook's decision from **stdout**: *"Your hook's stdout must contain only the JSON
object."* `kit_deny` writes JSON to **stderr**. Blocking therefore works only via `exit 2`, and
*"the blocking message is the reason from your JSON's blocking decision when it makes one, and your
stderr text otherwise"* — so every remediation message in all five guards reaches the agent as a raw
JSON blob. `permissionDecision` is inert, `hookSpecificOutput` is missing its required
`hookEventName`, and SubagentStop needs top-level `decision`/`reason`.

### RC3 — enforcement has three silent off-switches
1. **Workspace trust.** *"Until you trust the folder, the subagent still runs, but Claude Code skips
   its frontmatter hooks"*, and *"a `-p` session doesn't count as trusted."* The ownership guard is
   registered from the project's own `.claude/agents/`, so in an untrusted checkout or any
   non-interactive session it is simply absent — while §6.2 states ownership *is* enforced.
2. **Fail-open.** A missing `jq`, a renamed script, or a deleted guard yields a non-2 exit, which
   Claude Code treats as "show stderr to the user and continue". Inert-by-design and
   inert-because-broken are indistinguishable.
3. **The guard does not protect itself.** `.claude/hooks/**`, `.claude/kit.yaml`,
   `.claude/kit.lock.json` and `spine.inherited` are editable by every role. One `Edit` disarms
   ownership for everyone — the same "self-expansion by the shortest route" argument §6.4 uses to
   refuse `strategy.md`, not followed through.

### RC4 — there is no way in
All eight skills decline without a lock; nothing in M1 creates one; there is no README anywhere; the
install command exists only in a `cli.py` docstring. The three installer skills are M2. Separately,
`M0-S1-ARCH-001` — the first task of every install — is un-completable: nobody owns
`docs/CONTRACTS.md` while `/handoff` forbids writing a file you do not own, so `architect` is told to
request the file from itself.

### One-off A — `post-edit-format` reformats the entire tree on every edit
`timeout 30 $fmt "$path"` appends the edited file to a command assumed target-less. The shipped
`python_monolith` fixture sets `format: "black ."`. Recorded argv: `timeout 30 black . /…/routes.py`.
It writes into every other role's files with no guard in the path (`PostToolUse` is outside the
ownership matcher), dirties peer sessions' uncommitted work — R-013, the incident §6.2 cites as the
reason the hooks exist — and then manufactures the exact condition the role card tells the agent to
halt on.

### One-off B — the suite is 69% load-bearing
258 mutants, 80 real survivors. `verify.py` 57%, `model.py` 56% against `cli.py`'s 88%. Eight tests
*proved* unable to fail. Coverage is 96% line/branch, which is the clearest available demonstration
that coverage is not the question.

---

## Part 2 — Fix plan

### Phase 0 — ship blockers (7)

| # | Fix | Files | Test to add |
|---|---|---|---|
| 0.1 | Reject a `toolchain.format` that carries its own target (last token `.`, `./`, `--all`, or an existing path). A format command must be a prefix taking one file. Fix the `python_monolith` fixture. | `model.py` validate, `tests/fixtures/python_monolith/profile.yaml` | argv assertion with a stub formatter; a negative profile test |
| 0.2 | Correct the hook output contract in **both** copies: print the prose reason to stderr and `exit 2` (simplest), or the full correct object to stdout with `exit 0`. Drop `permissionDecision`/`systemMessage` or replace with `hookEventName` + `permissionDecisionReason`; SubagentStop uses top-level `decision`/`reason`. | `hooks/lib/kitlock.sh` `kit_deny`, `templates/ownership-guard.sh.j2` | assert stderr is prose, not JSON; ~270 hook tests assert on stderr and must be re-checked |
| 0.3 | Add the living documents and `.claude/agent-memory/**` to `GENERATE_ONCE`, or add a third "merge, never clobber" class. Have the CLI list what it is about to overwrite. | `render.py`, `cli.py` | seed each living doc, `--force`, assert content survives |
| 0.4 | Clash check must test **parent directories**, not only manifest paths. Fixes the normative §7.1b violation: `--dry-run --force` returns 0 where the real run returns 4. | `cli.py` | a zero-byte file at `.claude/agents`; assert dry-run == real |
| 0.5 | Guard protects itself: add `.claude/hooks/*`, `.claude/kit.yaml`, `.claude/kit.lock.json`, `.claude/settings.json` to the blanket refusal, and loop `spine.inherited` alongside `strategy`/`risks`. Mirror into `settings.json.j2` deny. | `templates/ownership-guard.sh.j2`, `templates/settings.json.j2` | per-path deny assertions |
| 0.6 | Make `M0-S1-ARCH-001` completable: fold `spine.contracts` into `architect.owns` at resolve time, **or** reword `/handoff` as "if *another role* owns it". Also resolve the acceptance clause that requires the user (I8). | `model.py` or `skills/handoff/SKILL.md`, `templates/strategy.md.j2` | a verify check that `spine.contracts` is owned or explicitly unowned-by-design |
| 0.7 | Exempt `*.example|*.sample|*.template|*.dist` in the secret matcher — `./secrets/**` currently swallows its own template, so the deny message recommends a path it blocks. | `hooks/pre-file-guard.sh` (and the Bash secret scan) | `secrets/prod.yaml.example` must be readable |

### Phase 1 — enforcement integrity (5)

| # | Fix | Notes |
|---|---|---|
| 1.1 | Document the workspace-trust off switch in §6.2's "does NOT guarantee" list and §6.4. | It is the kit's one real enforcement claim |
| 1.2 | Add `/kit-doctor` (or a `plan-status` section) that fires each guard with a known-blocked payload and reports which actually denied. | Closes the fail-open blind spot; also checks workspace trust |
| 1.3 | `pre-bash-guard`'s secret scan must use `kit_candidates`/`kit_match_glob`. It is a third independent matcher: `cat ./sub/../.env` passes while the equivalent `Read` is blocked. | Keep the `cp *.example` exemption on top |
| 1.4 | Narrow `Bash({{ forge.cli }}:*)` to read verbs; add a `pre-bash-guard` branch denying `<cli> (issue\|mr\|pr) (create\|close\|edit\|merge)`. | `CLAUDE.md` requires confirmation for outward-facing actions; settings currently pre-approves them |
| 1.5 | Stop-check must also accept the note from a `SubagentHandback` `tool_input` in the transcript. | Force-granted in auto mode on v2.1.271+, overriding `tools`/`disallowedTools`; the note is then in neither source the hook reads |

### Phase 2 — test suite (3)

| # | Fix | Kills |
|---|---|---|
| 2.1 | Parametrised "loud failure" test for `verify.py`: deleted `CLAUDE.md`, garbled `kit.yaml`, non-JSON `settings.json`/`kit.lock.json`, removed `## 2.`/`## 11.` headings — assert the **exact** message. | 8 survivors, 13 never-executed lines |
| 2.2 | `_overlaps`/`_covers` truth table: identical globs, a-under-b, b-under-a, disjoint siblings, trailing slash, wild first segment. **Two roles can currently declare the identical glob and validate.** | 8 survivors; pins the central invariant |
| 2.3 | Profile-key matrix: delete each of the 16 required keys and mistype each of the 9 shape-checked sections. | 22 survivors |
| 2.4 | Delete the 8 tests proved unable to fail; wire `scripts/check_plan_sync.py` into the suite (nothing runs it today, and a *new* template is silently unchecked). | — |

### Phase 3 — spec corrections (~25, controller does these)

Three false factual claims (F1 secrets depth semantics differ between the hook and the deny rules;
F2 stderr JSON; F3 `SubagentHandback`), two overstatements (§7.1a `--force`, §6.3 "no rule names a
forge"), four unenforced MUSTs to mark M2 (§7.2, §8.3 floors, §9.1 brownfield coverage, §9.1
`/handoff` union), four contradictions (§4.2 vs §5.1 vs §9.3 on the presence marker; §6.2 table vs
§6.2 line 388 on the stop-check source), two swapped cross-references (§6.4/§6.5), plus the minor
list in Part 3.

### Phase 4 — M2 scope

README with the literal install command and a commented example profile; the three installer skills;
§7.2 brownfield preservation; the plan-archive operation (`plan/README.md` is read `mode: full` every
session and grows unbounded); a role-count cap; a workspace-trust check at install.

---

## Part 3 — Findings register

IDs are `<audit><n>`: **A** install coherence, **B** spec vs code, **C** mutation, **D** hook system,
**E** adoption.

### Critical

| ID | Finding | Status |
|---|---|---|
| A-C1 / B-F9 | `--force` destroys living documents and all agent memory; orphans their indexes | **[V]** |
| A-C2 | Nobody owns `docs/CONTRACTS.md`; `/handoff` forbids writing it; `M0-S1-ARCH-001` can only be PARTIAL | **[V]** |
| D-C1 | `post-edit-format` runs `black . <path>` — reformats the whole tree on every edit | **[V]** |
| B-F1 | §5.2's root-anchoring rule is false for the deny rules: the hook is root-anchored, `Read(secrets/**)` matches at any depth | **[R]** |
| B-F2 | "Blocking hooks emit JSON on stderr" is false; stdout is the decision channel | **[V]** |
| B-F3 | "Prefer `last_assistant_message`" is stale: `SubagentHandback` delivers the report through a tool call, auto mode, v2.1.271+ | **[V]** |

### Important

| ID | Finding | Status |
|---|---|---|
| B-F8 | Frontmatter hooks skipped until workspace trust; `-p` never trusted — the ownership guard silently absent | **[V]** |
| D-I1 | Guard does not protect `.claude/hooks/**`, `.claude/kit.yaml`, or `spine.inherited` | **[R]** |
| D-I2 | `./secrets/**` swallows its own `.example`; deny message recommends a blocked path | **[R]** |
| D-I3 | File-guard and ownership guard both deny a secret in another role's tree; the ownership message ("request from X") is wrong and may be the one shown | **[R]** |
| D-I5 | `Bash(<forge.cli>:*)` pre-approves issue/MR create/close that `CLAUDE.md` says needs confirmation | **[R]** |
| D-I8 | `pre-bash-guard` has a third independent path matcher; `cat ./sub/../.env` passes | **[R]** |
| E-A2 | `--dry-run --force` returns 0 where the real run returns 4; violates normative §7.1b; recovery advice is a dead loop | **[V]** |
| E-A3 | The only M1 install path destroys `CLAUDE.md` (6163→5207 B) and replaces curated `settings.json` — exactly what §7.2 forbids | **[R]** |
| E-A6 / C | Ownership is directory-granular, no more-specific-wins: the veto role cannot own `src/common/kill_switch.py` | **[V]** |
| E-A5 | Observability floor unsatisfiable for 8 of 12 roles on a real repo | **[R]** |
| A-I1 | The worktree-isolation rule reaches no reader: orchestrator card never loads, §4 not in `load_order`, `/next-task` is user-only, `orchestrating` unlisted | **[R]** |
| A-I2 | `CLAUDE.md`'s dispatch loop is a lossy copy of `/next-task` (no Active row, no worktree, no re-dispatch-once) | **[R]** |
| A-I3 | §11's task table has no `Depends` column, yet `/next-task` must confirm dependencies | **[R]** |
| A-I4 | §10 says M0 `open` while `plan/README.md` says "Not yet entered" | **[R]** |
| A-I6 | Settings deny `Edit` but not `Write`; guard covers neither `kit.lock.json` nor `settings.json` | **[R]** |
| A-I9 | Role cards never mention branching, yet `strategy.md` mandates `task/<ID>-<slug>` and Completed has a Branch column | **[R]** |
| A-I10 | Role card's Boundaries section under-reports the guard it registers | **[R]** |
| A-I11 | `/risk` is model-invocable and walks a role agent into a guaranteed deny | **[R]** |
| A-I12 | "Request review from `safety`" is impossible: no `Agent` tool, `Agent(orchestrator)` denied, depth 1 | **[R]** |
| B-F4 | Presence marker: §4.2 says `kit.yaml`, §5.1 and all code say `kit.lock.json`, §9.3 says `kit.yaml` | **[R]** |
| B-F5 | §6.2's table says "falling back to"; §6.2 line 388 corrects it to "either source"; code implements the latter | **[R]** |
| B-F6 | §4.4's normative signature `(answers, project_facts)` does not exist | **[R]** |
| B-F7 | §6.2 publishes an attribution regex the hook deliberately does not use | **[R]** |
| B-F10 | §9.1's brownfield coverage check has no code and no M2 caveat | **[R]** |
| B-F11 | §9.1's `/handoff` union bullet describes a check that does not exist | **[R]** |
| C | 80 surviving mutants; `verify.py` 57%, `model.py` 56%; 8 tests proved unable to fail | **[R]** |
| C | Two roles can declare the **identical** `owns` glob and validate | **[R]** |
| C | `check_plan_sync.py` is run by no test and no CI; a *new* template is silently unchecked | **[R]** |
| E-A1 | No README; no way in; install command only in a docstring | **[V]** |
| E-A4 | No safe way to add a role: `--force` deletes the hand-expanded §11 | **[V]** |
| E-A7 | Generated artefacts promise `/kit-upgrade`, which does not exist in M1 | **[R]** |

### Minor (abbreviated — full detail in the audit transcripts)

`A-M1`–`A-M9`, `B-F12`–`B-F15`, `D-M1`–`D-M7`, `E-A8`–`E-A13`. Notable: the whole guard layer fails
open silently (D-M1); `MultiEdit` selects nothing (D-M3, B); `git add -A -- <path>` false positive
(D-M4); stop-check message overstates its own regex (D-M5); `CLAUDE.md`'s agent table header says
`Owns` but holds descriptions (B); `CLAUDE.md` lists six of eight skills (B, A-M4);
`services_layout` ships the `tests/**` anti-pattern §8.4 warns against (B, D-I4); `tests/*.py` cannot
coexist with `tests/<sub>/**` so ~60 loose tests and 39 scripts are ungoverned (E-A9); overlap errors
name an innocent glob (E-A8).

### Open runtime unknowns (Task 17 checklist)

1. **Do plugin `hooks.json` hooks fire for a subagent's tool calls?** If not, `pre-bash-guard` and
   `pre-file-guard` protect only the Orchestrator and role agents have no secret or staging guard.
2. Under `--safe-mode`, settings-file hooks do not run while session hooks do — suggesting the four
   plugin guards go silent while the rendered ownership guard survives. Asymmetric and undocumented.
3. Plugin slash-name resolution: `/handoff` vs `agentic-kit:handoff`.
4. Whether `memory: project` in role frontmatter collides with the kit's `.claude/agent-memory/`.

### Confirmed sound (do not re-litigate)

The inlined matcher is genuinely self-contained and its drift test binds in both directions. No
deny/deny loop across all ten remediations. `post-edit-format` correctly does not run after a blocked
edit. The transcript role/text filter is correct against real JSONL. The SubagentStop payload claims
hold. `check_plan_sync` byte-equality binds both ways. `test_render_module_contract` binds. The three
fixtures genuinely exercise different branches. §6.2a's four validator rows reproduce verbatim.
Nothing from §3's non-goals has crept in.

---

## Part 4 — Open design decisions (owner: Alex)

1. **Directory-granular ownership.** Add more-specific-wins, or accept and document the limit?
2. **Observability vs ownership.** Cross-cutting exemption, or relax "same task" to "same milestone"?
3. **Spine size.** Ship three documents (plan, strategy, risks) instead of six?
4. **Role cap.** §8.4's rule produced 12 roles on a real repo. Cap at ~6?
5. **Gate ceremony.** Five dimension files and three signers who are all the same model — keep, or
   reduce to a checklist? (The 2-milestone carried-condition tally is worth keeping regardless.)

Adoption auditor's recommendation, recorded for the decision: **retrofit the kit into its own
repository as the M2 acceptance test.** The orchestrator model has never run against any real
project, including this one — it was built with the superpowers plan-execution workflow. The parts
that were dogfooded (hooks, the `CLAUDE.md` template, documentation discipline) are the parts that
work; the parts with the most ceremony are the ones never run.

---

## Part 5 — How this was verified, and what it cost

Five read-only audits ran in parallel, each scoped to a dimension nobody had examined, each told to
leave the repository byte-identical and prove it with `git status`. All five did.

| Audit | Dimension | Method | Headline |
|---|---|---|---|
| A | installed-kit coherence | rendered all 3 fixtures, read every generated file, chased every cross-reference, walked `M0-S1-ARCH-001` and the `data` card | 2 Critical, 13 Important |
| B | spec vs implementation | section-by-section against code, docs and the binary | 3 false factual claims, 4 unenforced MUSTs |
| C | test strength | 258 mutants over 4 modules in 4 isolated venvs; `coverage --branch` | 80 survivors, 8 unfireable tests |
| D | the five guards as a system | interaction matrix, remediation-survival check, inertness of the rendered guard | the whole-tree formatter |
| E | adoption | installed into a copy of `321_project`, hand-wrote a profile, drove real tasks | no way in; 12 roles; unsatisfiable floor |

Techniques that found what tests could not, worth reusing:

- **Mutation testing.** 96% coverage with a 69% kill rate. Coverage says a line ran; mutation says a
  test would notice it changing. Three tests in this build were proved unable to fail *at all*.
- **Reading rendered output rather than asserting on it.** The M0 floor-tier bug, the ARCH-001
  deadlock and the `black .` argv all came from looking at the artefact.
- **Asking the harness instead of trusting the plan.** The `agent_transcript_path` bug during the
  build, and `stop_hook_active`, `SubagentHandback` and workspace trust in this audit. Every one was a
  shared false assumption that plan, code and tests agreed on.
- **Driving one component against another.** Every cross-layer defect — guard vs deny rule, skill vs
  spine document, dry-run vs real run — was invisible from inside either side.

Cost note for the record: four of the five audits found at least one defect that originated in a
*safeguard* rather than in the code it guarded (the editable-install check, the fence regex, the
block-index mismatch, the loose `any()` assertions in `test_verify.py`). That is now a pattern worth
naming: a check written by hand, asserting a hand-written index or pattern, is as likely to be wrong
as the thing it checks.
