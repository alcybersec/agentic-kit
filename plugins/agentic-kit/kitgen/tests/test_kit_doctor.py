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

DOCTOR = __import__("pathlib").Path(__file__).resolve().parents[2] / "bin/kit-doctor.sh"


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


def doctor(root):
    return subprocess.run(["bash", str(DOCTOR)], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)})


@pytest.mark.parametrize("fixture", ["python_monolith", "services_layout"])
def test_a_correctly_installed_kit_passes_every_check(tmp_path, load_fixture, fixture):
    r = doctor(install(tmp_path, load_fixture(fixture)))
    assert "FAIL" not in r.stdout, r.stdout
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all checks passed" in r.stdout


def test_a_disarmed_ownership_guard_is_reported(tmp_path, load_fixture):
    """The failure the whole script exists for: a guard that runs, exits 0 and
    protects nothing looks identical to a correctly inert one."""
    root = install(tmp_path, load_fixture("services_layout"))
    (root / ".claude/hooks/ownership-guard.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    r = doctor(root)
    assert r.returncode == 1
    assert "ALLOWED a payload that must be refused" in r.stdout


def test_a_guard_that_is_not_executable_is_reported(tmp_path, load_fixture):
    root = install(tmp_path, load_fixture("services_layout"))
    (root / ".claude/hooks/ownership-guard.sh").chmod(0o644)
    r = doctor(root)
    assert r.returncode == 1 and "not +x" in r.stdout


def test_a_role_card_that_does_not_register_the_guard_is_reported(tmp_path, load_fixture):
    """The other half: a working script nobody registers never runs."""
    root = install(tmp_path, load_fixture("services_layout"))
    card = root / ".claude/agents/architect.md"
    card.write_text("\n".join(l for l in card.read_text().splitlines()
                              if "ownership-guard.sh" not in l) + "\n")
    r = doctor(root)
    assert r.returncode == 1
    assert "not referenced by the card for: architect" in r.stdout


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


def test_a_missing_hook_script_is_reported(tmp_path, load_fixture):
    root = install(tmp_path, load_fixture("python_monolith"))
    (root / ".claude/hooks/ownership-guard.sh").unlink()
    r = doctor(root)
    assert r.returncode == 1 and "absent" in r.stdout


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
