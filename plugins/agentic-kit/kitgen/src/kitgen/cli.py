# plugins/agentic-kit/kitgen/src/kitgen/cli.py
"""kitgen CLI. Exit codes:

    0  ok
    1  verification problems
    2  bad profile (or bad --rendered-on)
    3  refused to overwrite
    4  write failed partway; the tree is incomplete and a retry needs --force

Consumers invoke it without kitgen on PATH, via the plugin cache:

    uv run --project "${CLAUDE_PLUGIN_ROOT}/kitgen" kitgen render --profile <p> --out <dir>

--project builds its venv under the plugin cache on first use; a read-only plugin
cache is a real failure mode to report, not to fall back from silently.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import yaml
from jinja2 import UndefinedError

from .model import KitConfig
from .render import is_preserved, render
from .verify import verify

HOOKS_PREFIX = ".claude/hooks/"


def _blockers(out: Path, manifest: dict[str, str]) -> list[str]:
    """Existing paths that stand in the way and that `--force` must not remove.

    Two shapes, both of which make the write fail rather than overwrite:
    a non-directory where a parent directory has to be created (`mkdir` raises
    NotADirectoryError / FileExistsError), and a directory where a file has to be
    written (`write_text` raises IsADirectoryError).

    They are separated from clashes because clearing one means deleting a path
    the kit does not own, which is beyond "replace the generated scaffolding".
    Leaving them out of the preflight made `--dry-run --force` predict 0 for a
    run that exits 4 having already written part of the tree -- the one thing
    §7.1b says a preview must never do.
    """
    bad: set[str] = set()
    for rel in manifest:
        parts = rel.split("/")
        for depth in range(1, len(parts) + 1):
            sub = "/".join(parts[:depth])
            target = out / sub
            # `is_symlink` as well as `exists`: a broken symlink is invisible to
            # exists() and still makes both mkdir and write_text fail.
            if not (target.exists() or target.is_symlink()):
                break
            wants_dir = depth < len(parts)
            if target.is_dir() != wants_dir:
                bad.add(sub)
                break
    return sorted(bad)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kitgen")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a profile into a project tree")
    r.add_argument("--profile", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--rendered-on", default=None,
                   help="ISO date recorded in the kit; defaults to the profile's value")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--force", action="store_true",
                   help="overwrite generated files (generate-once files are still kept)")

    v = sub.add_parser("verify", help="check that the profile renders a consistent kit and that its "
                          "inherited docs are present on disk")
    v.add_argument("--profile", type=Path, required=True)
    v.add_argument("--root", type=Path, required=True)

    args = parser.parse_args(argv)

    # `is not None`, not truthiness: an explicit empty string is a caller mistake, not
    # "unset". The ADR is generate-once, so a bad stamp would be permanent.
    rendered_on = getattr(args, "rendered_on", None)
    if rendered_on is not None:
        try:
            datetime.date.fromisoformat(rendered_on)
        except ValueError:
            print(f"invalid --rendered-on {rendered_on!r}: expected an ISO date "
                  "(YYYY-MM-DD)", file=sys.stderr)
            return 2

    try:
        raw = yaml.safe_load(args.profile.read_text())
        if rendered_on is not None:
            raw["rendered_on"] = rendered_on
        cfg = KitConfig.from_dict(raw)
        manifest = render(cfg)
    except (ValueError, KeyError, TypeError, AttributeError, OSError,
            yaml.YAMLError, UndefinedError) as exc:
        # Deliberately broad: this block only loads and validates a profile and
        # renders it, so any of these means a bad profile. ValueError subsumes
        # ConfigError; UndefinedError is a template needing a field the profile
        # lacks. An uncaught exception would exit 1, which the calling skill reads
        # as "verification problems" -- a materially wrong diagnosis.
        print(f"invalid profile: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "verify":
        problems = verify(manifest, cfg, project_root=args.root)
        for p in problems:
            print(p)
        return 1 if problems else 0

    # Verify BEFORE touching the filesystem: a half-written kit is worse than none.
    # This runs for --dry-run too, so a preview has the same verdict as the real run.
    problems = verify(manifest, cfg, project_root=args.out)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    # A clash is a FILE where the manifest wants a file: --force overwrites it,
    # subject to is_preserved. Anything else in the way is a blocker, which
    # --force does not clear -- see _blockers.
    blockers = _blockers(args.out, manifest)
    clashes = sorted(p for p in manifest if (args.out / p).is_file())
    frozen: list[str] = []
    overwrite: list[str] = []
    if args.force:
        # --force still must not clobber a generate-once or living file: see
        # render.is_preserved. What remains is scaffolding, and it is listed
        # because "overwrite the generated files" is only reassuring when the
        # caller can see which files those turned out to be.
        frozen = sorted(p for p in clashes if is_preserved(p))
        overwrite = sorted(p for p in clashes if not is_preserved(p))
        clashes = []

    if args.dry_run:
        print(json.dumps({"manifest": sorted(manifest),
                          "clashes": clashes,
                          "frozen": frozen,
                          "overwrite": overwrite,
                          "blocked": blockers}, indent=2))
        return 3 if clashes or blockers else 0

    if blockers:
        print(f"refusing to write: {blockers} stand in the way -- a file where a "
              f"directory must be created, or a directory where a file must be "
              f"written. --force does not remove these, because they are not the "
              f"kit's to delete. Move or delete them by hand and re-run.",
              file=sys.stderr)
        return 3
    if clashes:
        print(f"refusing to overwrite: {clashes}", file=sys.stderr)
        return 3
    if frozen:
        print(f"keeping {len(frozen)} existing file(s) the project owns: {frozen}",
              file=sys.stderr)
        for p in frozen:
            del manifest[p]
    if overwrite:
        print(f"overwriting {len(overwrite)} generated file(s): {overwrite}",
              file=sys.stderr)

    # Manifest insertion order is the write order AND the order of the emitted
    # `written` list (tests assert on it): kit.yaml before kit.lock.json (spec 5.1
    # reads mtime(kit.yaml) > mtime(lock) as drift). Do not sort.
    written: list[str] = []
    for path, content in manifest.items():
        target = args.out / path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            if path.startswith(HOOKS_PREFIX):
                target.chmod(target.stat().st_mode | 0o111)   # inert unless +x
        except OSError as exc:
            print(f"write failed at {path}: {type(exc).__name__}: {exc}\n"
                  f"already written ({len(written)}): {written}\n"
                  "the tree is incomplete. Fix the cause and re-run with --force; "
                  "a plain retry will refuse (exit 3) because those files now exist.",
                  file=sys.stderr)
            return 4
        written.append(path)

    print(json.dumps({"written": written}, indent=2))
    return 0
