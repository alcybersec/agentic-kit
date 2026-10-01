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
            assert fm["model"] == "inherit"


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
