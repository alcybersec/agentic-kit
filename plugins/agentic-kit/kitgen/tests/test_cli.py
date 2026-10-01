# plugins/agentic-kit/kitgen/tests/test_cli.py
import json
import os
from pathlib import Path

import pytest

from kitgen.cli import main

FIXTURE = Path(__file__).parent / "fixtures/services_layout/profile.yaml"


def _seed_spine(root: Path) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs/PRD.md").write_text("prd")
    (root / "docs/architecture.md").write_text("arch")


def _tree(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_render_writes_the_manifest_to_a_target_tree(tmp_path, capsys):
    _seed_spine(tmp_path)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".claude/kit.lock.json").exists()
    assert (tmp_path / ".claude/agents/safety.md").exists()
    written = json.loads(capsys.readouterr().out)["written"]
    assert "CLAUDE.md" in written


def test_force_still_keeps_generate_once_files(tmp_path, capsys):
    """plan/README.md is the dispatch state after the first task, and adr-0001 stamps
    the install's date and kit version. --force must not restamp an Accepted ADR or
    delete the record of what has been dispatched."""
    _seed_spine(tmp_path)
    for p in ("docs/adr", "docs/plan"):
        (tmp_path / p).mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs/plan/README.md").write_text("MY DISPATCH STATE")
    (tmp_path / "docs/adr/0001-adopt-agentic-kit.md").write_text("ACCEPTED 2026-01-01")
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path), "--force"])
    assert rc == 0
    assert (tmp_path / "docs/plan/README.md").read_text() == "MY DISPATCH STATE"
    assert (tmp_path / "docs/adr/0001-adopt-agentic-kit.md").read_text() == "ACCEPTED 2026-01-01"
    assert (tmp_path / "CLAUDE.md").exists()   # everything else still re-rendered
    written = json.loads(capsys.readouterr().out)["written"]
    assert "docs/plan/README.md" not in written


def test_force_writes_generate_once_files_when_absent(tmp_path):
    """--force protects existing history; it must not leave a fresh install without them."""
    _seed_spine(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--force"]) == 0
    assert (tmp_path / "docs/plan/README.md").exists()
    assert (tmp_path / "docs/adr/0001-adopt-agentic-kit.md").exists()


def test_render_refuses_to_overwrite_without_force(tmp_path, capsys):
    _seed_spine(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("existing")
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    assert rc == 3
    assert (tmp_path / "CLAUDE.md").read_text() == "existing"
    assert "refusing to overwrite" in capsys.readouterr().err


def test_refusal_writes_nothing_else(tmp_path):
    _seed_spine(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("existing")
    before = _tree(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 3
    assert _tree(tmp_path) == before


def test_dry_run_writes_nothing_and_prints_the_manifest(tmp_path, capsys):
    _seed_spine(tmp_path)
    before = _tree(tmp_path)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
               "--dry-run"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "CLAUDE.md" in out["manifest"]
    assert out["clashes"] == [] and out["frozen"] == []
    assert _tree(tmp_path) == before


def test_dry_run_has_the_real_runs_verdict_on_verification_failure(tmp_path, capsys):
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path), "--dry-run"])
    assert rc == 1
    assert "docs/PRD.md" in capsys.readouterr().err
    assert _tree(tmp_path) == set()


def test_dry_run_reports_clashes_and_writes_nothing(tmp_path, capsys):
    _seed_spine(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("existing")
    before = _tree(tmp_path)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path), "--dry-run"])
    assert rc == 3   # same verdict as the real run
    assert json.loads(capsys.readouterr().out)["clashes"] == ["CLAUDE.md"]
    assert _tree(tmp_path) == before
    assert (tmp_path / "CLAUDE.md").read_text() == "existing"


def test_dry_run_with_force_reports_frozen_paths(tmp_path, capsys):
    _seed_spine(tmp_path)
    (tmp_path / "docs/plan").mkdir()
    (tmp_path / "docs/plan/README.md").write_text("STATE")
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
               "--dry-run", "--force"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["frozen"] == ["docs/plan/README.md"] and out["clashes"] == []
    assert (tmp_path / "docs/plan/README.md").read_text() == "STATE"


