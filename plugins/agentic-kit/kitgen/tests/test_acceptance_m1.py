# plugins/agentic-kit/kitgen/tests/test_acceptance_m1.py
"""M1 acceptance: every fixture renders, verifies, installs and then behaves.

The other test files each examine one layer. This one walks the whole chain in the
order a project would, because every cross-layer defect in this build was invisible
from inside either side: the renderer was correct and the hook read the wrong field;
the guard was correct and `--force` deleted what it protected.

Two properties here are acceptance criteria rather than unit behaviour, and both were
broken until the post-build audit:

  * the FIRST task of every install must be executable — `M0-S1-ARCH-001` writes
    `spine.contracts`, which no role owns, and `/handoff` used to forbid that;
  * a re-render must not destroy the project's accumulated work.
"""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from kitgen.cli import main
from kitgen.model import KitConfig
from kitgen.render import render
from kitgen.verify import advise, verify

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]
PLUGIN = Path(__file__).resolve().parents[2]


def profile_of(name):
    return FIXTURE_DIR / name / "profile.yaml"


def cfg_of(name):
    return KitConfig.from_dict(yaml.safe_load(profile_of(name).read_text()))


def seed_inherited(root, cfg):
    for p in cfg.spine["inherited"]:
        (root / p).parent.mkdir(parents=True, exist_ok=True)
        (root / p).write_text("inherited placeholder")


def install(root, name, *extra):
    cfg = cfg_of(name)
    seed_inherited(root, cfg)
    rc = main(["render", "--profile", str(profile_of(name)), "--out", str(root), *extra])
    return cfg, rc


def guard(root, role, rel):
    """Fire the ownership guard the way a subagent's Edit does: the plugin's hook, with
    the role carried in the payload's `agent_type`."""
    return subprocess.run(
        ["bash", str(PLUGIN / "hooks/ownership-guard.sh")],
        input=json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": str(root / rel)},
                          "cwd": str(root), "agent_id": "a0", "agent_type": role}),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)})


# --- the chain ----------------------------------------------------------------

@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_renders_verifies_and_writes(name, tmp_path):
    cfg, rc = install(tmp_path, name)
    assert rc == 0
    assert verify(render(cfg), cfg, project_root=tmp_path) == []
    assert advise(render(cfg), cfg) == [], "a shipped fixture must draw no advice"

    lock = json.loads((tmp_path / ".claude/kit.lock.json").read_text())
    assert lock["project"]["slug"] == cfg.project.slug
    assert lock == json.loads(json.dumps(cfg.to_lock()))

    for r in cfg.roles:
        assert (tmp_path / f".claude/agents/{r.name}.md").exists()
        assert (tmp_path / f".claude/agent-memory/{r.name}/MEMORY.md").exists()

    claude_md = (tmp_path / "CLAUDE.md").read_text()
    for r in cfg.roles:
        assert f"`{r.name}`" in claude_md

    for key, value in cfg.spine.items():
        for p in (value if isinstance(value, list) else [value]):
            assert (tmp_path / p).exists(), (key, p)

    assert not (tmp_path / ".claude/hooks").exists(), (
        "nothing is rendered under .claude/hooks any more: the guard is a plugin hook")


@pytest.mark.parametrize("name", FIXTURES)
def test_a_second_render_refuses_and_writes_nothing(name, tmp_path):
    """§7.1b: code 3 guarantees an untouched tree."""
    install(tmp_path, name)
    before = {p: (tmp_path / p).read_text()
              for p in render(cfg_of(name)) if (tmp_path / p).exists()}
    assert main(["render", "--profile", str(profile_of(name)),
                 "--out", str(tmp_path)]) == 3
    assert {p: (tmp_path / p).read_text() for p in before} == before


@pytest.mark.parametrize("name", FIXTURES)
def test_rendered_kit_is_idempotent(name, tmp_path):
    cfg, rc = install(tmp_path, name)
    assert rc == 0
    first = {p: (tmp_path / p).read_text() for p in render(cfg)}
    assert main(["render", "--profile", str(profile_of(name)), "--out", str(tmp_path),
                 "--force"]) == 0
    assert {p: (tmp_path / p).read_text() for p in render(cfg)} == first


