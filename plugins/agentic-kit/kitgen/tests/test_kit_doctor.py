# plugins/agentic-kit/kitgen/tests/test_kit_doctor.py
"""`bin/kit-doctor.sh` is the only thing that can tell a disarmed guard from an
inert one.

Every hook in this kit exits 0 when it cannot do its job -- no `jq`, no lock, a
renamed script -- and Claude Code reads any non-2 exit as "continue". That is the
right default for a plugin installed machine-wide (§4.3), and it means the kit
cannot otherwise report whether its guards are protecting a project. So the doctor
itself needs to be shown failing: a check that cannot fail is worth nothing here.
"""
import json
import os
import subprocess

import pytest

from kitgen.render import render

PLUGIN = __import__("pathlib").Path(__file__).resolve().parents[2]
DOCTOR = PLUGIN / "bin/kit-doctor.sh"


def install(tmp_path, cfg):
    man = render(cfg)
    for rel, body in man.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        if rel.startswith(".claude/hooks/"):
            p.chmod(0o755)
    for rel in cfg.spine["inherited"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("inherited")
    # `true` as the formatter: present on every machine, so the post-edit-format
    # check does not depend on whether this host happens to have ruff.
    lock = tmp_path / ".claude/kit.lock.json"
    data = json.loads(lock.read_text())
    data["toolchain"]["format"] = "true"
    lock.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return tmp_path


def plugin_copy(tmp_path):
    """A throwaway copy of the plugin's hooks and bin.

    The guard is a plugin hook now, not a per-project file, so "disarm the guard" can no
    longer mean editing something in the project. Copying the plugin keeps the sabotage
    tests honest — they run the real script against a real tree — without mutating the
    plugin this repository ships.
    """
    import shutil
    dest = tmp_path / "plugin"
    (dest).mkdir()
    for part in ("hooks", "bin"):
        shutil.copytree(PLUGIN / part, dest / part)
    return dest


def doctor(root, plugin=None):
    script = (plugin / "bin/kit-doctor.sh") if plugin else DOCTOR
    return subprocess.run(["bash", str(script)], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)})


@pytest.mark.parametrize("fixture", ["python_monolith", "services_layout"])
def test_a_correctly_installed_kit_passes_every_check(tmp_path, load_fixture, fixture):
    r = doctor(install(tmp_path, load_fixture(fixture)))
    assert "FAIL" not in r.stdout, r.stdout
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all checks passed" in r.stdout


