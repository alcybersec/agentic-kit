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


def test_spine_path_the_renderer_does_not_produce_is_reported(load_fixture, tmp_path):
    """render() hardcodes docs/design.md; a profile pointing elsewhere is only
    caught here."""
    def edit(l):
        l["spine"]["design"] = "docs/elsewhere.md"
    cfg = _variant(load_fixture("python_monolith"), edit)
    problems = verify(render(cfg), cfg, project_root=tmp_path)
    assert any("spine.design" in p and "docs/elsewhere.md" in p for p in problems)


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
