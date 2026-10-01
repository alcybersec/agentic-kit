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


def test_resync_widens_the_fence_for_content_that_contains_one():
    """A block whose body holds ``` cannot be delimited by ```: the inner fence ends
    the outer one, the plan keeps a truncated copy, and the orphaned tail swallows
    what follows. That happened twice in this build — once to CONTRACTS.md.j2 and
    once when CLAUDE.md.j2 gained a command block — so the fence is computed from the
    content rather than carried over."""
    resync = _load("resync")
    assert resync.fence_for("no fences here", "```") == "```"
    assert resync.fence_for("holds a ```json block\n```\n", "```") == "````"
    assert resync.fence_for("holds a ````wide block\n````\n", "```") == "`````"
    # An opener with a language does NOT close a block, so it forces no widening —
    # otherwise every template mentioning ```bash would churn the plan.
    assert resync.fence_for("see ```bash for the shape", "```") == "```"
    # Never narrows: an already-wide block stays wide.
    assert resync.fence_for("plain", "````") == "````"


def test_every_plan_block_fence_contains_its_body():
    """The invariant the helper exists to keep, asserted over the real plan."""
    fences = _load("fences")
    import re
    plan = (REPO / "docs/superpowers/plans/2026-09-30-agentic-kit-m1.md").read_text()
    for body, fence, lang in fences.blocks(plan):
        # A BARE fence line is the only thing that closes a block; `` ```json `` is
        # an opener and passes through. So this is the exact truncation condition.
        longest = max((len(m) for m in re.findall(r"^(`{3,})[ \t]*$", body, re.M)),
                      default=0)
        assert longest < len(fence), (
            f"a ```{lang} block delimited by {len(fence)} backticks contains a bare "
            f"fence of {longest}: everything after it is outside the block")
