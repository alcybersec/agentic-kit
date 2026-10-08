import json

import pytest

from kitgen.model import KitConfig
from kitgen.render import render
from kitgen.verify import verify

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def _variant(cfg, edit):
    """A valid profile derived from cfg: edit(lock_dict) then re-validate."""
    lock = cfg.to_lock()
    edit(lock)
    return KitConfig.from_dict(lock)


def _role(lock, name):
    return next(r for r in lock["roles"] if r["name"] == name)


def test_freshly_rendered_manifests_verify_clean(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        assert verify(render(cfg), cfg) == [], name


def test_clean_with_a_project_root_holding_the_inherited_files(load_fixture, tmp_path):
    for name in FIXTURES:
        cfg = load_fixture(name)
        for p in cfg.spine["inherited"]:
            (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / p).write_text("x")
        assert verify(render(cfg), cfg, project_root=tmp_path) == [], name


def test_an_m0_owner_absent_from_the_roster_is_reported(load_fixture):
    """The M0 task table names architect, devops, qa and the veto role. A profile
    without one of them renders a task assigned to a role that does not exist."""
    cfg = load_fixture("greenfield_prd")
    man = render(cfg)
    man[cfg.spine["strategy"]] = man[cfg.spine["strategy"]].replace(
        "| `devops` |", "| `platform` |")
    assert any("devops" in p for p in verify(man, cfg))


def test_profile_without_devops_is_reported(load_fixture):
    cfg = _variant(load_fixture("python_monolith"),
                   lambda l: l.update(roles=[r for r in l["roles"]
                                             if r["name"] != "devops"]))
    problems = verify(render(cfg), cfg)
    assert any("'devops'" in p and "assigned to nobody" in p for p in problems)


def test_an_m0_task_assigned_to_an_unknown_role_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = cfg.spine["strategy"]
    man[s] = man[s].replace("-S1-QA-004 | `qa` |", "-S1-QA-004 | `ghost` |")
    assert any("'ghost'" in p and "not in roles[]" in p for p in verify(man, cfg))


def test_a_veto_role_owning_no_path_is_reported(load_fixture):
    cfg = _variant(load_fixture("python_monolith"),
                   lambda l: _role(l, "safety").update(owns=[]))
    assert any("veto" in p.lower() and "owns no path" in p
               for p in verify(render(cfg), cfg))


def test_architect_owning_no_path_is_reported(load_fixture):
    """The ARCH row says 'a path architect owns per §2'; with no owned path it
    is unexecutable."""
    cfg = _variant(load_fixture("python_monolith"),
                   lambda l: _role(l, "architect").update(owns=[]))
    assert any("'architect'" in p and "owns no path" in p
               for p in verify(render(cfg), cfg))


def test_ci_owned_by_a_role_other_than_the_ci_wiring_row_is_reported(load_fixture):
    def edit(l):
        _role(l, "devops")["owns"] = ["docker/**"]
        _role(l, "architect")["owns"].append(".github/workflows/**")
    cfg = _variant(load_fixture("python_monolith"), edit)
    problems = verify(render(cfg), cfg)
    assert any(".github/workflows" in p and "architect" in p and "devops" in p
               for p in problems)


def test_missing_ci_wiring_row_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = cfg.spine["strategy"]
    man[s] = man[s].replace("wired into `.github/workflows`", "wired into CI")
    assert any("CI-wiring" in p for p in verify(man, cfg))


def test_no_ci_row_is_expected_when_there_is_no_forge(load_fixture):
    cfg = load_fixture("greenfield_prd")
    assert verify(render(cfg), cfg) == []


def test_a_forge_none_profile_carrying_a_ci_value_is_rejected_outright(load_fixture):
    from kitgen.model import ConfigError

    def edit(l):
        l["forge"]["ci"] = ".github/workflows"
    with pytest.raises(ConfigError, match="forge.ci"):
        _variant(load_fixture("greenfield_prd"), edit)


def test_missing_role_card_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    del man[".claude/agents/architect.md"]  # no handoff_extra: only this check fires
    assert verify(man, cfg) == [
        "role 'architect': no .claude/agents/architect.md in the manifest"]


def test_missing_role_memory_file_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    del man[".claude/agent-memory/data/MEMORY.md"]
    assert verify(man, cfg) == [
        "role 'data': no .claude/agent-memory/data/MEMORY.md in the manifest"]


def test_stray_agent_card_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    man[".claude/agents/ghost.md"] = "x"
    assert any("'ghost'" in p for p in verify(man, cfg))


def test_role_absent_from_the_claude_md_table_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    man["CLAUDE.md"] = man["CLAUDE.md"].replace("| `data` |", "| `dta` |")
    problems = verify(man, cfg)
    assert any("CLAUDE.md" in p and "'data'" in p for p in problems)
    assert any("CLAUDE.md" in p and "'dta'" in p for p in problems)


def test_kit_yaml_roles_disagreeing_with_the_config_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    man[".claude/kit.yaml"] = man[".claude/kit.yaml"].replace(
        "name: backend", "name: backendd")
    assert any("kit.yaml" in p and "roles" in p for p in verify(man, cfg))


def test_strategy_ownership_glob_mismatch_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = cfg.spine["strategy"]
    man[s] = man[s].replace("`alembic/**`", "`alembic2/**`")
    assert any("'data'" in p and "alembic" in p for p in verify(man, cfg))


def test_handoff_extra_missing_from_a_role_card_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    man[".claude/agents/data.md"] = man[".claude/agents/data.md"].replace(
        "MIGRATION:", "MIGRATIONS:")
    assert any("MIGRATION:" in p for p in verify(man, cfg))


def test_handoff_extra_missing_from_the_strategy_table_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = cfg.spine["strategy"]
    man[s] = man[s].replace("`MIGRATION:`", "`OTHER:`")
    assert any("handoff extras" in p and "'data'" in p for p in verify(man, cfg))


@pytest.mark.parametrize("verb", ["Read", "Edit"])
def test_secret_not_denied_for_one_verb_is_reported(load_fixture, verb):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = json.loads(man[".claude/settings.json"])
    s["permissions"]["deny"].remove(f"{verb}(./.env)")
    man[".claude/settings.json"] = json.dumps(s)
    assert verify(man, cfg) == [
        f".claude/settings.json: secret './.env' is not denied for {verb}"]


def test_strategy_listing_a_role_not_in_the_roster_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = cfg.spine["strategy"]
    man[s] = man[s].replace("| `data` |", "| `dta` |", 1)
    assert "docs/strategy.md §2 lists role 'dta', which is not in roles[]" in verify(man, cfg)


def test_m0_table_assigning_nothing_to_a_required_role_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = cfg.spine["strategy"]
    man[s] = "\n".join(l for l in man[s].splitlines()
                       if not ("-S1-QA-" in l and l.startswith("|")))
    assert "docs/strategy.md §11: the M0 table assigns no task to 'qa'" in verify(man, cfg)


def test_missing_m0_rows_are_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = cfg.spine["strategy"]
    man[s] = "\n".join(l for l in man[s].splitlines() if "-S1-" not in l)
    assert "docs/strategy.md §11: no M0 task rows found" in verify(man, cfg)


def test_non_inherited_spine_path_missing_from_the_manifest_is_reported_without_a_root(
        load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    del man["docs/design.md"]
    assert verify(man, cfg) == [
        "spine.design path 'docs/design.md' is neither rendered nor present on disk",
        "load_order path 'docs/design.md' is neither rendered nor on disk"]


def test_inherited_path_missing_everywhere_is_not_reported_without_a_root(load_fixture):
    cfg = load_fixture("services_layout")
    assert "docs/PRD.md" not in render(cfg)
    assert verify(render(cfg), cfg, project_root=None) == []


def test_spine_path_neither_rendered_nor_on_disk_is_reported(load_fixture, tmp_path):
    cfg = load_fixture("services_layout")
    problems = verify(render(cfg), cfg, project_root=tmp_path)
    assert any("docs/PRD.md" in p for p in problems)


def test_a_relocated_spine_document_is_rendered_there_and_verifies(load_fixture, tmp_path):
    """This test used to assert the opposite, because `render()` hardcoded the spine paths
    while §5 offered them as configuration — so pointing `spine.design` elsewhere produced
    `docs/design.md` and a verification error. Since 2026-10-03 the renderer emits at the
    configured path, and the check's remaining job is `spine.inherited`, which is never
    rendered by anyone."""
    def edit(l):
        l["spine"]["design"] = "docs/elsewhere.md"
        l["load_order"] = [{"path": l["spine"]["plan"], "mode": "full"}]
    cfg = _variant(load_fixture("python_monolith"), edit)
    man = render(cfg)
    assert "docs/elsewhere.md" in man and "docs/design.md" not in man
    assert verify(man, cfg, project_root=tmp_path) == []


def test_an_inherited_path_absent_from_disk_is_still_reported(load_fixture, tmp_path):
    """What that check is actually for: a document the profile calls authoritative and
    that nothing renders, so only the disk can confirm it."""
    def edit(l):
        l["spine"]["inherited"] = ["docs/PRD.md"]
    cfg = _variant(load_fixture("python_monolith"), edit)
    problems = verify(render(cfg), cfg, project_root=tmp_path)
    assert any("spine.inherited" in p and "docs/PRD.md" in p for p in problems), problems


def test_without_a_project_root_the_disk_checks_are_skipped(load_fixture):
    cfg = load_fixture("services_layout")  # inherits docs not in the manifest
    assert verify(render(cfg), cfg) == []


def test_load_order_path_neither_rendered_nor_on_disk_is_reported(load_fixture, tmp_path):
    def edit(l):
        l["load_order"].append({"path": "docs/nowhere.md", "mode": "full"})
    cfg = _variant(load_fixture("python_monolith"), edit)
    problems = verify(render(cfg), cfg, project_root=tmp_path)
    assert any("load_order" in p and "docs/nowhere.md" in p for p in problems)


def test_inherited_path_present_on_disk_is_accepted(load_fixture, tmp_path):
    cfg = load_fixture("services_layout")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/PRD.md").write_text("prd")
    (tmp_path / "docs/architecture.md").write_text("arch")
    assert verify(render(cfg), cfg, project_root=tmp_path) == []


def test_lock_disagreeing_with_the_config_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    lock = json.loads(man[".claude/kit.lock.json"])
    lock["project"]["slug"] = "tampered"
    man[".claude/kit.lock.json"] = json.dumps(lock)
    assert any("kit.lock.json" in p for p in verify(man, cfg))


# --- the first task of every install must be completable ---------------------

def test_contracts_owned_by_another_role_than_the_m0_task_is_reported(load_fixture):
    """`M0-S1-ARCH-001` writes `spine.contracts`. If a role other than the one the
    task is assigned to owns that path, the ownership guard blocks the assigned
    role, `/handoff` tells it to request the file from the owner, and the task can
    only ever be PARTIAL. That is a deadlock on move one, so it is a verify error
    rather than something to discover during M0."""
    cfg = load_fixture("python_monolith")

    def give_contracts_to_qa(lock):
        _role(lock, "qa")["owns"].append(lock["spine"]["contracts"])

    cfg2 = _variant(cfg, give_contracts_to_qa)
    problems = verify(render(cfg2), cfg2)
    assert any("cannot be completed" in p and "qa" in p for p in problems), problems


def test_contracts_owned_by_the_assigned_role_is_fine(load_fixture):
    """The other direction: the task's own owner holding the path is not a
    deadlock, so folding `spine.contracts` into `architect.owns` stays an option."""
    cfg = load_fixture("python_monolith")

    def give_contracts_to_architect(lock):
        _role(lock, "architect")["owns"].append(lock["spine"]["contracts"])

    cfg2 = _variant(cfg, give_contracts_to_architect)
    assert verify(render(cfg2), cfg2) == []


def test_contracts_unowned_is_the_intended_state(load_fixture):
    """Every shipped fixture leaves it unowned, and that must stay clean: the guard
    blocks a path only when another role owns it."""
    for name in FIXTURES:
        cfg = load_fixture(name)
        contracts = cfg.spine["contracts"]
        assert not any(contracts in r.owns for r in cfg.roles), name
        assert verify(render(cfg), cfg) == [], name


# --- fix 2.1: every structural failure must be LOUD, and say which one --------
#
# verify()'s whole job is to refuse before anything is written, so a check that
# passes vacuously is worse than no check. Thirteen of its lines had never been
# executed by any test, all of them the "I could not even find this" branches:
# a missing document, a garbled one, a renamed heading. Each case below damages
# the manifest in one specific way and asserts the EXACT message, because a
# `len(problems) > 0` assertion would be satisfied by any complaint at all --
# including one about something else entirely.

def _man(load_fixture, fixture="services_layout"):
    cfg = load_fixture(fixture)
    return render(cfg), cfg


def _drop_heading(text, heading):
    """Rename a heading in place, keeping the body: the section becomes
    unfindable without the file shrinking, which is what a template edit does."""
    return text.replace(heading, heading.replace("## ", "## x"), 1)


LOUD = [
    # (label, damage(manifest, cfg), expected substring)
    ("CLAUDE.md deleted",
     lambda m, c: m.pop("CLAUDE.md"),
     "CLAUDE.md: agent table (header '| Agent | Owns |') not found"),
    ("CLAUDE.md agent table heading renamed",
     lambda m, c: m.__setitem__("CLAUDE.md",
                                m["CLAUDE.md"].replace("| Agent | Owns |", "| Role | Paths |")),
     "CLAUDE.md: agent table (header '| Agent | Owns |') not found"),
    ("kit.yaml replaced with a scalar",
     lambda m, c: m.__setitem__(".claude/kit.yaml", "just a string\n"),
     ".claude/kit.yaml is not usable"),
    ("kit.yaml is not parseable YAML",
     lambda m, c: m.__setitem__(".claude/kit.yaml", "roles: [unclosed\n"),
     ".claude/kit.yaml is not usable"),
    ("kit.yaml lost its roles key",
     lambda m, c: m.__setitem__(".claude/kit.yaml", "project: {name: x}\n"),
     ".claude/kit.yaml is not usable"),
    ("settings.json is not JSON",
     lambda m, c: m.__setitem__(".claude/settings.json", "{not json"),
     ".claude/settings.json is not usable"),
    ("settings.json lost its permissions key",
     lambda m, c: m.__setitem__(".claude/settings.json", '{"env": {}}'),
     ".claude/settings.json is not usable"),
    ("kit.lock.json is not JSON",
     lambda m, c: m.__setitem__(".claude/kit.lock.json", "{not json"),
     ".claude/kit.lock.json is not usable"),
    ("kit.lock.json no longer matches the config",
     lambda m, c: m.__setitem__(".claude/kit.lock.json", '{"roles": []}'),
     ".claude/kit.lock.json does not match the config it came from"),
    ("strategy.md deleted",
     lambda m, c: m.pop(c.spine["strategy"]),
     "§2 ownership map not found"),
    ("strategy §2 heading renamed",
     lambda m, c: m.__setitem__(c.spine["strategy"],
                                _drop_heading(m[c.spine["strategy"]], "## 2.")),
     "§2 ownership map not found"),
    ("strategy §11 heading renamed",
     lambda m, c: m.__setitem__(c.spine["strategy"],
                                _drop_heading(m[c.spine["strategy"]], "## 11.")),
     "§11 task graph not found"),
    ("strategy §11 task rows removed",
     lambda m, c: m.__setitem__(
         c.spine["strategy"],
         "\n".join(l for l in m[c.spine["strategy"]].splitlines()
                   if not l.startswith("| M0-S1-")) + "\n"),
     "§11: no M0 task rows found"),
    ("a role card is missing",
     lambda m, c: m.pop(f".claude/agents/{c.roles[0].name}.md"),
     "no .claude/agents/"),
    ("a role's memory file is missing",
     lambda m, c: m.pop(f".claude/agent-memory/{c.roles[0].name}/MEMORY.md"),
     "/MEMORY.md in the manifest"),
    ("a rendered spine document is missing",
     lambda m, c: m.pop(c.spine["design"]),
     "is neither rendered nor present on disk"),
    ("a load_order document is missing",
     lambda m, c: m.pop(c.load_order[0]["path"]),
     "is neither rendered nor"),
]


@pytest.mark.parametrize("label,damage,expected",
                         LOUD, ids=[c[0] for c in LOUD])
def test_a_damaged_manifest_fails_with_the_right_message(load_fixture, label,
                                                         damage, expected):
    man, cfg = _man(load_fixture)
    assert verify(man, cfg) == [], "the fixture must start clean"
    damage(man, cfg)
    problems = verify(man, cfg)
    assert any(expected in p for p in problems), (label, expected, problems)


def test_an_extra_agent_card_with_no_role_is_reported(load_fixture):
    man, cfg = _man(load_fixture)
    man[".claude/agents/ghost.md"] = "# ghost\n"
    assert any("agent card 'ghost' has no matching role" in p
               for p in verify(man, cfg))


def test_an_extra_row_in_the_claude_md_table_is_reported(load_fixture):
    man, cfg = _man(load_fixture)
    first = cfg.roles[0].name
    man["CLAUDE.md"] = man["CLAUDE.md"].replace(
        f"| `{first}` |", f"| `phantom` | `x/**` | - |\n| `{first}` |", 1)
    assert any("lists 'phantom', which is not in roles[]" in p
               for p in verify(man, cfg))


def test_a_handoff_extra_missing_from_the_card_is_reported(load_fixture):
    man, cfg = _man(load_fixture)
    role = next(r for r in cfg.roles if r.handoff_extra)
    card = f".claude/agents/{role.name}.md"
    man[card] = man[card].replace(role.handoff_extra[0], "REMOVED:")
    assert any(f"handoff line {role.handoff_extra[0]!r} missing" in p
               for p in verify(man, cfg))


def test_an_extra_role_row_in_strategy_2_is_reported(load_fixture):
    man, cfg = _man(load_fixture)
    sp = cfg.spine["strategy"]
    first = cfg.roles[0].name
    man[sp] = man[sp].replace(f"| `{first}` |",
                              f"| `phantom` | `x/**` | - |\n| `{first}` |", 1)
    assert any("§2 lists role 'phantom', which is not in roles[]" in p
               for p in verify(man, cfg))


def test_an_inherited_doc_in_load_order_is_not_demanded_without_a_root(load_variant):
    """A brownfield profile may put the PRD in `load_order`. It is never rendered,
    so with no `project_root` there is no way to look for it — and demanding it
    would make every clean render verify dirty."""
    cfg = load_variant(
        "services_layout",
        load_order=[{"path": "docs/plan/README.md", "mode": "full"},
                    {"path": "docs/PRD.md", "mode": "full"}])
    assert "docs/PRD.md" in cfg.spine["inherited"]
    assert verify(render(cfg), cfg) == []


def test_the_same_inherited_doc_is_demanded_when_a_root_is_given(load_variant, tmp_path):
    """With a root, absence is a fact rather than an unknown."""
    cfg = load_variant(
        "services_layout",
        load_order=[{"path": "docs/plan/README.md", "mode": "full"},
                    {"path": "docs/PRD.md", "mode": "full"}])
    problems = verify(render(cfg), cfg, project_root=tmp_path)
    assert any("docs/PRD.md" in p for p in problems), problems


def test_a_table_row_without_a_backticked_name_is_not_read_as_a_role(load_fixture):
    """The row parser takes the backticked name from the first cell. A row that has
    none is not a role row, and must not be silently accepted as one — otherwise a
    reformatted table would let a missing role through."""
    man, cfg = _man(load_fixture)
    first = cfg.roles[0].name
    man["CLAUDE.md"] = man["CLAUDE.md"].replace(f"| `{first}` |", f"| {first} |", 1)
    assert any(f"role {first!r}: absent from the CLAUDE.md agent table" in p
               for p in verify(man, cfg))


def test_the_agent_table_is_read_when_it_is_the_last_thing_in_the_file(load_fixture):
    """The row loop normally stops at the first line that is not a table row. When
    the table runs to the end of the file it has to stop by exhausting the lines
    instead — the case a truncated template produces, and the one branch of this
    loop no other test reached. The roles must still be read, so that a truncated
    CLAUDE.md is reported for what it is missing and not for a role it does list."""
    man, cfg = _man(load_fixture)
    lines = man["CLAUDE.md"].splitlines()
    last_row = max(i for i, l in enumerate(lines) if l.startswith("| `"))
    man["CLAUDE.md"] = "\n".join(lines[:last_row + 1]) + "\n"
    problems = verify(man, cfg)
    assert not any("agent table" in p for p in problems), problems
    assert not any("absent from the CLAUDE.md agent table" in p for p in problems), problems


# --- fix 2.2: _covers, the other half of the path logic -----------------------
#
# A different question from _overlaps: not "may these two globs collide" but
# "does this glob claim this one literal path". It decides which role owns
# `forge.ci` and `spine.contracts`, so a wrong answer reassigns a task.

COVERS = [
    # (glob, path, covers, why)
    (".github/workflows/**", ".github/workflows/ci.yml", True, "a file in the tree"),
    (".github/workflows", ".github/workflows/ci.yml", True,
     "a directory claim covers what is under it"),
    (".github/workflows/ci.yml", ".github/workflows/ci.yml", True, "exact literal"),
    ("docs/**", "docs/CONTRACTS.md", True, "a file in the tree"),
    ("src/**", "docs/CONTRACTS.md", False, "a different tree"),
    (".gitlab-ci.yml", ".github/workflows/ci.yml", False, "a different file"),
    ("docs/adr/**", "docs", True,
     "the path is a PARENT of the claim: writing docs/ touches the claimed tree"),
    ("**/*.yml", ".github/workflows/ci.yml", True,
     "a wild first segment has no prefix, and fnmatch decides"),
    ("docs/a*/**", "docs/adr/0001.md", True, "mid-segment wildcard, via the prefix"),
    ("docs/ab/**", "docs/a", False, "a string prefix that is not a path prefix"),
]


@pytest.mark.parametrize("glob,path,expected,why", COVERS,
                         ids=[f"{c[0]}|{c[1]}" for c in COVERS])
def test_covers_truth_table(glob, path, expected, why):
    from kitgen.verify import _covers
    assert _covers(glob, path) is expected, why


# --- advisories: valid, but probably wrong (decision 3) -----------------------

def test_the_shipped_fixtures_draw_no_advice(load_fixture):
    """Including services_layout at exactly eight roles — the ceiling is inclusive,
    and a reference roster must not scold the person copying it."""
    from kitgen.verify import advise
    for name in FIXTURES:
        cfg = load_fixture(name)
        assert advise(render(cfg), cfg) == [], name


def test_a_roster_above_the_ceiling_is_flagged(load_variant):
    from kitgen.verify import ROLE_CEILING, advise
    cfg = load_variant("services_layout")
    extra = [
        {"name": f"domain{i}", "description": f"Domain {i}.",
         "owns": [f"services/domain{i}/**"], "handoff_extra": [], "veto": False}
        for i in range(3)
    ]
    lock = cfg.to_lock()
    lock["roles"] = lock["roles"] + extra
    cfg2 = KitConfig.from_dict(lock)
    assert len(cfg2.roles) == ROLE_CEILING + 3
    msgs = advise(render(cfg2), cfg2)
    assert any(f"above the {ROLE_CEILING}" in m for m in msgs), msgs
    assert any("Fold domain roles" in m for m in msgs)


def test_a_role_owning_no_path_is_flagged(load_fixture):
    from kitgen.verify import advise
    cfg = _variant(load_fixture("python_monolith"),
                   lambda lock: _role(lock, "architect").__setitem__("owns", []))
    assert any("owns no path" in m and "architect" in m for m in advise(render(cfg), cfg))


def test_no_task_row_is_not_flagged_before_the_graph_is_expanded(load_fixture):
    """The generated M0 table is scaffolding: it assigns tasks to architect, devops,
    qa and the veto role only, so every domain role correctly has none at install.
    Flagging that would fire on all three shipped fixtures — advice nobody can act on
    is advice nobody reads."""
    from kitgen.verify import advise
    cfg = load_fixture("services_layout")
    assert {"backend", "worker", "frontend", "data"} <= {r.name for r in cfg.roles}
    assert advise(render(cfg), cfg) == []


def test_a_role_with_no_task_row_is_flagged_once_the_graph_is_expanded(load_fixture):
    """At the first gate the next milestone is expanded, and from then on a role with
    no task anywhere is paying for a boundary and a handoff it never uses."""
    from kitgen.verify import advise
    cfg = load_fixture("services_layout")
    man = render(cfg)
    sp = cfg.spine["strategy"]
    # What /gate-check does on PASS: expand the next milestone's rows.
    man[sp] += ("\n| M1-S1-BACKEND-010 | `backend` | the ingest endpoint | unit | 2xx |\n"
                "| M1-S1-QA-011 | `qa` | ingest e2e | e2e | green |\n")
    msgs = advise(man, cfg)
    assert any("'worker' is assigned no task anywhere" in m for m in msgs), msgs
    assert any("expanded past M0" in m for m in msgs)
    assert not any("'backend'" in m for m in msgs), "backend now has one"


def test_an_advisory_never_changes_the_exit_code(load_fixture, tmp_path, capsys):
    """§7.1b's codes are an interface M2 branches on. A roster worth a second look is
    not "nothing was written"."""
    import yaml
    from kitgen.cli import main
    cfg = load_fixture("services_layout")
    lock = cfg.to_lock()
    # A DOMAIN role, deliberately: `architect` with no paths is a hard verify error,
    # because an M0 row tells it to write in a path it owns. `worker` appears in no M0
    # row, so an empty `owns` there is exactly the valid-but-questionable case.
    _role(lock, "worker")["owns"] = []
    profile = tmp_path / "p.yaml"
    profile.write_text(yaml.safe_dump(lock))
    for p in cfg.spine["inherited"]:
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("x")
    rc = main(["render", "--profile", str(profile), "--out", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 0, err
    assert "advice: role 'worker' owns no path" in err


# --- M2.4: code nobody owns ---------------------------------------------------

def _tree(root, paths):
    for rel in paths:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")


def test_unowned_code_is_reported_shallowest_first(load_fixture, tmp_path):
    """§9.1 asked for this and nothing implemented it, because it needs the disk. A role
    agent found the gap unaided on the first real retrofit: the event bus, the contracts
    package and the exchange adapters had no owner, and two of that project's three floors
    depended on exactly that code — unenforceable by anyone the ownership map named."""
    from kitgen.verify import unowned_source_dirs
    cfg = load_fixture("python_monolith")      # owns src/ledger/{api,models}, alembic, tests/*
    _tree(tmp_path, [
        "src/ledger/api/routes.py",           # owned
        "src/ledger/models/entry.py",         # owned
        "src/common/bus.py",                  # NOT owned
        "src/common/deep/nested/thing.py",    # under an unowned parent: not reported twice
        "src/contracts/schema.py",            # NOT owned
        "docs/notes.md",                      # no code: not a source directory
        "node_modules/pkg/index.js",          # noise
        ".venv/lib/x.py",                     # noise
    ])
    found = unowned_source_dirs(cfg, tmp_path)
    assert "src/common" in found and "src/contracts" in found
    assert "src/common/deep/nested" not in found, "the shallowest finding is the useful one"
    assert "src/ledger/api" not in found and "src/ledger/models" not in found
    assert "docs" not in found, "documentation is not source"
    assert not any("node_modules" in f or ".venv" in f for f in found)


def test_a_container_of_owned_trees_is_not_itself_a_finding(load_fixture, tmp_path):
    """`src` is unowned in every fixture, and reporting it would bury the real findings
    under the directory that holds them. The first version of this walk used `_covers`,
    which answers "does this glob cover OR LIE INSIDE the path" — so `src` read as *owned*
    and the whole check reported nothing on the project that motivated it."""
    from kitgen.verify import unowned_source_dirs
    cfg = load_fixture("python_monolith")
    _tree(tmp_path, ["src/ledger/api/routes.py", "src/__init__.py"])
    found = unowned_source_dirs(cfg, tmp_path)
    assert "src" not in found
    assert "src/ledger" not in found


def test_an_owned_directory_is_never_reported(load_fixture, tmp_path):
    from kitgen.verify import unowned_source_dirs
    cfg = load_fixture("services_layout")
    _tree(tmp_path, ["services/api/main.py", "services/ui/App.tsx",
                     "services/safety/floor.py", "infra/compose.yaml"])
    assert unowned_source_dirs(cfg, tmp_path) == []


def test_the_advice_says_why_it_matters(load_fixture, tmp_path):
    from kitgen.verify import advise
    cfg = load_fixture("python_monolith")
    _tree(tmp_path, ["src/common/bus.py"])
    msgs = advise(render(cfg), cfg, project_root=tmp_path)
    hit = [m for m in msgs if "src/common" in m]
    assert hit, msgs
    assert "no role owns it" in hit[0]
    assert "a floor depends on" in hit[0], "the consequence, not just the fact"


def test_the_disk_half_is_skipped_without_a_root(load_fixture):
    """Same convention as verify(): with nothing to look at, "no role owns this" cannot be
    told apart from "this directory does not exist"."""
    from kitgen.verify import advise
    cfg = load_fixture("python_monolith")
    assert advise(render(cfg), cfg) == []


def test_an_unarchived_plan_is_reported(load_fixture, tmp_path):
    """`spine.plan` is read `mode: full` at the start of every session, so every stale row
    is charged to every prompt. The archive operation lives in /gate-check; this is what
    makes it enforceable rather than aspirational."""
    from kitgen.verify import PLAN_LINE_BUDGET, advise
    cfg = load_fixture("python_monolith")
    plan = tmp_path / cfg.spine["plan"]
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("\n".join(f"| M0-S1-BACK-{i:03d} | `backend` | done |"
                              for i in range(PLAN_LINE_BUDGET + 50)))
    msgs = advise(render(cfg), cfg, project_root=tmp_path)
    hit = [m for m in msgs if cfg.spine["plan"] in m]
    assert hit, msgs
    assert "mode: full" in hit[0] and "/gate-check archives" in hit[0]


def test_a_fresh_plan_draws_no_advice(load_fixture, tmp_path):
    from kitgen.verify import advise
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    plan = tmp_path / cfg.spine["plan"]
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(man[cfg.spine["plan"]])
    assert advise(man, cfg, project_root=tmp_path) == []


def test_tests_unit_is_not_reported_because_kit_init_prescribes_leaving_it_unowned(
        load_fixture, tmp_path):
    """The check must not advise undoing what the installer instructed.

    `/kit-init` is explicit: "Do not give one role all of `tests/**`: that blocks every
    other role from writing a test while the kit mandates test-first … leave
    `tests/unit/**` unowned." So an unowned `tests/unit` is the prescribed state, and
    reporting it is the kit disagreeing with itself — found on the `study-helper-project`
    retrofit (2026-10-04), where `services/app/tests/unit` was advised against by the
    same tool that told the installer to leave it alone.

    Only `unit` is prescribed. `tests/integration` and `tests/e2e` belong to `qa` and the
    floor tier to the veto role, so those staying unowned IS a real finding and must still
    be reported — the suppression has to be narrow or it hides the cases that matter.
    """
    from kitgen.verify import unowned_source_dirs
    cfg = load_fixture("python_monolith")      # qa owns tests/integration + tests/e2e
    _tree(tmp_path, [
        "tests/unit/test_a.py",                     # prescribed unowned: silent
        "services/app/tests/unit/test_b.py",        # same, not at the root
        "tests/unit/services/test_deep.py",         # inside the prescribed tree: silent
        "services/app/tests/contracts/test_c.py",   # NOT prescribed: a real finding
    ])
    found = unowned_source_dirs(cfg, tmp_path)
    assert "tests/unit" not in found
    assert "services/app/tests/unit" not in found
    assert not any("tests/unit" in f for f in found), found
    assert "services/app/tests/contracts" in found, (
        "only tests/unit is prescribed unowned; everything else must still be reported")
