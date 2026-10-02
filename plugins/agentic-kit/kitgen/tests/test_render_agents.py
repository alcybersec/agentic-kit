# plugins/agentic-kit/kitgen/tests/test_render_agents.py
import re

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def frontmatter(body: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", body, re.S)
    assert m, "role card must open with YAML frontmatter"
    import yaml
    return yaml.safe_load(m.group(1))


def test_every_role_card_declares_its_name_and_description(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        man = render(cfg)
        for r in cfg.roles:
            fm = frontmatter(man[f".claude/agents/{r.name}.md"])
            assert fm["name"] == r.name
            assert fm["description"]
            assert fm["model"] == r.model


def test_role_card_lists_its_owned_paths_and_forbids_others(load_fixture):
    cfg = load_fixture("services_layout")
    man = render(cfg)
    card = man[".claude/agents/backend.md"]
    assert "services/api/**" in card
    assert "Never edit another role's territory" in card
    assert "services/ui/**" in card  # named as another role's territory


def test_role_card_carries_the_atomic_commit_rule(load_fixture):
    cfg = load_fixture("python_monolith")
    for r in cfg.roles:
        card = render(cfg)[f".claude/agents/{r.name}.md"]
        assert "git commit --only" in card
        assert "git add -A" in card


def test_veto_role_card_states_the_veto_and_the_floors(load_fixture):
    cfg = load_fixture("services_layout")
    card = render(cfg)[f".claude/agents/{cfg.veto_role.name}.md"]
    assert "veto" in card.lower()
    for floor in cfg.floors:
        assert floor in card


def test_non_veto_cards_do_not_claim_a_veto(load_fixture):
    cfg = load_fixture("services_layout")
    man = render(cfg)
    for r in cfg.roles:
        if not r.veto:
            assert "veto on gates" not in man[f".claude/agents/{r.name}.md"]


def test_orchestrator_card_forbids_writing_code(load_fixture):
    card = render(load_fixture("greenfield_prd"))[".claude/agents/orchestrator.md"]
    assert "do not write implementation code" in card.lower()


def test_memory_stub_explains_the_linked_index_convention(load_fixture):
    cfg = load_fixture("python_monolith")
    stub = render(cfg)[".claude/agent-memory/data/MEMORY.md"]
    assert "one fact per file" in stub.lower()
    assert "[[" in stub


def test_every_role_card_can_run_the_handoff_skill(load_fixture):
    """strategy.md §9 makes the /handoff note the gate for accepting work."""
    for name in FIXTURES:
        cfg = load_fixture(name)
        man = render(cfg)
        for r in cfg.roles:
            tools = [t.strip() for t in frontmatter(man[f".claude/agents/{r.name}.md"])["tools"].split(",")]
            assert "Skill" in tools, (name, r.name)


def test_each_role_card_declares_its_own_model(load_fixture):
    import re as _re
    for name in ("greenfield_prd", "python_monolith", "services_layout"):
        cfg = load_fixture(name)
        man = render(cfg)
        for r in cfg.roles:
            card = man[f".claude/agents/{r.name}.md"]
            fm = _re.match(r"^---\n(.*?)\n---\n", card, _re.S).group(1)
            assert f"model: {r.model}" in fm, (name, r.name, r.model)


def test_the_orchestrator_always_inherits(load_fixture):
    """It is not dispatched — it *is* the session, so any other value would be a claim
    about what the user should be running."""
    import re as _re
    for name in ("greenfield_prd", "python_monolith", "services_layout"):
        card = render(load_fixture(name))[".claude/agents/orchestrator.md"]
        fm = _re.match(r"^---\n(.*?)\n---\n", card, _re.S).group(1)
        assert _re.search(r"^model: inherit\b", fm, _re.M), name


def test_the_shipped_rosters_put_judgement_roles_on_the_capable_model(load_fixture):
    """These are reference rosters, copied as-is. The split they encode: `architect` and
    the veto role exercise judgement, everyone else works against a contract that
    contract-first required to exist before they were dispatched."""
    for name in ("greenfield_prd", "python_monolith", "services_layout"):
        cfg = load_fixture(name)
        by = {r.name: r.model for r in cfg.roles}
        assert by["architect"] == "opus", name
        assert by[cfg.veto_role.name] == "opus", name
        for other in set(by) - {"architect", cfg.veto_role.name}:
            assert by[other] == "sonnet", (name, other)
        assert "haiku" not in by.values(), (
            f"{name}: nothing is shipped on haiku — the kit has no evidence about how it "
            f"handles the handoff evidence rule or a guard refusal, and a reference "
            f"roster must not guess")
