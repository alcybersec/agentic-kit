# plugins/agentic-kit/kitgen/tests/test_usage_gate.py
"""Pausing autonomous work before a subscription window runs out, and resuming after.

The architecture is forced, not chosen. `rate_limits` reaches user code in exactly one
payload — the status line's — and NO hook event carries it, so the only possible shape is:
status line as sensor, a file as the bus, a hook as the actuator. The sensor is
`bin/kit-usage-probe.sh`; this tests both halves and the seam between them.

Two properties matter more than the arithmetic:

  * **No `rate_limits` means do nothing.** It appears only for claude.ai Pro and Max, so
    its absence IS the API-key case. No detection, no snapshot, no pause.
  * **A stale reading fails OPEN.** The status line stops being invoked when a session is
    not rendering, and pausing on an hour-old number would stop work that could have
    continued. This gate reduces overrun; it does not guarantee against it.
"""
import json
import subprocess
import time
from pathlib import Path

import pytest

from kitgen.render import render

from .hooks_conftest import HOOKS

PLUGIN = Path(__file__).resolve().parents[2]
PROBE = PLUGIN / "bin/kit-usage-probe.sh"
GATE = HOOKS / "usage-gate.sh"


def probe(payload, snap, *args):
    return subprocess.run(
        ["bash", str(PROBE), *args], input=json.dumps(payload),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(snap.parent.parent),
             "CLAUDE_KIT_USAGE_FILE": str(snap)})


def project(tmp_path, load_fixture, name="python_monolith", **usage):
    cfg = load_fixture(name)
    lock = json.loads(render(cfg)[".claude/kit.lock.json"])
    lock["usage"] = {**lock["usage"], **usage}
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps(lock))
    return tmp_path


def gate(root, snap, tool="Agent"):
    return subprocess.run(
        ["bash", str(GATE)],
        input=json.dumps({"tool_name": tool, "tool_input": {}, "cwd": str(root)}),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root),
             "CLAUDE_KIT_USAGE_FILE": str(snap)})


def snapshot(path, five=None, seven=None, age_s=0):
    data = {"read_at": int(time.time()) - age_s}
    if five is not None:
        data["five_hour"] = {"used_percentage": five,
                             "resets_at": int(time.time()) + 3600}
    if seven is not None:
        data["seven_day"] = {"used_percentage": seven,
                             "resets_at": int(time.time()) + 200_000}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


# --- the sensor ---------------------------------------------------------------

def test_the_probe_writes_a_snapshot_and_prints_nothing(tmp_path):
    """Printing would disturb whatever layout the user's status line already has."""
    snap = tmp_path / "h/.claude/kit-usage.json"
    snap.parent.mkdir(parents=True)
    r = probe({"rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": 1},
                               "seven_day": {"used_percentage": 41.2, "resets_at": 2}}},
              snap)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    data = json.loads(snap.read_text())
    assert data["five_hour"]["used_percentage"] == 23.5
    assert data["seven_day"]["resets_at"] == 2
    assert abs(data["read_at"] - time.time()) < 60, "the reading must carry its own age"


def test_the_probe_can_print_a_segment_on_request(tmp_path):
    snap = tmp_path / "h/.claude/kit-usage.json"
    snap.parent.mkdir(parents=True)
    r = probe({"rate_limits": {"five_hour": {"used_percentage": 23.9, "resets_at": 1}}},
              snap, "--print")
    assert r.stdout.strip() == "5h 23%"


def test_no_rate_limits_means_no_snapshot(tmp_path):
    """`rate_limits` appears only for Pro and Max, so its absence IS the API-key case.
    Nothing to detect, and nothing left behind for the gate to act on."""
    snap = snapshot(tmp_path / "h/.claude/kit-usage.json", five=99)
    assert snap.exists()
    r = probe({"model": {"id": "x"}, "cost": {"total_cost_usd": 1}}, snap)
    assert r.returncode == 0
    assert not snap.exists(), "a stale reading is worse than none: the gate would act on it"


def test_a_window_that_has_reset_is_simply_absent(tmp_path):
    """Claude Code drops a window once its `resets_at` passes, so a missing window means
    'no limit in force', never 'zero used'."""
    snap = tmp_path / "h/.claude/kit-usage.json"
    snap.parent.mkdir(parents=True)
    probe({"rate_limits": {"seven_day": {"used_percentage": 41.2, "resets_at": 2}}}, snap)
    data = json.loads(snap.read_text())
    assert data["five_hour"] is None and data["seven_day"]["used_percentage"] == 41.2


# --- the gate -----------------------------------------------------------------

def test_no_snapshot_means_no_gate(tmp_path, load_fixture):
    """An unwired probe, or an API key. The gate must be inert, not suspicious."""
    root = project(tmp_path, load_fixture)
    assert gate(root, tmp_path / "absent.json").returncode == 0


