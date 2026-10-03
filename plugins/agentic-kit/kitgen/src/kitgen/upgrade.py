"""What a re-render would change that `--force` cannot tell you.

`--force` already replaces scaffolding and preserves everything living, and `/kit-doctor`
already reports a stale `kit_version`, lock drift, a leftover guard and a stale role card.
Three things were left over, and this module is exactly those three:

1. **Orphans.** A file an older render wrote and this one does not. Renaming `spine.strategy`
   leaves the old document behind; plugin 1.1.0 left a dead `.claude/hooks/ownership-guard.sh`
   that looked like an enforcement hook and ran never. Found exactly, by comparing
   `.claude/kit.manifest.json` against the new manifest, rather than guessed at.
2. **Scaffolding drift inside a living document.** `--force` refuses to touch those files, by
   design — so when a template's headings change, nobody is told. Comparing *headings* rather
   than content keeps the signal: the body below them is hand-written and a diff of it is noise.
3. **The version delta**, stated once, with what it implies.

Reports; changes nothing. The re-render is a separate, explicit step.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import KitConfig
from .render import LIVING_KEYS, MANIFEST_RECORD, render

_SECTION = re.compile(r"^(## .+)$", re.M)


# Paths earlier versions of this kit rendered, for trees that predate MANIFEST_RECORD.
#
# A deliberate, enumerated bridge rather than a heuristic: the record makes orphan detection
# exact from the render that writes it onwards, but it cannot see what happened before it
# existed — and the two orphans that actually exist today both predate it. The default spine
# paths are here because relocating `spine.strategy` leaves the default behind, and the
# rendered guard because plugin 1.1.0 moved it into the plugin and left a dead copy that
# looked like an enforcement hook and ran never.
LEGACY_PATHS = (
    "docs/plan/README.md", "docs/strategy.md", "docs/design.md", "docs/decisions.md",
    "docs/risk-register.md", "docs/CONTRACTS.md",
    ".claude/hooks/ownership-guard.sh",
)


def orphans(manifest: dict[str, str], root: Path) -> list[str]:
    """Paths an earlier render wrote, that this one does not, and that still exist."""
    record = root / MANIFEST_RECORD
    previous: list[str] = list(LEGACY_PATHS)
    if record.is_file():
        try:
            recorded = json.loads(record.read_text()).get("paths") or []
            previous += [p for p in recorded if isinstance(p, str)]
        except (OSError, json.JSONDecodeError):
            pass
    return sorted({p for p in previous
                   if p not in manifest and (root / p).is_file()})


def heading_drift(manifest: dict[str, str], cfg: KitConfig,
                  root: Path) -> list[tuple[str, list[str]]]:
    """Living documents whose on-disk copy is missing headings the template now renders.

    Only headings, and only ones that have gone missing. The body under a living document's
    headings is the project's own work, so comparing content would report every project as
    drifted on its first task; and a heading the project ADDED is not drift, it is use.
    """
    out: list[tuple[str, list[str]]] = []
    for key in sorted(LIVING_KEYS):
        rel = cfg.spine[key]
        target = root / rel
        if rel not in manifest or not target.is_file():
            continue
        try:
            on_disk = target.read_text()
        except OSError:
            continue
        missing = [h for h in _SECTION.findall(manifest[rel]) if h not in on_disk]
        if missing:
            out.append((rel, missing))
    return out


def missing_role_sections(cfg: KitConfig, root: Path) -> list[str]:
    """Roles with no `### <role>` section in the design document.

    The one `###` worth checking, and it is checked by name rather than by diffing: a role
    added to the roster after the first render has nowhere to record its design, and
    `--force` will not add the section because design.md is living. Adding a role is the
    commonest reason to re-render, so this is the commonest real drift.
    """
    design = root / cfg.spine["design"]
    if not design.is_file():
        return []
    try:
        body = design.read_text()
    except OSError:
        return []
    return [r.name for r in cfg.roles if f"### {r.name}" not in body]


def inspect(cfg: KitConfig, root: Path) -> list[str]:
    """Everything a re-render would not tell you. Empty means nothing to review."""
    manifest = render(cfg)
    findings: list[str] = []

    record = root / MANIFEST_RECORD
    recorded_version = None
    if record.is_file():
        try:
            recorded_version = json.loads(record.read_text()).get("kit_version")
        except (OSError, json.JSONDecodeError):
            recorded_version = None
    if recorded_version is None:
        findings.append(
            f"no {MANIFEST_RECORD} here, so this tree predates the kit recording what it "
            f"writes. The orphans below come from an enumerated list of paths earlier "
            f"versions rendered, which is not the same as complete — after the next render "
            f"the record makes it exact.")
    elif recorded_version != cfg.kit_version:
        findings.append(
            f"rendered by kit {recorded_version}, profile now says {cfg.kit_version}. The "
            f"re-render below brings the scaffolding up to date; the living documents are "
            f"kept either way.")

    for path in orphans(manifest, root):
        findings.append(
            f"{path!r} was written by an earlier render and is not in this one. Nothing "
            f"invokes or reads it now, which is worse than absent for anything that looks "
            f"like configuration or a guard. Check whether it holds work you want, then "
            f"delete it — the renderer never removes files, deliberately.")

    absent = missing_role_sections(cfg, root)
    if absent:
        findings.append(
            f"{cfg.spine['design']} has no section for {', '.join(repr(a) for a in absent)}. "
            f"Adding a role is the commonest reason to re-render, and design.md is living, so "
            f"--force will not add it — the role would have nowhere to record its design. Add "
            f"a '### <role>' section for each.")

    for rel, missing in heading_drift(manifest, cfg, root):
        findings.append(
            f"{rel} is missing {len(missing)} heading(s) the template now renders: "
            f"{', '.join(repr(h) for h in missing[:4])}"
            f"{' …' if len(missing) > 4 else ''}. It is a living document, so --force will "
            f"not touch it and the new sections will never appear by themselves. Add them "
            f"by hand, or move your content aside and re-render it.")

    return findings
