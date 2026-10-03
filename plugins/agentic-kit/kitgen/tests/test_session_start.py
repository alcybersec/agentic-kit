# plugins/agentic-kit/kitgen/tests/test_session_start.py
"""The session's own grounding, and the drift signal that nothing used to read.

§5.1 defines drift as `mtime(kit.yaml) > mtime(kit.lock.json)` — the profile was edited
and never re-rendered, so every hook is still enforcing the OLD ownership map and the OLD
secrets list. Until this hook existed, only `/kit-doctor` checked it, which means the
guarantee held exactly as long as someone remembered to ask. That is the same shape as the
ownership guard's dependence on workspace trust, and it deserved the same fix.
"""
import json
import os
import subprocess

import pytest

from kitgen.render import render

from .hooks_conftest import HOOKS


def install(tmp_path, cfg):
    man = render(cfg)
    for rel, body in man.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    for rel in cfg.spine["inherited"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    return tmp_path


def start(root):
    return subprocess.run(
        ["bash", str(HOOKS / "session-start.sh")],
        input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(root),
                          "source": "startup"}),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)})


def test_it_says_where_the_project_is(tmp_path, load_fixture):
    cfg = load_fixture("services_layout")
    r = start(install(tmp_path, cfg))
    assert r.returncode == 0
    out = r.stdout
    assert f"agentic-kit {cfg.kit_version}" in out
    assert f"{len(cfg.roles)} roles" in out
    assert cfg.milestones["outline"][0]["id"] in out
    assert "You are the Orchestrator" in out
    assert "Nothing in flight" in out and cfg.spine["plan"] in out


def test_an_in_flight_task_is_reported_from_the_plan_not_asserted(tmp_path, load_fixture):
    """Read from the file the Orchestrator actually dispatches from, so the greeting
    cannot disagree with it — audit finding A-I4 was §10 calling a milestone open while
    the plan said "not yet entered"."""
    cfg = load_fixture("services_layout")
    root = install(tmp_path, cfg)
    plan = root / cfg.spine["plan"]
    plan.write_text(plan.read_text().replace(
        "## Open gates",
        "## Active\n\n| M1-S1-BACKEND-010 | `backend` | dispatched 2026-10-03 |\n\n## Open gates",
        1))
    out = start(root).stdout
    assert "In flight" in out and "M1-S1-BACKEND-010" in out
    assert "Nothing in flight" not in out


def test_drift_is_reported(tmp_path, load_fixture):
    cfg = load_fixture("python_monolith")
    root = install(tmp_path, cfg)
    lock = root / ".claude/kit.lock.json"
    later = lock.stat().st_mtime_ns + 2_000_000_000
    os.utime(root / ".claude/kit.yaml", ns=(later, later))
    out = start(root).stdout
    assert "DRIFT" in out
    assert "NOT in effect" in out, "say what it costs, not just that it happened"


def test_a_clean_render_is_not_drift(tmp_path, load_fixture):
    """render() writes kit.yaml immediately before the lock, so the two can share an
    mtime. `-nt` is strictly-newer, which is what keeps this quiet."""
    root = install(tmp_path, load_fixture("python_monolith"))
    lock = root / ".claude/kit.lock.json"
    same = lock.stat().st_mtime_ns
    os.utime(root / ".claude/kit.yaml", ns=(same, same))
    assert "DRIFT" not in start(root).stdout


def test_a_leftover_guard_script_is_reported(tmp_path, load_fixture):
    root = install(tmp_path, load_fixture("python_monolith"))
    (root / ".claude/hooks").mkdir(parents=True, exist_ok=True)
    (root / ".claude/hooks/ownership-guard.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    out = start(root).stdout
    assert "STALE" in out and "never invoked" in out


def test_open_risks_are_counted(tmp_path, load_fixture):
    cfg = load_fixture("python_monolith")
    root = install(tmp_path, cfg)
    reg = root / cfg.spine["risks"]
    reg.write_text(reg.read_text()
                   + "| R-001 | a thing | high | open |\n"
                   + "| R-002 | another | low | open |\n"
                   + "| R-003 | closed one | low | closed |\n")
    out = start(root).stdout
    assert "Open risks" in out and ": 2." in out


def test_it_is_silent_outside_a_kit_project(tmp_path):
    r = start(tmp_path)
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""


def test_it_is_silent_when_the_lock_is_unusable(tmp_path, load_fixture):
    root = install(tmp_path, load_fixture("python_monolith"))
    (root / ".claude/kit.lock.json").write_text("")
    r = start(root)
    assert r.returncode == 0 and r.stdout == ""
