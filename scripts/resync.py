#!/usr/bin/env python3
"""Resync a plan task's fenced blocks from the committed files they describe.

Matches a block to a file ONLY when the block's first line is a path comment for
it -- `# <path>` or `#!/...` followed by that path. Matching the path anywhere in
the first line clobbers prose: a `git add <path>` snippet in the same task was
once replaced with the whole hook body, because the command names the file too.

Usage: resync.py "## Task 11:" "## Task 12:" <repo-relative-path>...
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fences import blocks  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs/superpowers/plans/2026-09-30-agentic-kit-m1.md"


def first_line_names(first: str, rel: str) -> bool:
    """True only when the block's opening line is a path comment for `rel`."""
    stripped = first.strip()
    return stripped in (f"# {rel}", f"# {rel.split('/')[-1]}")


def main(argv: list[str]) -> int:
    start, end, *rels = argv
    plan = PLAN.read_text()
    a, b = plan.index(start), plan.index(end)
    sec = plan[a:b]
    changed = []
    for rel in rels:
        live = (ROOT / rel).read_text()
        for body, fence, lang in blocks(sec):
            lines = body.splitlines()
            if not lines or not first_line_names(lines[0], rel):
                continue
            new = body if body.startswith(lines[0] + "\n") and lines[0] in live else lines[0] + "\n" + live
            if live.startswith(lines[0]):
                new = live
            if body != new:
                sec = sec.replace(f"{fence}{lang}\n{body}{fence}",
                                  f"{fence}{lang}\n{new}{fence}", 1)
                changed.append(f"{rel}: {len(lines)} -> {len(new.splitlines())} lines")
            break
        else:
            print(f"  WARNING: no block in {start[:-1]} opens with a path comment for {rel}")
    PLAN.write_text(plan[:a] + sec + plan[b:])
    for c in changed:
        print(f"  resynced {c}")
    print(f"{len(changed)} block(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
