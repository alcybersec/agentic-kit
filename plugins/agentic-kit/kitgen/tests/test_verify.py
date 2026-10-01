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
    assert not any("CI" in p for p in verify(render(cfg), cfg))


def test_missing_role_card_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    del man[".claude/agents/data.md"]
    problems = verify(man, cfg)
    assert any("data" in p and "agents/data.md" in p for p in problems)


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


def test_secret_not_denied_in_settings_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = json.loads(man[".claude/settings.json"])
    s["permissions"]["deny"] = [d for d in s["permissions"]["deny"]
                                if "./.env" not in d]
    man[".claude/settings.json"] = json.dumps(s)
    assert any("./.env" in p for p in verify(man, cfg))


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
