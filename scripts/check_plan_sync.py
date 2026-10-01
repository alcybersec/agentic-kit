#!/usr/bin/env python3
"""Assert every committed template is byte-identical to its block in the plan.

The plan is the authority the next task is written against, so a template that has
drifted from it is worse than no plan at all. Run this after any template change.

Uses a fence-length-aware scanner: CONTRACTS.md.j2 contains its own ```json fence,
and the obvious regex ```jinja\\n(.*?)``` truncates at it silently -- which it did,
once, leaving a short copy in the plan and an orphaned tail that swallowed the next
block's opening fence.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fences import blocks  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs/superpowers/plans/2026-09-30-agentic-kit-m1.md"
TPL = ROOT / "plugins/agentic-kit/kitgen/src/kitgen/templates"

# (task heading, next heading, index within that task's jinja blocks, template name)
EXPECTED = [
    ("## Task 4:", "## Task 5:", 0, "CLAUDE.md.j2"),
    ("## Task 5:", "## Task 6:", 0, "role.md.j2"),
    ("## Task 5:", "## Task 6:", 1, "orchestrator.md.j2"),
    ("## Task 5:", "## Task 6:", 2, "MEMORY.md.j2"),
    ("## Task 6:", "## Task 7:", 0, "settings.json.j2"),
    ("## Task 7:", "## Task 8:", 0, "strategy.md.j2"),
    ("## Task 7:", "## Task 8:", 1, "plan.md.j2"),
    ("## Task 7:", "## Task 8:", 2, "design.md.j2"),
    ("## Task 7:", "## Task 8:", 3, "decisions.md.j2"),
    ("## Task 7:", "## Task 8:", 4, "risk-register.md.j2"),
    ("## Task 7:", "## Task 8:", 5, "CONTRACTS.md.j2"),
    ("## Task 7:", "## Task 8:", 6, "adr-0001.md.j2"),
]


def main() -> int:
    plan = PLAN.read_text()
    bad = []
    for start, end, idx, name in EXPECTED:
        section = plan[plan.index(start):plan.index(end)]
        found = [t for t, _, _ in blocks(section, "jinja")]
        if idx >= len(found):
            bad.append(f"{name}: {start[:-1]} has {len(found)} jinja blocks, need index {idx}")
            continue
        if found[idx] != (TPL / name).read_text():
            bad.append(f"{name}: differs from its block in {start[:-1]}")
    for line in bad:
        print(f"  {line}")
    print(f"{len(EXPECTED) - len(bad)}/{len(EXPECTED)} templates in sync with the plan")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
