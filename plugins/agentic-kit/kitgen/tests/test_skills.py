# plugins/agentic-kit/kitgen/tests/test_skills.py
import re
from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[2] / "skills"

EXPECTED = {"next-task", "gate-check", "handoff", "new-adr", "risk",
            "plan-status", "agent-memory", "orchestrating", "kit-doctor",
            "kit-init"}
# Skills the user invokes deliberately; the model must not fire them on its own.
EXPLICIT_ONLY = {"next-task", "gate-check", "kit-init"}


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


# `kit-init` is the one skill that runs where there is NO lock — it creates one — so the
# inertness rule applies to it inverted, and it is the one skill that must name the
# forges, because reading the forge off the git remote is its job. §6.3's rule is that
# nothing *assumes* a forge, not that no file names one.
INSTALLERS = {"kit-init"}


@pytest.mark.parametrize("name", sorted(EXPECTED - INSTALLERS))
def test_every_skill_reads_the_lock_and_declines_without_it(name):
    body = (SKILLS / name / "SKILL.md").read_text()
    assert ".claude/kit.lock.json" in body, name
    assert "decline" in body.lower() or "not a kit project" in body.lower(), name


@pytest.mark.parametrize("name", sorted(INSTALLERS))
def test_an_installer_skill_stops_when_a_lock_already_exists(name):
    """The inverse of the rule, and it matters more: reinstalling over a live kit would
    re-interview the user and re-render a project that already has accumulated work."""
    body = (SKILLS / name / "SKILL.md").read_text()
    collapsed = " ".join(body.split())
    assert ".claude/kit.lock.json" in body, name
    assert "If it exists, stop" in collapsed, name
    assert "Do not reinstall over a live kit" in collapsed, name


@pytest.mark.parametrize("name", sorted(INSTALLERS))
def test_an_installer_skill_handles_every_forge_kind(name):
    body = (SKILLS / name / "SKILL.md").read_text().lower()
    for kind in ("gitlab", "github", "glab", "gh"):
        assert kind in body, f"{name}: detection must cover {kind}"
    assert "no remote means `kind: none`" in body, (
        f"{name}: a project with no remote is the case most easily forgotten")


@pytest.mark.parametrize("name", sorted(EXPECTED - INSTALLERS))
def test_no_skill_hardcodes_a_spine_path_or_a_forge(name):
    body = (SKILLS / name / "SKILL.md").read_text()
    assert "docs/strategy.md" not in body, f"{name}: read spine.strategy from the lock"
    assert "docs/plan/README.md" not in body, f"{name}: read spine.plan from the lock"
    for forge in ("gitlab", "github", "glab", " gh "):
        assert forge not in body.lower(), f"{name}: mentions {forge!r}; stay forge-neutral"


def test_handoff_scopes_the_contracts_rule_to_another_role():
    """`/handoff` used to say "if you do not own `spine.contracts`, do not edit it
    ... ask the architect". No role owns it in any generated roster, so the first
    task of every install told `architect` to request the file from itself and mark
    itself PARTIAL. The guard's actual rule is "blocked only when ANOTHER role owns
    it", and the skill must say the same thing."""
    text = (SKILLS / "handoff/SKILL.md").read_text()
    assert "another\nrole** owns `spine.contracts`" in text or \
           "another role** owns `spine.contracts`" in text
    assert "If you do\nnot own `spine.contracts`" not in text
    assert "no role** owns" in text, "the unowned case must be spelled out"


def test_gate_check_writes_two_files_and_does_not_author_the_floors_verdict():
    """Decision 4: the five dimensions are the discipline and stay; the five-file
    bundle was ceremony, and `summary.md` restated the other four. Floors keeps its
    own file because it can BLOCK — a verdict the veto role writes itself cannot be
    softened in synthesis, so the skill must not let the Orchestrator edit it."""
    raw = (SKILLS / "gate-check/SKILL.md").read_text()
    # Collapsed whitespace: these are prose assertions and the file is hard-wrapped,
    # so a phrase can legitimately straddle a line break.
    text = " ".join(raw.split())
    assert "Two files, not five" in text
    assert "floors.md" in text and "summary.md" in text
    for gone in ("functional.md", "tests.md", "operational.md"):
        assert gone not in text, f"{gone} should no longer be a separate file"
    for heading in ("## Functional", "## Tests", "## Operational",
                    "## Milestone additions", "## Verdict", "## Floors"):
        assert heading in raw, heading
    assert "you do not edit that file" in text
    assert "not yours to summarise" in text


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_no_skill_hardcodes_a_spine_path(name):
    """Spine paths are configurable for every skill, installers included: `kit-init`
    describes the documents by their profile key, not by where they usually land."""
    body = (SKILLS / name / "SKILL.md").read_text()
    assert "docs/strategy.md" not in body, f"{name}: say spine.strategy"
    assert "docs/plan/README.md" not in body, f"{name}: say spine.plan"


def test_kit_init_insists_on_merge_for_an_existing_project():
    """Without `--merge` the render refuses rather than destroying a curated CLAUDE.md or
    settings.json — safe, but a dead end. The skill has to know that `--merge` is the
    answer and not a workaround, because a user who is told only "it refused" will reach
    for `--force`."""
    text = " ".join((SKILLS / "kit-init/SKILL.md").read_text().split())
    assert "you MUST pass `--merge`" in text
    assert "Project-specific notes" in text
    assert "unioned" in text and "never replaced" in text
    assert "--force" in text and "not a workaround" in text


def test_kit_init_does_not_delegate_the_roster_to_a_subagent():
    """The roster and the ownership map are the user's decisions, and a subagent cannot
    answer for them."""
    text = " ".join((SKILLS / "kit-init/SKILL.md").read_text().split())
    assert "Never dispatch a subagent" in text
    assert "AskUserQuestion" in text
