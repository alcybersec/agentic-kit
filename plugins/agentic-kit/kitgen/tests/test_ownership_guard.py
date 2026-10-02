# plugins/agentic-kit/kitgen/tests/test_ownership_guard.py
"""The guard is the only mechanical enforcement of exclusive path ownership.

Every case here was validated against a prototype before the implementation was
written, so a failure means the implementation diverged from a verified design.
"""
import json
import re
import subprocess

import pytest

from kitgen.render import render

from .hooks_conftest import HOOKS

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]
# The guard ships WITH THE PLUGIN and learns its role from the payload's `agent_type`.
# It used to be rendered into the project and registered by each role card's frontmatter
# `hooks:` block with the role as $1 — and frontmatter hooks are skipped until the
# workspace is trusted, so the guard was absent in a fresh clone and in every `-p`
# session while the spec said ownership was enforced. Verified 2026-10-02 on a live
# install: a plugin hook fires inside a subagent in an untrusted checkout, and the
# payload carries `agent_type` set to the subagent's frontmatter `name`.
GUARD = HOOKS / "ownership-guard.sh"


def _install(tmp_path, cfg):
    """Write only the lock. There is nothing per-project left to install."""
    man = render(cfg)
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(man[".claude/kit.lock.json"])
    return GUARD


def _run(script, tmp_path, role, rel, tool="Edit", **payload_extra):
    payload = {"tool_name": tool, "tool_input": {"file_path": str(tmp_path / rel)},
               "cwd": str(tmp_path), "agent_id": "a0", "agent_type": role}
    payload.update(payload_extra)
    if role is None:
        del payload["agent_type"]
    return subprocess.run(
        ["bash", str(script)], input=json.dumps(payload),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)})


# (fixture, role, path, expected) -- expected True means BLOCKED
CASES = [
    # a role's own territory is always allowed
    ("python_monolith", "backend", "src/ledger/api/routes.py", False),
    ("python_monolith", "data", "alembic/versions/0003_x.py", False),
    ("services_layout", "frontend", "services/ui/App.tsx", False),
    ("greenfield_prd", "safety", "tests/safety/test_floor.py", False),
    # another role's territory is blocked
    ("python_monolith", "backend", "src/ledger/models/entry.py", True),
    ("python_monolith", "architect", "src/ledger/api/routes.py", True),
    ("services_layout", "worker", "services/api/main.py", True),
    ("greenfield_prd", "qa", "tests/safety/test_floor.py", True),
    # unowned paths are allowed -- this is what keeps the guard usable
    ("python_monolith", "backend", "Makefile", False),
    ("python_monolith", "backend", "README.md", False),
    ("python_monolith", "backend", "tests/unit/test_routes.py", False),
    ("python_monolith", "backend", "docs/design.md", False),
    ("services_layout", "devops", "pyproject.toml", False),
    ("greenfield_prd", "devops", "src/nimbus/sync.py", False),
    # a role's own memory is allowed, another role's is not
    ("python_monolith", "backend", ".claude/agent-memory/backend/MEMORY.md", False),
    ("python_monolith", "backend", ".claude/agent-memory/backend/a-fact.md", False),
    ("python_monolith", "backend", ".claude/agent-memory/data/MEMORY.md", True),
    # role cards and dispatch state are never an agent's to write
    ("python_monolith", "backend", ".claude/agents/backend.md", True),
    ("python_monolith", "backend", ".claude/agents/data.md", True),
    ("python_monolith", "qa", "docs/plan/README.md", True),
    ("services_layout", "devops", "docs/plan/README.md", True),
    # the rulebook and the register are never an agent's to rewrite
    ("python_monolith", "backend", "docs/strategy.md", True),
    ("python_monolith", "safety", "docs/strategy.md", True),
    ("services_layout", "qa", "docs/risk-register.md", True),
    # but these stay writable: design invites per-role sections, and the
    # contract-first rule needs the implementing role to record a contract
    ("python_monolith", "backend", "docs/design.md", False),
    ("python_monolith", "backend", "docs/CONTRACTS.md", False),
    ("python_monolith", "architect", "docs/decisions.md", False),
    # the guard protects itself: every refusal above is only as strong as these
    ("python_monolith", "backend", ".claude/hooks/ownership-guard.sh", True),
    ("python_monolith", "safety", ".claude/hooks/ownership-guard.sh", True),
    ("python_monolith", "backend", ".claude/kit.lock.json", True),
    ("python_monolith", "backend", ".claude/kit.yaml", True),
    ("python_monolith", "backend", ".claude/settings.json", True),
    ("services_layout", "devops", ".claude/kit.lock.json", True),
    # inherited documents are the user's, not an agent's
    ("services_layout", "backend", "docs/PRD.md", True),
    ("services_layout", "worker", "docs/architecture.md", True),
    ("greenfield_prd", "safety", "docs/PRD.md", True),
    # ... and a project that inherited nothing keeps those names free
    ("python_monolith", "backend", "docs/PRD.md", False),
]