def test_a_disarmed_ownership_guard_is_reported(tmp_path, load_fixture):
    """The failure the whole script exists for: a guard that runs, exits 0 and protects
    nothing looks identical to a correctly inert one."""
    root = install(tmp_path, load_fixture("services_layout"))
    plug = plugin_copy(tmp_path)
    (plug / "hooks/ownership-guard.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    r = doctor(root, plug)
    assert r.returncode == 1
    assert "ALLOWED a payload that must be refused" in r.stdout


def test_a_guard_that_refuses_the_main_thread_is_reported(tmp_path, load_fixture):
    """The opposite failure, and newly possible: the guard now decides for itself whether
    a call is the Orchestrator's, so a bug there would block the one agent that must
    write the plan, the register and the gate bundles."""
    root = install(tmp_path, load_fixture("services_layout"))
    plug = plugin_copy(tmp_path)
    g = plug / "hooks/ownership-guard.sh"
    body = g.read_text().replace('[ -n "$role" ] || exit 0', '[ -n "$role" ] || role=qa')
    assert body != g.read_text()
    g.write_text(body)
    r = doctor(root, plug)
    assert r.returncode == 1
    assert "the main thread was refused" in r.stdout


def test_a_role_card_still_registering_the_guard_is_reported(tmp_path, load_fixture):
    """A card from a render before 2026-10-02 points at a script nothing writes any more,
    and a hook whose script is missing exits non-2 — which Claude Code reads as
    "continue". Fail-open, silently."""
    root = install(tmp_path, load_fixture("services_layout"))
    card = root / ".claude/agents/architect.md"
    card.write_text(card.read_text().replace(
        "memory: project",
        'memory: project\nhooks:\n  PreToolUse:\n    - matcher: "Edit"\n      hooks:\n'
        '        - type: command\n          command: bash ".claude/hooks/ownership-guard.sh" architect',
        1))
    r = doctor(root)
    assert r.returncode == 1
    assert "still register the guard in frontmatter" in r.stdout
    assert "architect" in r.stdout


def test_a_missing_guard_script_is_reported(tmp_path, load_fixture):
    root = install(tmp_path, load_fixture("python_monolith"))
    plug = plugin_copy(tmp_path)
    (plug / "hooks/ownership-guard.sh").unlink()
    r = doctor(root, plug)
    assert r.returncode == 1 and "script missing" in r.stdout


def test_a_lock_older_than_the_profile_is_reported(tmp_path, load_fixture):
    """§5.1's drift signal: hooks read the lock, so an edit to kit.yaml that was
    never re-rendered is not in effect, however correct it looks."""
    root = install(tmp_path, load_fixture("python_monolith"))
    # Set the mtime explicitly rather than touch(): on this filesystem a write and
    # a touch microseconds apart can land on the same nanosecond, and `-nt` is
    # strictly-newer. That is the right way round -- render() writes kit.yaml then
    # the lock (§5.1), so equal mtimes must NOT read as drift -- but it makes
    # touch() too fast to simulate a hand edit.
    # Nanoseconds, not `st_mtime`: that is a float in seconds and cannot represent
    # a filesystem timestamp exactly, so a round trip through it can land a few
    # hundred nanoseconds either side of the original -- enough to make `-nt`
    # answer at random.
    lock = root / ".claude/kit.lock.json"
    later = lock.stat().st_mtime_ns + 2_000_000_000
    os.utime(root / ".claude/kit.yaml", ns=(later, later))
    r = doctor(root)
    assert r.returncode == 1 and "kit.yaml is newer" in r.stdout


def test_equal_mtimes_are_not_drift(tmp_path, load_fixture):
    """A clean render writes kit.yaml immediately before the lock, so the two can
    share an mtime. `-nt` is strictly-newer, which is what keeps that quiet."""
    root = install(tmp_path, load_fixture("python_monolith"))
    lock = root / ".claude/kit.lock.json"
    same = lock.stat().st_mtime_ns
    os.utime(root / ".claude/kit.yaml", ns=(same, same))
    assert "kit.yaml is newer" not in doctor(root).stdout



def test_it_declines_outside_a_kit_project(tmp_path):
    """Same blast-radius rule as every hook: this is a machine-wide plugin."""
    r = doctor(tmp_path)
    assert r.returncode == 1
    assert "the kit is not installed" in r.stdout


def test_an_unparseable_lock_is_reported_not_ignored(tmp_path, load_fixture):
    root = install(tmp_path, load_fixture("python_monolith"))
    (root / ".claude/kit.lock.json").write_text("{not json")
    r = doctor(root)
    assert r.returncode == 1 and "every hook is inert" in r.stdout


def test_a_zero_byte_lock_is_reported(tmp_path, load_fixture):
    """`jq -e` exits 0 on an empty file, which is how a zero-byte lock once read
    as a valid profile."""
    root = install(tmp_path, load_fixture("python_monolith"))
    (root / ".claude/kit.lock.json").write_text("")
    r = doctor(root)
    assert r.returncode == 1 and "every hook is inert" in r.stdout


def test_a_leftover_rendered_guard_is_reported(tmp_path, load_fixture):
    """A real upgrade finding: plugin 1.0.0 rendered the guard into
    `.claude/hooks/`, and `--force` on 1.1.0 does not delete files it no longer
    writes. The orphan is never invoked, which is the problem — a file that looks
    like an enforcement hook and does nothing invites the belief that ownership is
    enforced from the project."""
    root = install(tmp_path, load_fixture("python_monolith"))
    (root / ".claude/hooks").mkdir(parents=True, exist_ok=True)
    (root / ".claude/hooks/ownership-guard.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    r = doctor(root)
    assert r.returncode == 1
    assert "leftover guard script" in r.stdout and "Delete it" in r.stdout


def test_a_kit_version_behind_the_plugin_is_a_note_not_a_failure(tmp_path, load_fixture):
    """`kit_version` is a PROFILE field, so re-rendering does not change it: a FAIL here
    could not be cleared by following its own advice, and a FAIL that cannot be cleared
    is one people learn to scroll past. The fixtures pin 1.0.0 while the plugin is
    further on, which is exactly the case."""
    import json as _json
    root = install(tmp_path, load_fixture("python_monolith"))
    plugin_ver = _json.loads(
        (PLUGIN / ".claude-plugin/plugin.json").read_text())["version"]
    lock = root / ".claude/kit.lock.json"
    data = _json.loads(lock.read_text())
    assert data["kit_version"] != plugin_ver, "the fixture must differ for this to test"
    r = doctor(root)
    assert "kit version" in r.stdout
    assert "note" in r.stdout
    assert f"installed plugin is {plugin_ver}" in r.stdout
    assert "FAIL" not in r.stdout, r.stdout
    assert r.returncode == 0


def test_a_matching_kit_version_draws_no_note(tmp_path, load_fixture):
    import json as _json
    root = install(tmp_path, load_fixture("python_monolith"))
    plugin_ver = _json.loads(
        (PLUGIN / ".claude-plugin/plugin.json").read_text())["version"]
    lock = root / ".claude/kit.lock.json"
    data = _json.loads(lock.read_text())
    data["kit_version"] = plugin_ver
    lock.write_text(_json.dumps(data, indent=2, sort_keys=True) + "\n")
    r = doctor(root)
    assert f"kit version                        ok      {plugin_ver}" in r.stdout
    assert r.returncode == 0


def test_the_doctor_says_whether_the_usage_pause_is_armed(tmp_path, load_fixture):
    """The gate is only as live as the status-line probe feeding it, and an unwired probe
    is indistinguishable from a healthy kit — which is exactly the class of invisible
    off-switch this script exists for."""
    root = install(tmp_path, load_fixture("python_monolith"))
    import os as _os
    env_absent = dict(PATH="/usr/bin:/bin", CLAUDE_PROJECT_DIR=str(root),
                      CLAUDE_KIT_USAGE_FILE=str(tmp_path / "absent.json"))
    r = subprocess.run(["bash", str(DOCTOR)], capture_output=True, text=True,
                       env=env_absent)
    assert "usage pause" in r.stdout and "note" in r.stdout
    assert "not wired" in r.stdout
    assert "FAIL" not in r.stdout, "an unwired probe is a judgement call, not a failure"

    snap = tmp_path / "u.json"
    snap.write_text(json.dumps({"read_at": int(__import__("time").time()),
                                "five_hour": {"used_percentage": 12.7,
                                              "resets_at": 1}}))
    r = subprocess.run(["bash", str(DOCTOR)], capture_output=True, text=True,
                       env={**env_absent, "CLAUDE_KIT_USAGE_FILE": str(snap)})
    assert "armed" in r.stdout and "5h 12%" in r.stdout
    assert r.returncode == 0


def test_the_doctor_flags_a_stale_usage_reading(tmp_path, load_fixture):
    root = install(tmp_path, load_fixture("python_monolith"))
    snap = tmp_path / "u.json"
    snap.write_text(json.dumps({"read_at": int(__import__("time").time()) - 9000,
                                "five_hour": {"used_percentage": 99, "resets_at": 1}}))
    r = subprocess.run(["bash", str(DOCTOR)], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root),
                            "CLAUDE_KIT_USAGE_FILE": str(snap)})
    assert "fails OPEN" in r.stdout
    assert r.returncode == 0, "a stale reading is a note, not a failure"
