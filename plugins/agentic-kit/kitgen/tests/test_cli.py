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
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
               "--dry-run"])
    assert rc == 0
    assert not (tmp_path / "CLAUDE.md").exists()
    assert "CLAUDE.md" in json.loads(capsys.readouterr().out)["manifest"]


def test_verification_failure_writes_nothing(tmp_path, capsys):
    """Verify BEFORE writing. The spine docs are absent, so verify() fails; a
    half-written kit is worse than none, so the tree must be left untouched."""
    before = _tree(tmp_path)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    assert rc == 1
    assert "docs/PRD.md" in capsys.readouterr().err
    assert _tree(tmp_path) == before == set()


def test_lock_is_written_after_kit_yaml(tmp_path):
    """Spec 5.1: mtime(kit.yaml) > mtime(kit.lock.json) means hand-edited drift, so a
    clean install must leave the lock at least as new as the yaml."""
    _seed_spine(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 0
    y = (tmp_path / ".claude/kit.yaml").stat().st_mtime_ns
    l = (tmp_path / ".claude/kit.lock.json").stat().st_mtime_ns
    assert l >= y


def test_hook_scripts_are_executable(tmp_path, capsys):
    """Every manifest path under .claude/hooks/ must be executable once written.
    VACUOUS today: render() emits no hook yet (Task 12b adds ownership-guard.sh),
    so this asserts over an empty set. It becomes meaningful when 12b lands."""
    _seed_spine(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]) == 0
    written = json.loads(capsys.readouterr().out)["written"]
    for rel in (p for p in written if p.startswith(".claude/hooks/")):
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
    assert os.access(tmp_path / ".claude/hooks/ownership-guard.sh", os.X_OK)
    assert not os.access(tmp_path / "CLAUDE.md", os.X_OK)