@pytest.mark.parametrize("fixture,role,rel,blocked", CASES)
def test_ownership_guard_verdict(tmp_path, load_fixture, fixture, role, rel, blocked):
    script = _install(tmp_path, load_fixture(fixture))
    r = _run(script, tmp_path, role, rel)
    assert (r.returncode == 2) is blocked, (fixture, role, rel, r.returncode, r.stderr)
    if blocked:
        assert r.stderr.strip(), "a block must explain itself"


def test_a_block_names_the_owner_and_the_remedy(tmp_path, load_fixture):
    script = _install(tmp_path, load_fixture("python_monolith"))
    r = _run(script, tmp_path, "backend", "src/ledger/models/entry.py")
    assert r.returncode == 2
    assert "data" in r.stderr
    assert "request" in r.stderr.lower() or "split" in r.stderr.lower()


def test_the_guard_is_inert_without_a_lock(tmp_path, load_fixture):
    """Same blast-radius rule as every other hook in this kit."""
    script = _install(tmp_path, load_fixture("python_monolith"))
    (tmp_path / ".claude/kit.lock.json").unlink()
    assert _run(script, tmp_path, "backend", "src/ledger/models/entry.py").returncode == 0


def test_an_absolute_path_outside_the_project_is_not_policed(tmp_path, load_fixture):
    script = _install(tmp_path, load_fixture("python_monolith"))
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "/etc/hosts"},
               "cwd": str(tmp_path)}
    r = subprocess.run(["bash", str(script), "backend"], input=json.dumps(payload),
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert r.returncode == 0


def test_no_role_card_registers_a_frontmatter_hook(load_fixture):
    """The registration moved into the plugin's hooks.json. A card still carrying a
    frontmatter `hooks:` block would point at a script no render writes any more — and
    a hook whose script is missing exits non-2, which Claude Code reads as "continue".
    Fail-open, silently, which is the whole failure mode /kit-doctor exists to catch."""
    for name in FIXTURES:
        cfg = load_fixture(name)
        man = render(cfg)
        for r in cfg.roles:
            card = man[f".claude/agents/{r.name}.md"]
            fm = re.match(r"^---\n(.*?)\n---\n", card, re.S).group(1)
            assert "hooks:" not in fm, (name, r.name)
            assert "ownership-guard" not in card, (name, r.name)


def test_nothing_is_rendered_under_claude_hooks(load_fixture):
    """`.claude/hooks/` is no longer the kit's to write. The guard's own blanket refusal
    still covers that directory, because a project may keep hooks of its own."""
    for name in FIXTURES:
        for p in render(load_fixture(name)):
            assert not p.startswith(".claude/hooks/"), (name, p)


def test_the_orchestrator_card_does_not_register_the_guard(load_fixture):
    """It owns no paths and legitimately writes the plan, the risk register and the
    gate bundles. Guarding it would block its actual job."""
    for name in FIXTURES:
        card = render(load_fixture(name))[".claude/agents/orchestrator.md"]
        assert "ownership-guard" not in card, name


def test_the_guard_matcher_covers_every_file_mutating_tool():
    """Read is deliberately absent: reading another role's file is not a boundary
    crossing, and denying it would make cross-role review impossible."""
    entries = json.loads((HOOKS / "hooks.json").read_text())["hooks"]["PreToolUse"]
    mine = [e for e in entries if "ownership-guard.sh" in str(e)]
    assert len(mine) == 1, entries
    tools = mine[0]["matcher"].split("|")
    assert set(tools) == {"Edit", "Write", "NotebookEdit", "MultiEdit"}, tools


def test_the_guard_sources_the_shared_library_rather_than_copying_it():
    """The inlined copy is gone, and with it the drift it needed a test to police. The
    guard must define none of the matcher helpers itself."""
    body = (HOOKS / "ownership-guard.sh").read_text()
    assert re.search(r"^source .*kitlock\.sh", body, re.M)
    # Nothing from the library may be redefined here...
    for fn in ("kit_lexnorm", "kit_candidates", "kit_match_glob", "kit_deny",
               "kit_init", "kit_in", "kit_q"):
        assert not re.search(rf"^{fn}\(\)", body, re.M), f"{fn} is redefined, not reused"
    # ...and the ones this guard's logic needs must actually be called. kit_lexnorm is
    # absent on purpose: kit_candidates calls it, the guard does not.
    for fn in ("kit_init", "kit_in", "kit_q", "kit_candidates", "kit_match_glob",
               "kit_deny"):
        assert fn in body, f"{fn} is not used at all"


# ---- adversarial cases beyond the plan's corpus ----------------------------------

def _plain(tmp_path, cfg):
    return _install(tmp_path, cfg)


def test_a_symlink_from_an_owned_path_into_another_roles_tree_is_blocked(tmp_path, load_fixture):
    script = _install(tmp_path, load_fixture("python_monolith"))
    (tmp_path / "src/ledger/models").mkdir(parents=True)
    (tmp_path / "src/ledger/models/entry.py").write_text("x")
    (tmp_path / "src/ledger/api").mkdir(parents=True)
    (tmp_path / "src/ledger/api/link.py").symlink_to(tmp_path / "src/ledger/models/entry.py")
    r = _run(script, tmp_path, "backend", "src/ledger/api/link.py")
    assert r.returncode == 2, r.stderr


def test_a_dotdot_traversal_into_another_roles_tree_is_blocked(tmp_path, load_fixture):
    script = _install(tmp_path, load_fixture("python_monolith"))
    r = _run(script, tmp_path, "backend", "src/ledger/api/../models/entry.py")
    assert r.returncode == 2, r.stderr


def test_a_symlink_from_own_memory_into_anothers_memory_is_blocked(tmp_path, load_fixture):
    script = _install(tmp_path, load_fixture("python_monolith"))
    (tmp_path / ".claude/agent-memory/data").mkdir(parents=True)
    (tmp_path / ".claude/agent-memory/data/MEMORY.md").write_text("x")
    (tmp_path / ".claude/agent-memory/backend").mkdir(parents=True)
    (tmp_path / ".claude/agent-memory/backend/l.md").symlink_to(
        tmp_path / ".claude/agent-memory/data/MEMORY.md")
    assert _run(script, tmp_path, "backend", ".claude/agent-memory/backend/l.md").returncode == 2


def test_a_symlink_out_of_the_project_is_not_policed(tmp_path, load_fixture):
    script = _install(tmp_path, load_fixture("python_monolith"))
    (tmp_path / "out.txt").symlink_to("/etc/hosts")
    assert _run(script, tmp_path, "backend", "out.txt").returncode == 0


@pytest.mark.parametrize("role", ["backend", "data", "architect", "qa", "safety", "devops"])
def test_strategy_and_risks_are_blocked_for_every_role(tmp_path, load_fixture, role):
    cfg = load_fixture("python_monolith")
    if role not in [r.name for r in cfg.roles]:
        pytest.skip("not in this fixture")
    script = _install(tmp_path, cfg)
    for rel in ("docs/strategy.md", "docs/risk-register.md"):
        assert _run(script, tmp_path, role, rel).returncode == 2, (role, rel)




# --- critical paths: the veto role holds them outright ------------------------

CRITICAL = ["src/ledger/api/kill_switch.py", "src/ledger/models/permissions.py"]


def _install_critical(tmp_path, load_variant):
    """python_monolith with two critical files, one inside `backend`'s tree and one
    inside `data`'s — the case the feature exists for."""
    cfg = load_variant("python_monolith", critical=CRITICAL)
    return _install(tmp_path, cfg), cfg


@pytest.mark.parametrize("rel", CRITICAL)
@pytest.mark.parametrize("role", ["backend", "data", "architect", "qa", "devops"])
def test_a_critical_path_is_refused_to_every_non_veto_role(tmp_path, load_variant,
                                                           role, rel):
    """Including the role that owns the directory around it: `backend` owns
    `src/ledger/api/**` and still may not touch the kill switch."""
    script, cfg = _install_critical(tmp_path, load_variant)
    r = _run(script, tmp_path, role, rel)
    assert r.returncode == 2, (role, rel, r.stdout, r.stderr)
    assert "critical path" in r.stderr
    assert cfg.veto_role.name in r.stderr, "the message must name who can change it"


@pytest.mark.parametrize("rel", CRITICAL)
def test_the_veto_role_may_write_a_critical_path_it_does_not_own(tmp_path,
                                                                load_variant, rel):
    """The other half, and the whole point: `safety` owns neither directory."""
    script, cfg = _install_critical(tmp_path, load_variant)
    assert not any(rel.startswith(g.rstrip("*").rstrip("/") + "/")
                   for g in cfg.veto_role.owns), "safety must not own it, or this proves nothing"
    r = _run(script, tmp_path, cfg.veto_role.name, rel)
    assert r.returncode == 0, (rel, r.stderr)


def test_a_critical_glob_covers_a_subtree(tmp_path, load_variant):
    cfg = load_variant("python_monolith", critical=["src/ledger/api/admin/**"])
    script = _install(tmp_path, cfg)
    assert _run(script, tmp_path, "backend", "src/ledger/api/admin/users.py").returncode == 2
    assert _run(script, tmp_path, "safety", "src/ledger/api/admin/users.py").returncode == 0
    # A sibling inside the same owned tree is unaffected.
    assert _run(script, tmp_path, "backend", "src/ledger/api/routes.py").returncode == 0


def test_neighbouring_files_are_untouched_by_a_critical_entry(tmp_path, load_variant):
    """The feature must not quietly widen: only the named paths change hands."""
    script, cfg = _install_critical(tmp_path, load_variant)
    assert _run(script, tmp_path, "backend", "src/ledger/api/routes.py").returncode == 0
    assert _run(script, tmp_path, "data", "src/ledger/models/entry.py").returncode == 0
    # And safety gains nothing else in those trees.
    assert _run(script, tmp_path, "safety", "src/ledger/api/routes.py").returncode == 2


def test_no_critical_list_changes_nothing(tmp_path, load_fixture):
    """Absent by default, and absent must mean inert."""
    cfg = load_fixture("python_monolith")
    assert cfg.critical == []
    script = _install(tmp_path, cfg)
    assert _run(script, tmp_path, "backend", "src/ledger/api/routes.py").returncode == 0
    assert _run(script, tmp_path, "safety", "src/ledger/api/routes.py").returncode == 2


# --- the role comes from the payload (2026-10-02) -----------------------------

def test_the_main_thread_is_never_guarded(tmp_path, load_fixture):
    """No `agent_type` means the Orchestrator, which owns no paths and legitimately
    writes the dispatch state, the register and the gate bundles. Under the old design
    this depended on not registering the guard on its card; now it is structural."""
    script = _install(tmp_path, load_fixture("python_monolith"))
    for rel in ("src/ledger/api/routes.py", "docs/strategy.md", "docs/plan/README.md",
                ".claude/kit.lock.json", ".claude/agents/backend.md"):
        r = _run(script, tmp_path, None, rel)
        assert r.returncode == 0, (rel, r.stderr)


@pytest.mark.parametrize("agent", ["Explore", "general-purpose", "Plan",
                                   "security-reviewer", ""])
def test_an_agent_that_is_not_a_role_is_not_policed(tmp_path, load_fixture, agent):
    """An ownership map describes the roles it lists. A project's own subagent, or a
    built-in one, is not bound by a boundary nobody drew for it."""
    script = _install(tmp_path, load_fixture("python_monolith"))
    r = _run(script, tmp_path, agent, "src/ledger/api/routes.py")
    assert r.returncode == 0, (agent, r.stderr)
    r = _run(script, tmp_path, agent, "docs/strategy.md")
    assert r.returncode == 0, (agent, r.stderr)


def test_a_role_whose_owns_is_empty_is_still_policed(tmp_path, load_variant):
    """`jq -e` on the role's presence, not on its paths: a role that owns nothing is
    still a role, and must still be refused another role's tree."""
    cfg = load_variant("python_monolith", critical=[])
    lock = cfg.to_lock()
    next(r for r in lock["roles"] if r["name"] == "qa")["owns"] = []
    from kitgen.model import KitConfig
    script = _install(tmp_path, KitConfig.from_dict(lock))
    assert _run(script, tmp_path, "qa", "src/ledger/api/routes.py").returncode == 2


def test_no_file_path_in_the_payload_is_allowed(tmp_path, load_fixture):
    script = _install(tmp_path, load_fixture("python_monolith"))
    r = subprocess.run(
        ["bash", str(script)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {},
                          "cwd": str(tmp_path), "agent_type": "backend"}),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("tool", ["Edit", "Write", "NotebookEdit", "MultiEdit"])
def test_every_matched_tool_is_guarded(tmp_path, load_fixture, tool):
    script = _install(tmp_path, load_fixture("python_monolith"))
    r = _run(script, tmp_path, "backend", "src/ledger/models/entry.py", tool=tool)
    assert r.returncode == 2, (tool, r.stdout, r.stderr)
