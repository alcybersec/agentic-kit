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


@pytest.mark.parametrize("extra", [[], ["--force"]])
def test_a_directory_at_a_manifest_path_is_refused(tmp_path, extra):
    """Still 3, but as a blocker rather than a clash: --force clears a clash, and
    a directory cannot be written over, so clearing this one would mean deleting
    it. Both forms must refuse."""
    _seed_spine(tmp_path)
    (tmp_path / "CLAUDE.md").mkdir()
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)]
                + extra) == 3


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


def test_a_directory_where_a_file_belongs_is_refused_before_any_write(tmp_path, capsys):
    """Used to exit 4 after writing 14 files, including the lock. `write_text`
    cannot overwrite a directory, and --force must not delete one to make room,
    so the preflight refuses with 3 and the tree is left untouched (§7.1b)."""
    _seed_spine(tmp_path)
    (tmp_path / ".claude/agents/backend.md").mkdir(parents=True)
    before = _tree(tmp_path)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path), "--force"])
    err = capsys.readouterr().err
    assert rc == 3
    assert ".claude/agents/backend.md" in err
    assert "--force does not remove these" in err
    assert _tree(tmp_path) == before


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


@pytest.mark.parametrize("extra", [[], ["--force"]])
def test_a_file_where_a_parent_directory_belongs_is_refused(tmp_path, capsys, extra):
    """`mkdir` cannot create a directory under a regular file. The old behaviour
    exited 4 partway through; a `.claude` that is a file now blocks every path
    beneath it and is reported once, by the directory, not eleven times."""
    _seed_spine(tmp_path)
    (tmp_path / ".claude").write_text("i am a file")
    before = _tree(tmp_path)
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)] + extra)
    err = capsys.readouterr().err
    assert rc == 3
    assert "['.claude']" in err, "reported once, by the directory, not per path"
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("make", [
    lambda root: (root / ".claude").write_text("a file where a directory goes"),
    lambda root: (root / ".claude/agents/backend.md").mkdir(parents=True),
    lambda root: (root / "docs/adr").symlink_to("nowhere-at-all"),
])
def test_dry_run_predicts_a_blocked_tree(tmp_path, capsys, make):
    """§7.1b: `--dry-run` returns the code the real run would return. These three
    obstructions were invisible to the preflight, so the preview said 0 for a run
    that failed partway with 4 -- including the broken symlink, which `exists()`
    reports as absent while `mkdir` still refuses it."""
    _seed_spine(tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    make(tmp_path)
    before = _tree(tmp_path)
    dry = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                "--dry-run", "--force"])
    assert json.loads(capsys.readouterr().out)["blocked"] != []
    real = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--force"])
    capsys.readouterr()
    assert dry == real == 3
    assert _tree(tmp_path) == before


# --- §7.1a: --force replaces scaffolding, it does not discard the project's work ---

def _seed_living(root: Path) -> dict[str, str]:
    """Put a distinctive sentence in every file `--force` must not clobber.

    These are the files a project writes into: five living spine documents, two
    generate-once files, and per-role memory. CLAUDE.md tells the user to
    re-render after every plugin update, so this is the ordinary path, not a
    corner case.
    """
    seeded = {
        "docs/strategy.md": "M0-S1-BACK-004 hand-expanded at the gate",
        "docs/design.md": "the ledger writes through a single append path",
        "docs/decisions.md": "| 0002 | drop the cache layer | Accepted |",
        "docs/CONTRACTS.md": "POST /entries -> 201 {id}",
        "docs/risk-register.md": "| R-013 | peer edits during a sweep | high |",
        "docs/plan/README.md": "dispatch state after task 4",
        "docs/adr/0001-adopt-agentic-kit.md": "Accepted 2026-09-01, kit 1.0.0",
        ".claude/agent-memory/backend/MEMORY.md": "- alembic autogenerate lies here",
    }
    for rel, text in seeded.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return seeded


def test_force_keeps_every_living_and_generate_once_file(tmp_path, capsys):
    """The failure this pins was an amputation, not a diff: a re-render restored
    the empty scaffold over five documents of accumulated project content, and
    over every role's memory. The orphan state is the worst of it -- blanking
    `decisions.md` leaves `docs/adr/0002-*.md` on disk with nothing pointing at
    it, so the project reads as though the decision was never recorded."""
    _seed_spine(tmp_path)
    seeded = _seed_living(tmp_path)
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--force"]) == 0
    for rel, text in seeded.items():
        assert (tmp_path / rel).read_text() == text, rel
    err = capsys.readouterr().err
    for rel in seeded:
        assert rel in err, f"the skip must be named, not silent: {rel}"


def test_force_does_overwrite_the_generated_scaffolding(tmp_path, capsys):
    """The other half of the contract. Preserving too much is also a defect: a
    profile change that never reaches CLAUDE.md, the role cards, settings or the
    lock leaves the kit describing a project it no longer configures."""
    _seed_spine(tmp_path)
    scaffold = ["CLAUDE.md", ".claude/settings.json", ".claude/kit.lock.json",
                ".claude/kit.yaml", ".claude/agents/orchestrator.md",
]
    for rel in scaffold:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("STALE")
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--force"]) == 0
    for rel in scaffold:
        assert (tmp_path / rel).read_text() != "STALE", rel
    err = capsys.readouterr().err
    for rel in scaffold:
        assert rel in err, f"--force must name what it overwrote: {rel}"


def test_dry_run_predicts_the_force_split(tmp_path, capsys):
    """§7.1b: a preview that disagrees with the real run is worse than none."""
    _seed_spine(tmp_path)
    seeded = _seed_living(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("STALE")
    assert main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
                 "--dry-run", "--force"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["clashes"] == []
    assert out["frozen"] == sorted(seeded)
    assert out["overwrite"] == ["CLAUDE.md"]
    for rel, text in seeded.items():
        assert (tmp_path / rel).read_text() == text, rel
    assert (tmp_path / "CLAUDE.md").read_text() == "STALE"
