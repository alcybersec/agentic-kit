# plugins/agentic-kit/kitgen/tests/test_skills.py
import re
from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[2] / "skills"

EXPECTED = {"next-task", "gate-check", "handoff", "new-adr", "risk",
            "plan-status", "agent-memory", "orchestrating"}
# Skills the user invokes deliberately; the model must not fire them on its own.
EXPLICIT_ONLY = {"next-task", "gate-check"}


def frontmatter(path: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.S)
    assert m, f"{path} must open with YAML frontmatter"
    return yaml.safe_load(m.group(1))


def test_exactly_the_expected_skills_are_shipped():
    assert {p.name for p in SKILLS.iterdir() if p.is_dir()} == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_frontmatter_declares_name_and_description(name):
    fm = frontmatter(SKILLS / name / "SKILL.md")
    assert fm["name"] == name
    assert 20 < len(fm["description"]) < 400


@pytest.mark.parametrize("name", sorted(EXPLICIT_ONLY))
def test_dispatch_skills_are_user_invoked_only(name):
    assert frontmatter(SKILLS / name / "SKILL.md")["disable-model-invocation"] is True


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_skill_reads_the_lock_and_declines_without_it(name):
    body = (SKILLS / name / "SKILL.md").read_text()
    assert ".claude/kit.lock.json" in body, name
    assert "decline" in body.lower() or "not a kit project" in body.lower(), name


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_no_skill_hardcodes_a_spine_path_or_a_forge(name):
    body = (SKILLS / name / "SKILL.md").read_text()
    assert "docs/strategy.md" not in body, f"{name}: read spine.strategy from the lock"
    assert "docs/plan/README.md" not in body, f"{name}: read spine.plan from the lock"
    for forge in ("gitlab", "github", "glab", " gh "):
        assert forge not in body.lower(), f"{name}: mentions {forge!r}; stay forge-neutral"
