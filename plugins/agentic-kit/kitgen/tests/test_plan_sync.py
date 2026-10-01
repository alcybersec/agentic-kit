# plugins/agentic-kit/kitgen/tests/test_plan_sync.py
"""The plan and the templates must stay byte-identical, and the suite must say so.

`scripts/check_plan_sync.py` existed and nothing ran it: the plan was verified by
hand, which is exactly the kind of check that rots. Worse, its `EXPECTED` list is
hardcoded, so a FOURTEENTH template would be silently unchecked — the drift it
exists to catch would be invisible in precisely the case where someone is adding
new code.

This also matters beyond tidiness. The plan is the document a future reader
follows to rebuild the kit, and the build already produced one template that was
committed truncated with every test green.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPTS = REPO / "scripts"
TEMPLATES = Path(__file__).resolve().parents[1] / "src/kitgen/templates"


def _load(name):
    """Import a script from scripts/ without making it a package."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    # check_plan_sync imports `fences` as a sibling.
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)
    return mod


def test_every_template_is_byte_identical_to_its_block_in_the_plan(capsys):
    cps = _load("check_plan_sync")
    rc = cps.main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert f"{len(cps.EXPECTED)}/{len(cps.EXPECTED)} templates in sync" in out


def test_the_sync_check_covers_every_template_on_disk():
    """The gap that made the check weaker than it looked: `EXPECTED` is a literal
    list, so a new template is not unchecked-and-reported, it is unchecked-and-
    silent. Adding one must now break this test until its plan block exists."""
    cps = _load("check_plan_sync")
    checked = {name for _, _, _, name in cps.EXPECTED}
    on_disk = {p.name for p in TEMPLATES.iterdir() if p.suffix == ".j2"}
    assert checked == on_disk, (
        f"not checked against the plan: {sorted(on_disk - checked)}; "
        f"checked but absent from templates/: {sorted(checked - on_disk)}")


def test_the_sync_check_covers_every_template_render_uses():
    """And the other direction: a template in `SINGLETONS` or rendered per role
    that nobody checks."""
    from kitgen.render import SINGLETONS
    cps = _load("check_plan_sync")
    checked = {name for _, _, _, name in cps.EXPECTED}
    used = set(SINGLETONS) | {"role.md.j2", "MEMORY.md.j2"}
    assert used <= checked, sorted(used - checked)


def test_the_fence_scanner_survives_a_nested_code_fence():
    """The regex this replaced truncated any template containing a fence of its
    own, which silently wrote a short copy into the plan and orphaned the tail.
    CONTRACTS.md.j2 contains a ```json block, so the plan holds a live example."""
    fences = _load("fences")
    text = ('````jinja\n'
            'outer line\n'
            '```json\n'
            '{"inner": true}\n'
            '```\n'
            'after the inner fence\n'
            '````\n')
    blocks = fences.blocks(text)
    assert len(blocks) == 1
    body = blocks[0][0]
    assert "after the inner fence" in body
    assert '{"inner": true}' in body


@pytest.mark.parametrize("name", ["check_plan_sync", "resync", "fences"])
def test_the_sync_tooling_is_importable(name):
    """Each of these broke at least once during the build; an ImportError in the
    tool that guards the plan is a silent loss of the guard."""
    assert _load(name) is not None
