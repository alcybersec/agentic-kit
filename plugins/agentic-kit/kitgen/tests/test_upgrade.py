# plugins/agentic-kit/kitgen/tests/test_upgrade.py
"""The three things a re-render cannot tell you.

`--force` already replaces scaffolding and preserves everything living, and `/kit-doctor`
already reports a stale `kit_version`, lock drift, a leftover guard and a stale role card.
What was left over is exactly this module: orphans, sections a living document is missing,
and a role with nowhere to record its design.
"""
import json

import pytest

from kitgen.model import KitConfig
from kitgen.render import LIVING_KEYS, MANIFEST_RECORD, render
from kitgen.upgrade import (heading_drift, inspect, missing_role_sections, orphans)


def install(root, cfg):
    man = render(cfg)
    for rel, body in man.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    for rel in cfg.spine["inherited"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("inherited")
    return man


def test_a_freshly_rendered_tree_has_nothing_to_review(tmp_path, load_fixture):
    cfg = load_fixture("python_monolith")
    install(tmp_path, cfg)
    assert inspect(cfg, tmp_path) == []


def test_the_record_lists_what_was_written_but_not_itself(tmp_path, load_fixture):
    """A record that includes its own path reads as though the file were content rather
    than bookkeeping."""
    cfg = load_fixture("python_monolith")
    man = install(tmp_path, cfg)
    rec = json.loads((tmp_path / MANIFEST_RECORD).read_text())
    assert rec["kit_version"] == cfg.kit_version
    assert MANIFEST_RECORD not in rec["paths"]
    assert set(rec["paths"]) == set(man) - {MANIFEST_RECORD}


def test_a_relocated_spine_document_leaves_an_orphan_and_it_is_found(tmp_path, load_variant):
    """The case that motivated this: relocating `spine.strategy` leaves the old document
    behind, and the renderer never removes files — deliberately, since it cannot know
    whether the old one holds work."""
    before = load_variant("python_monolith")
    install(tmp_path, before)
    assert (tmp_path / "docs/strategy.md").is_file()

    after = load_variant("python_monolith", spine={**before.to_lock()["spine"],
                                                   "strategy": "docs/operating-model.md"},
                         load_order=[{"path": before.spine["plan"], "mode": "full"}])
    found = orphans(render(after), tmp_path)
    assert found == ["docs/strategy.md"], found
    msgs = inspect(after, tmp_path)
    assert any("docs/strategy.md" in m and "never removes files" in m for m in msgs)


def test_a_dead_rendered_guard_is_found(tmp_path, load_fixture):
    """Plugin 1.1.0 moved the ownership guard into the plugin and left the rendered copy
    behind: a file that looks like an enforcement hook and runs never."""
    cfg = load_fixture("python_monolith")
    install(tmp_path, cfg)
    (tmp_path / ".claude/hooks").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/hooks/ownership-guard.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    assert ".claude/hooks/ownership-guard.sh" in orphans(render(cfg), tmp_path)


def test_orphans_are_found_in_a_tree_that_predates_the_record(tmp_path, load_variant):
    """The enumerated bridge. The record makes detection exact from the render that writes
    it onwards, and cannot see before it existed — but both orphans that exist in the wild
    today predate it, so a list of paths earlier versions rendered is what finds them."""
    before = load_variant("python_monolith")
    install(tmp_path, before)
    (tmp_path / MANIFEST_RECORD).unlink()          # as an older render would have left it
    after = load_variant("python_monolith", spine={**before.to_lock()["spine"],
                                                   "strategy": "docs/operating-model.md"},
                         load_order=[{"path": before.spine["plan"], "mode": "full"}])
    msgs = inspect(after, tmp_path)
    assert any("docs/strategy.md" in m for m in msgs)
    assert any("predates the kit recording" in m and "not the same as complete" in m
               for m in msgs)


def test_a_living_document_missing_a_section_is_reported(tmp_path, load_fixture):
    """`--force` refuses to touch a living document, so a new section never appears by
    itself and nobody is told."""
    cfg = load_fixture("python_monolith")
    man = install(tmp_path, cfg)
    target = tmp_path / cfg.spine["decisions"]
    target.write_text(man[cfg.spine["decisions"]].replace("## Rulings", "## Our Own Heading"))
    drift = dict(heading_drift(man, cfg, tmp_path))
    assert drift[cfg.spine["decisions"]] == ["## Rulings"]
    assert any("will not touch it" in m for m in inspect(cfg, tmp_path))


def test_replacing_an_example_entry_is_use_not_drift(tmp_path, load_fixture):
    """The first version compared `###` headings too and reported
    `### orders.create v1` as missing from a project whose architect had correctly replaced
    the template's example with four real contracts. `###` is content in every living
    template — an example contract, a milestone block, a per-role section."""
    cfg = load_fixture("python_monolith")
    man = install(tmp_path, cfg)
    target = tmp_path / cfg.spine["contracts"]
    body = man[cfg.spine["contracts"]]
    assert "### " in body, "the template must carry an example for this to mean anything"
    target.write_text(body.replace("### orders.create v1", "### bus.OrderFilled v1"))
    assert heading_drift(man, cfg, tmp_path) == []
    assert inspect(cfg, tmp_path) == []


def test_a_heading_the_project_added_is_not_drift(tmp_path, load_fixture):
    cfg = load_fixture("python_monolith")
    man = install(tmp_path, cfg)
    target = tmp_path / cfg.spine["design"]
    target.write_text(man[cfg.spine["design"]] + "\n## Our own section\n\nnotes\n")
    assert heading_drift(man, cfg, tmp_path) == []


def test_a_role_added_later_has_nowhere_to_record_its_design(tmp_path, load_fixture):
    """Adding a role is the commonest reason to re-render, and design.md is living."""
    cfg = load_fixture("python_monolith")
    install(tmp_path, cfg)
    lock = cfg.to_lock()
    lock["roles"].append({"name": "search", "description": "Search service.",
                          "owns": ["src/ledger/search/**"], "handoff_extra": [],
                          "veto": False})
    grown = KitConfig.from_dict(lock)
    assert missing_role_sections(grown, tmp_path) == ["search"]
    assert any("no section for 'search'" in m for m in inspect(grown, tmp_path))


def test_the_version_delta_is_stated_once(tmp_path, load_fixture):
    cfg = load_fixture("python_monolith")
    install(tmp_path, cfg)
    rec = json.loads((tmp_path / MANIFEST_RECORD).read_text())
    rec["kit_version"] = "0.9.0"
    (tmp_path / MANIFEST_RECORD).write_text(json.dumps(rec))
    msgs = inspect(cfg, tmp_path)
    hit = [m for m in msgs if "0.9.0" in m]
    assert len(hit) == 1
    assert "living documents are kept either way" in hit[0]


def test_it_changes_nothing(tmp_path, load_fixture):
    """A report that writes is one nobody dares run."""
    cfg = load_fixture("python_monolith")
    install(tmp_path, cfg)
    before = {p: p.read_text() for p in tmp_path.rglob("*") if p.is_file()}
    inspect(cfg, tmp_path)
    assert {p: p.read_text() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_an_unreadable_record_does_not_crash_the_inspection(tmp_path, load_fixture):
    cfg = load_fixture("python_monolith")
    install(tmp_path, cfg)
    (tmp_path / MANIFEST_RECORD).write_text("{not json")
    msgs = inspect(cfg, tmp_path)
    assert isinstance(msgs, list)