def test_verification_failure_writes_nothing(tmp_path, capsys):
    """Verify BEFORE writing. The spine docs are absent, so verify() fails; a
    half-written kit is worse than none, so the tree must be left untouched."""
    before = _tree(tmp_path)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    assert rc == 1
    assert "docs/PRD.md" in capsys.readouterr().err
    assert _tree(tmp_path) == before == set()


def test_lock_is_written_after_kit_yaml(tmp_path, capsys):
    """Spec 5.1: mtime(kit.yaml) > mtime(kit.lock.json) means hand-edited drift, so the
    CLI must write the yaml first. Asserted on the `written` list, which is in write
    order precisely because the CLI emits it unsorted (mtimes tie on coarse
    filesystems, so an mtime assertion cannot fail)."""
    _seed_spine(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 0
    written = json.loads(capsys.readouterr().out)["written"]
    assert written.index(".claude/kit.yaml") < written.index(".claude/kit.lock.json")


def test_hook_scripts_are_executable(tmp_path, capsys):
    """Every manifest path under .claude/hooks/ must be executable once written.
    Non-vacuous since Task 12b: ownership-guard.sh is in the manifest, and the
    assert below pins that so this can never silently go back to an empty set."""
    _seed_spine(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 0
    written = json.loads(capsys.readouterr().out)["written"]
    hooks = [p for p in written if p.startswith(".claude/hooks/")]
    assert ".claude/hooks/ownership-guard.sh" in hooks
    for rel in hooks:
        assert os.access(tmp_path / rel, os.X_OK), rel


def test_verify_reports_problems_and_exits_nonzero(tmp_path, capsys):
    rc = main(["verify", "--profile", str(FIXTURE), "--root", str(tmp_path)])
    assert rc == 1
    assert "docs/PRD.md" in capsys.readouterr().out


def test_invalid_profile_exits_two(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("kit_version: 1.0.0\n")
    rc = main(["verify", "--profile", str(bad), "--root", str(tmp_path)])
    assert rc == 2


def test_unparseable_yaml_exits_two(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("kit_version: [1.0.0\n")
    assert main(["verify", "--profile", str(bad), "--root", str(tmp_path)]) == 2
    assert "invalid profile" in capsys.readouterr().err


def test_a_scalar_where_a_mapping_belongs_exits_two(tmp_path, capsys):
    """Regression: this path raised a bare ValueError from dict(), which is not a
    ConfigError, so it escaped the handler and exited 1 instead of 2."""
    import yaml as _yaml
    raw = _yaml.safe_load(FIXTURE.read_text())
    raw["spine"] = "docs/strategy.md"
    bad = tmp_path / "bad.yaml"
    bad.write_text(_yaml.safe_dump(raw))
    assert main(["verify", "--profile", str(bad), "--root", str(tmp_path)]) == 2
    assert "spine" in capsys.readouterr().err


def test_hook_chmod_is_exercised_with_a_synthetic_hook(tmp_path, monkeypatch):
    """Non-vacuous companion to the test above: inject a hook into the manifest."""
    import kitgen.cli as cli
    real = cli.render
    monkeypatch.setattr(cli, "render", lambda cfg: {
        **real(cfg), ".claude/hooks/ownership-guard.sh": "#!/bin/sh\nexit 0\n"})
    _seed_spine(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 0
    mode = (tmp_path / ".claude/hooks/ownership-guard.sh").stat().st_mode
    assert mode & 0o111 == 0o111          # executable by everyone
    assert mode & 0o600 == 0o600          # and still readable/writable by the owner
    assert not os.access(tmp_path / "CLAUDE.md", os.X_OK)


def test_frozen_message_is_on_stderr_and_names_both_paths(tmp_path, capsys):
    _seed_spine(tmp_path)
    for p in ("docs/adr", "docs/plan"):
        (tmp_path / p).mkdir(parents=True)
    (tmp_path / "docs/plan/README.md").write_text("S")
    (tmp_path / "docs/adr/0001-adopt-agentic-kit.md").write_text("A")
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--force"]) == 0
    cap = capsys.readouterr()
    assert "docs/plan/README.md" in cap.err
    assert "docs/adr/0001-adopt-agentic-kit.md" in cap.err
    assert "docs/plan/README.md" not in cap.out


def test_refusal_names_every_clashing_path(tmp_path, capsys):
    _seed_spine(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("x")
    (tmp_path / "docs/strategy.md").write_text("y")
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 3
    err = capsys.readouterr().err
    assert "CLAUDE.md" in err and "docs/strategy.md" in err


def test_a_directory_at_a_manifest_path_is_a_clash(tmp_path):
    _seed_spine(tmp_path)
    (tmp_path / "CLAUDE.md").mkdir()
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 3


def test_missing_profile_file_exits_two(tmp_path, capsys):
    assert main(["verify", "--profile", str(tmp_path / "nope.yaml"),
                 "--root", str(tmp_path)]) == 2
    assert "FileNotFoundError" in capsys.readouterr().err


@pytest.mark.parametrize("body", ["", "- a\n- b\n", "just a string\n"])
def test_non_mapping_profile_exits_two(tmp_path, body):
    bad = tmp_path / "bad.yaml"
    bad.write_text(body)
    assert main(["verify", "--profile", str(bad), "--root", str(tmp_path)]) == 2


def test_verify_on_a_clean_tree_exits_zero(tmp_path, capsys):
    _seed_spine(tmp_path)
    assert main(["verify", "--profile", str(FIXTURE), "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_verify_root_is_honoured(tmp_path, monkeypatch):
    """--root, not the cwd, decides where the inherited docs are looked for."""
    (tmp_path / "proj").mkdir()
    _seed_spine(tmp_path / "proj")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert main(["verify", "--profile", str(FIXTURE), "--root", str(tmp_path / "proj")]) == 0
    assert main(["verify", "--profile", str(FIXTURE), "--root", str(elsewhere)]) == 1


# --- --rendered-on --------------------------------------------------------------

def test_rendered_on_reaches_the_adr_and_the_lock(tmp_path):
    _seed_spine(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--rendered-on", "2031-02-03"]) == 0
    assert "2031-02-03" in (tmp_path / "docs/adr/0001-adopt-agentic-kit.md").read_text()
    assert "2031-02-03" in (tmp_path / ".claude/kit.lock.json").read_text()


@pytest.mark.parametrize("bad", ["not-a-date", "2031-13-45", ""])
def test_bad_rendered_on_exits_two_and_writes_nothing(tmp_path, capsys, bad):
    _seed_spine(tmp_path)
    before = _tree(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--rendered-on", bad]) == 2
    assert repr(bad) in capsys.readouterr().err
    assert _tree(tmp_path) == before


# --- write failures: exit 4 -----------------------------------------------------

def test_write_failure_on_a_readonly_directory_exits_four(tmp_path, capsys):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    _seed_spine(tmp_path)
    agents = tmp_path / ".claude/agents"
    agents.mkdir(parents=True)
    agents.chmod(0o555)
    try:
        rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    finally:
        agents.chmod(0o755)
    err = capsys.readouterr().err
    assert rc == 4
    assert ".claude/agents/" in err and "PermissionError" in err
    assert "CLAUDE.md" in err            # an already-written file is listed
    assert "--force" in err


def test_write_failure_on_a_directory_where_a_file_belongs_exits_four(tmp_path, capsys):
    _seed_spine(tmp_path)
    (tmp_path / ".claude/agents/backend.md").mkdir(parents=True)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path), "--force"])
    err = capsys.readouterr().err
    assert rc == 4
    assert "write failed at .claude/agents/backend.md" in err
    assert "IsADirectoryError" in err
    assert ".claude/kit.lock.json" in err   # written before the failure, so listed
    assert "--force" in err


def test_attribute_error_inside_validation_exits_two(tmp_path, capsys):
    """roles[0].owns as a list of ints trips an AttributeError in from_dict, which is
    neither a ValueError nor a TypeError."""
    import yaml as _yaml
    raw = _yaml.safe_load(FIXTURE.read_text())
    raw["roles"][0]["owns"] = [1]
    bad = tmp_path / "bad.yaml"
    bad.write_text(_yaml.safe_dump(raw))
    assert main(["verify", "--profile", str(bad), "--root", str(tmp_path)]) == 2
    assert "AttributeError" in capsys.readouterr().err


def test_write_failure_creating_a_parent_directory_exits_four(tmp_path, capsys):
    """A regular file where a directory belongs fails in mkdir, not write_text."""
    _seed_spine(tmp_path)
    (tmp_path / ".claude").write_text("i am a file")
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 4
    assert "write failed at .claude/" in err
    assert "CLAUDE.md" in err
