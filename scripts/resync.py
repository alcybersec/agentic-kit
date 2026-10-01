#!/usr/bin/env python3
"""Resync a plan task's fenced blocks from the committed files they describe.

Matches a block to a file ONLY when the block's first line is a path comment for
it -- `# <path>` or `#!/...` followed by that path. Matching the path anywhere in
the first line clobbers prose: a `git add <path>` snippet in the same task was
once replaced with the whole hook body, because the command names the file too.

Usage: resync.py "## Task 11:" "## Task 12:" <repo-relative-path>...
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fences import blocks  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# A positional `N:path` spec names a block by index, and an index that is off by one
# silently rewrites a neighbouring block: a 69-line Python test block was once
# replaced with a 118-line Jinja template, and check_plan_sync.py could not see it
# because it only ever looks at the indices it expects. The fence language is the
# cheap cross-check -- it has to agree with the file's own kind.
FENCE_LANG = {".j2": "jinja", ".py": "python", ".sh": "bash", ".json": "json",
              ".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml"}


def fence_for(content: str, current: str) -> str:
    """A fence long enough to contain `content`.

    A block whose body holds ``` cannot be delimited by ``` — the inner fence ends
    the outer one, the plan keeps a truncated copy, and the orphaned tail swallows
    whatever follows. That happened twice in this build, so the fence is computed
    from the content rather than carried over from the block being replaced.
    """
    # Only a line that is backticks ALONE closes a block (see fences.py), so an
    # opener like ```json inside the body is harmless and must not force a widening
    # that would churn the plan.
    longest = max((len(m) for m in re.findall(r"^(`{3,})[ \t]*$", content, re.M)),
                  default=0)
    return "`" * max(len(current), longest + 1, 3)
PLAN = ROOT / "docs/superpowers/plans/2026-09-30-agentic-kit-m1.md"


def first_line_names(first: str, rel: str) -> bool:
    """True only when the block's opening line is a path comment for `rel`."""
    stripped = first.strip()
    return stripped in (f"# {rel}", f"# {rel.split('/')[-1]}")


def main(argv: list[str]) -> int:
    start, end, *specs = argv
    plan = PLAN.read_text()
    a, b = plan.index(start), plan.index(end)
    sec = plan[a:b]
    changed = []
    missed = []

    # "N:path" addresses the Nth fenced block positionally. Template blocks are
    # introduced by surrounding prose, so their first line is template content
    # (`---`, `#!/usr/bin/env bash`) rather than a path comment, and there is
    # nothing in them to match on.
    for spec in [x for x in specs if ":" in x]:
        idx_s, rel = spec.split(":", 1)
        idx = int(idx_s)
        live = (ROOT / rel).read_text()
        found = [(t, f, l) for t, f, l in blocks(sec)]
        if idx >= len(found):
            missed.append(f"{start[:-1]} has {len(found)} blocks, need index {idx}")
            continue
        body, fence, lang = found[idx]
        new_fence = fence_for(live, fence)
        want = FENCE_LANG.get(pathlib.Path(rel).suffix)
        if want and lang != want:
            missed.append(
                f"{start[:-1]} block {idx} is a ```{lang or '(none)'} block, but "
                f"{rel} belongs in a ```{want} one -- refusing to overwrite it. "
                f"Check the index against check_plan_sync.py's table.")
            continue
        if body != live or new_fence != fence:
            sec = sec.replace(f"{fence}{lang}\n{body}{fence}",
                              f"{new_fence}{lang}\n{live}{new_fence}", 1)
            note = "" if new_fence == fence else f", fence {len(fence)}->{len(new_fence)}"
            changed.append(f"{rel}: {len(body.splitlines())} -> "
                           f"{len(live.splitlines())} lines{note}")

    rels = [x for x in specs if ":" not in x]
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
            missed.append(f"no block in {start[:-1]} opens with a path comment "
                          f"for {rel} -- a template block has no path comment to "
                          f"match, so address it positionally as N:{rel}")
    PLAN.write_text(plan[:a] + sec + plan[b:])
    for c in changed:
        print(f"  resynced {c}")
    for m in missed:
        print(f"  WARNING: {m}")
    print(f"{len(changed)} block(s) updated")
    # A spec that matched nothing exits non-zero. It used to warn and return 0,
    # so a mis-addressed template looked like "already in sync" and the drift was
    # only caught by check_plan_sync.py on a later run.
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