def test_under_both_thresholds_is_allowed(tmp_path, load_fixture):
    root = project(tmp_path, load_fixture)
    snap = snapshot(tmp_path / "u.json", five=89, seven=94)
    assert gate(root, snap).returncode == 0


@pytest.mark.parametrize("five,seven,window", [
    (90, 10, "5-hour"), (95, 10, "5-hour"), (10, 95, "7-day"), (10, 99, "7-day"),
])
def test_at_or_over_a_threshold_pauses(tmp_path, load_fixture, five, seven, window):
    """At the threshold, not past it: 90 means 90."""
    root = project(tmp_path, load_fixture)
    snap = snapshot(tmp_path / "u.json", five=five, seven=seven)
    r = gate(root, snap)
    assert r.returncode == 2, (five, seven, r.stdout, r.stderr)
    assert window in r.stderr
    assert "Paused" in r.stderr


def test_the_pause_names_both_halves_of_the_protocol(tmp_path, load_fixture):
    """Durable first, scheduled second. A scheduled task lives only in its session, so the
    plan entry is what carries the work across a session that ends."""
    root = project(tmp_path, load_fixture)
    r = gate(root, snapshot(tmp_path / "u.json", five=10, seven=97))
    assert "Record the state in the plan" in r.stderr
    assert "ONE-SHOT scheduled task" in r.stderr
    assert "/next-task" in r.stderr
    assert "if the session ends the plan entry above is what carries the work" in r.stderr
    assert "Do not retry this dispatch" in r.stderr
    assert "do not start the task yourself" in r.stderr


def test_the_pause_names_the_reset_time(tmp_path, load_fixture):
    """"Resume later" is not actionable; a wall-clock time is."""
    root = project(tmp_path, load_fixture)
    r = gate(root, snapshot(tmp_path / "u.json", five=99))
    assert "Schedule the resume for just after" in r.stderr
    assert ":" in r.stderr.split("just after")[1][:24], "a time, not a placeholder"


def test_the_worst_window_is_the_one_reported(tmp_path, load_fixture):
    root = project(tmp_path, load_fixture)
    r = gate(root, snapshot(tmp_path / "u.json", five=91, seven=99))
    assert "7-day" in r.stderr and "99%" in r.stderr


def test_a_stale_reading_fails_open(tmp_path, load_fixture):
    """The status line is not invoked when a session is not rendering. Pausing on an
    hour-old number would stop work that could have continued, so the gate declines to
    act on one — and the docs say plainly that this reduces overrun rather than
    preventing it."""
    root = project(tmp_path, load_fixture)
    snap = snapshot(tmp_path / "u.json", five=99, age_s=5000)
    assert gate(root, snap).returncode == 0


def test_the_staleness_window_comes_from_the_profile(tmp_path, load_fixture):
    root = project(tmp_path, load_fixture, stale_after_s=10_000)
    snap = snapshot(tmp_path / "u.json", five=99, age_s=5000)
    assert gate(root, snap).returncode == 2, "5000s is fresh when stale_after_s is 10000"


def test_the_thresholds_come_from_the_profile(tmp_path, load_fixture):
    root = project(tmp_path, load_fixture, five_hour_pct=50)
    snap = snapshot(tmp_path / "u.json", five=55)
    assert gate(root, snap).returncode == 2
    root2 = project(tmp_path / "b", load_fixture, five_hour_pct=99)
    assert gate(root2, snap).returncode == 0


def test_only_dispatch_is_gated(tmp_path, load_fixture):
    """The Orchestrator must still be able to record where the work stopped — a gate that
    blocked everything would prevent the parking it demands. `hooks.json` matches
    `Agent|Task` and nothing else; this asserts the registration, since the hook itself
    sees whatever it is given."""
    entries = json.loads((HOOKS / "hooks.json").read_text())["hooks"]["PreToolUse"]
    mine = [e for e in entries if "usage-gate.sh" in str(e)]
    assert len(mine) == 1
    assert set(mine[0]["matcher"].split("|")) == {"Agent", "Task"}
    for other in entries:
        if "usage-gate.sh" in str(other):
            continue
        assert "Agent" not in other.get("matcher", ""), "nothing else gates dispatch"


def test_the_gate_survives_an_environment_without_home(tmp_path, load_fixture):
    """These hooks run under `set -u` with whatever environment the harness provides, and
    HOME is not guaranteed. `${HOME}` unbound aborts the script, and an exit code other
    than 2 is read as "continue" — so the gate would have been silently absent. Found by
    the kit-doctor tests, which pass no HOME."""
    root = project(tmp_path, load_fixture)
    r = subprocess.run(
        ["bash", str(GATE)],
        input=json.dumps({"tool_name": "Agent", "tool_input": {}, "cwd": str(root)}),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)})
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "unbound variable" not in r.stderr