@pytest.mark.parametrize("name", FIXTURES)
def test_a_re_render_keeps_the_work_the_project_has_done(name, tmp_path):
    """The acceptance form of fix 0.3. A kit that loses the design document and every
    role's memory on upgrade is not installable twice, and CLAUDE.md tells the user to
    re-render after each plugin update."""
    cfg, _ = install(tmp_path, name)
    written = {
        cfg.spine["design"]: "\n## backend\nThe ledger writes through one append path.\n",
        cfg.spine["decisions"]: "\n| 0002 | drop the cache | Accepted | M1-S2-BACK-012 |\n",
        cfg.spine["contracts"]: "\n### entries v2\nPOST /entries -> 201 {id}\n",
        cfg.spine["risks"]: "\n| R-013 | peer edits during a sweep | high | open |\n",
        cfg.spine["strategy"]: "\n| M1-S1-BACK-010 | `backend` | ingest | unit | 2xx |\n",
        cfg.spine["plan"]: "\n## Active\nM1-S1-BACK-010 dispatched 2026-10-02\n",
    }
    for rel, text in written.items():
        (tmp_path / rel).write_text((tmp_path / rel).read_text() + text)
    memory = tmp_path / f".claude/agent-memory/{cfg.roles[0].name}/MEMORY.md"
    memory.write_text(memory.read_text() + "\n- alembic autogenerate lies about enums\n")

    assert main(["render", "--profile", str(profile_of(name)), "--out", str(tmp_path),
                 "--force"]) == 0

    for rel, text in written.items():
        assert text in (tmp_path / rel).read_text(), rel
    assert "alembic autogenerate" in memory.read_text()


# --- the installed kit behaves ------------------------------------------------

@pytest.mark.parametrize("name", FIXTURES)
def test_the_first_task_of_the_install_is_executable(name, tmp_path):
    """`M0-S1-ARCH-001` writes `spine.contracts`. Nobody owns it, and until fix 0.6
    `/handoff` read "do not write what you do not own", so the first task of every
    install could only ever be PARTIAL. Assert the whole chain that makes it work:
    the guard allows it, the skill says so, and §8 explains why."""
    cfg, _ = install(tmp_path, name)
    contracts = cfg.spine["contracts"]
    assert not any(contracts in r.owns for r in cfg.roles)

    r = guard(tmp_path, "architect", contracts)
    assert r.returncode == 0, (r.stdout, r.stderr)

    handoff = " ".join((PLUGIN / "skills/handoff/SKILL.md").read_text().split())
    assert "If **another role** owns `spine.contracts`" in handoff
    assert "If **no role** owns it" in handoff
    assert "owned by **no role**" in " ".join(
        (tmp_path / cfg.spine["strategy"]).read_text().split())


@pytest.mark.parametrize("name", FIXTURES)
def test_a_cross_boundary_edit_is_refused_in_prose(name, tmp_path):
    """The guard works in the rendered tree, and its message reaches the agent as a
    sentence rather than a serialised decision object (fix 0.2)."""
    cfg, _ = install(tmp_path, name)
    pairs = [(a, b) for a in cfg.roles for b in cfg.roles if a.name != b.name and b.owns]
    actor, owner = pairs[0]
    victim = owner.owns[0].split("*")[0].rstrip("/") + "/probe.txt"

    r = guard(tmp_path, actor.name, victim)
    assert r.returncode == 2, (actor.name, victim, r.stdout, r.stderr)
    assert r.stdout == "", "stdout is the decision channel; stray output is parsed"
    with pytest.raises(ValueError):
        json.loads(r.stderr)
    assert owner.name in r.stderr and actor.name in r.stderr


