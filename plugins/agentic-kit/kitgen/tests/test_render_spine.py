# plugins/agentic-kit/kitgen/tests/test_render_spine.py
import re

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def test_strategy_ownership_table_matches_the_roles(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        body = render(cfg)["docs/strategy.md"]
        for r in cfg.roles:
            assert f"`{r.name}`" in body, (name, r.name)
            for p in r.owns:
                assert p in body, (name, p)


def test_strategy_states_every_floor_and_the_veto_holder(load_fixture):
    cfg = load_fixture("services_layout")
    body = render(cfg)["docs/strategy.md"]
    for floor in cfg.floors:
        assert floor in body
    assert cfg.veto_role.name in body


def test_strategy_expands_only_milestone_zero(load_fixture):
    cfg = load_fixture("services_layout")
    body = render(cfg)["docs/strategy.md"]
    assert "M0-S1-" in body
    assert "M1-S1-" not in body
    assert "M1 — Ingest" in body  # later milestones present as outline only


def test_plan_pointer_starts_at_the_first_m0_task(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        body = render(cfg)["docs/plan/README.md"]
        assert re.search(r"Next task\W+.*M0-S1-", body), name
        assert "## Completed" in body


def test_plan_forbids_subagent_edits(load_fixture):
    body = render(load_fixture("greenfield_prd"))["docs/plan/README.md"]
    assert "Subagents never edit this file" in body


def test_design_references_inherited_docs_without_restating(load_fixture):
    cfg = load_fixture("services_layout")
    body = render(cfg)["docs/design.md"]
    for p in cfg.spine["inherited"]:
        assert p in body
    assert "authoritative" in body.lower()


def test_design_has_no_inherited_section_when_none(load_fixture):
    body = render(load_fixture("python_monolith"))["docs/design.md"]
    assert "Inherited documentation" not in body


def test_risk_register_has_a_table_header_and_no_invented_rows(load_fixture):
    body = render(load_fixture("greenfield_prd"))["docs/risk-register.md"]
    assert "| ID | Risk |" in body
    assert "| R-001 |" not in body  # the numbering hint may name R-001; no row may


def test_adr_0001_records_the_install(load_fixture):
    cfg = load_fixture("python_monolith")
    body = render(cfg)["docs/adr/0001-adopt-agentic-kit.md"]
    assert "Accepted" in body
    assert cfg.rendered_on in body
    assert cfg.kit_version in body
    assert cfg.veto_role.name in body


def test_contracts_is_empty_but_structured(load_fixture):
    body = render(load_fixture("greenfield_prd"))["docs/CONTRACTS.md"]
    assert "## Change log" in body


def test_the_observability_rule_is_scoped_to_a_roles_own_paths(load_fixture):
    """Read as "every role instruments the shared observability module", the rule is
    unsatisfiable for any role that does not own that module — most of them on a real
    roster. The remedy is contract-first, not an ownership exemption."""
    cfg = load_fixture("services_layout")
    assert cfg.observability
    man = render(cfg)
    strategy = man[cfg.spine["strategy"]]
    assert "in paths that task's own role holds per §2" in strategy
    assert cfg.spine["contracts"] in strategy
    assert "in paths your own role holds" in man["CLAUDE.md"]


def test_the_observability_text_is_absent_when_the_flag_is_false(load_variant):
    cfg = load_variant("services_layout", observability=False)
    man = render(cfg)
    assert "Not applicable for this project." in man[cfg.spine["strategy"]]
    assert "Observability with the feature" not in man["CLAUDE.md"]