@pytest.mark.parametrize("name", FIXTURES)
def test_kit_doctor_passes_on_a_freshly_rendered_kit(name, tmp_path):
    """The end-to-end check the kit ships for its users, run against its own output.

    `toolchain.format` is rewritten to `true` first: `python_monolith` specifies
    `black`, and whether this machine has it is not a property of the kit. Everything
    else is left exactly as rendered.
    """
    install(tmp_path, name)
    lock_path = tmp_path / ".claude/kit.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["toolchain"]["format"] = "true"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

    r = subprocess.run(["bash", str(PLUGIN / "bin/kit-doctor.sh")],
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert "FAIL" not in r.stdout, r.stdout
    assert r.returncode == 0, r.stdout + r.stderr


def test_hooks_are_inert_in_a_rendered_tree_before_the_lock_lands(tmp_path):
    """A half-written install must not start blocking commands."""
    from .hooks_conftest import bash_payload, run_hook
    (tmp_path / "CLAUDE.md").write_text("# partial install")
    r = run_hook("pre-bash-guard.sh", bash_payload("git add -A", tmp_path), tmp_path)
    assert r.returncode == 0


def test_marketplace_source_resolves_to_the_plugin_manifest():
    """Task 1 asserted the source string; assert the path it names exists and that the
    two manifests agree on the plugin name."""
    repo = Path(__file__).resolve().parents[4]
    mp = json.loads((repo / ".claude-plugin/marketplace.json").read_text())
    entry = mp["plugins"][0]
    manifest = repo / entry["source"] / ".claude-plugin/plugin.json"
    assert manifest.exists(), manifest
    assert json.loads(manifest.read_text())["name"] == entry["name"]


def test_the_readme_documents_what_exists_and_not_what_does_not():
    """The audit's RC4 was "no way in". A README that points at M2's installer skills
    would be the same failure wearing a hat."""
    readme = (Path(__file__).resolve().parents[4] / "README.md")
    # Whitespace collapsed: the file is hard-wrapped and the render command carries a
    # line continuation, so a phrase can legitimately straddle a break.
    text = " ".join(readme.read_text().split())
    assert "kitgen render" in text, "the command that works today must be here"
    assert "kit.lock.json" in text, "inertness is the reason this is safe to install"
    assert "/kit-doctor" in text
    assert "/kit-init" in text, "the way in must be the first thing documented"
    assert "--merge" in text, "a retrofit is the common case and must not be a footnote"
    # Every installer skill now exists, so nothing here may be described as pending: a
    # README that points at an unbuilt skill is the same failure as having no way in.
    assert "/kit-upgrade" in text
    assert "Still M2" not in text and "not-yet-shipped" not in text
    for gone in ("/kit-install", "/kit-retrofit"):
        assert gone not in text, (
            f"{gone} was superseded by /kit-init; naming it sends the user to a skill "
            f"that does not exist")
    for skill in ("/kit-init", "/kit-upgrade", "/kit-doctor"):
        assert text.count(skill) >= 2, f"{skill} should be both listed and explained"


# --- the documented install path, followed literally --------------------------

@pytest.mark.parametrize("name", FIXTURES)
def test_a_profile_at_its_own_destination_installs_without_force(name, tmp_path):
    """The README says: put the profile at `.claude/kit.yaml` and render. That path is
    also in the manifest, so the render used to write over its own input — the first
    install clashed with itself and returned 3, leaving `--force` as the only way
    forward on a fresh tree, which is exactly what the docs warn against.

    Found by following the README's steps rather than by reading them.
    """
    cfg = cfg_of(name)
    seed_inherited(tmp_path, cfg)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    here = tmp_path / ".claude/kit.yaml"
    original = profile_of(name).read_text()
    here.write_text("# hand-written, with a comment that must survive\n" + original)

    assert main(["render", "--profile", str(here), "--out", str(tmp_path),
                 "--dry-run"]) == 0, "a dry run on a fresh tree must predict success"
    assert main(["render", "--profile", str(here), "--out", str(tmp_path)]) == 0

    assert here.read_text().startswith("# hand-written"), (
        "the author's profile, comments included, is the source of truth")
    assert (tmp_path / ".claude/kit.lock.json").exists()
    assert json.loads((tmp_path / ".claude/kit.lock.json").read_text()) == \
        json.loads(json.dumps(cfg.to_lock()))
    assert verify(render(cfg), cfg, project_root=tmp_path) == []


def test_a_profile_elsewhere_still_renders_the_kit_yaml(tmp_path):
    """The other direction: a profile outside the tree is not the keystone, so
    `.claude/kit.yaml` must still be written from it."""
    cfg = cfg_of("python_monolith")
    seed_inherited(tmp_path, cfg)
    elsewhere = tmp_path / "profile-source.yaml"
    elsewhere.write_text(profile_of("python_monolith").read_text())
    assert main(["render", "--profile", str(elsewhere), "--out", str(tmp_path)]) == 0
    assert (tmp_path / ".claude/kit.yaml").exists()
    assert yaml.safe_load((tmp_path / ".claude/kit.yaml").read_text())["project"] == {
        "name": cfg.project.name, "slug": cfg.project.slug,
        "summary": cfg.project.summary}
