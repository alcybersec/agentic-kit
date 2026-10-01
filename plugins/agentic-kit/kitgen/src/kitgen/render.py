# plugins/agentic-kit/kitgen/src/kitgen/render.py
"""Pure rendering: a KitConfig becomes a {path: content} manifest.

Reads nothing from the project tree and writes nothing. See design spec §4.4.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .model import KitConfig

TEMPLATES = Path(__file__).parent / "templates"

# template file -> output path; one entry per singleton output.
#
# Complete: every template here must exist, since render() loads each one.
SINGLETONS = {
    "CLAUDE.md.j2": "CLAUDE.md",
    "orchestrator.md.j2": ".claude/agents/orchestrator.md",
    "settings.json.j2": ".claude/settings.json",
    "plan.md.j2": "docs/plan/README.md",
    "strategy.md.j2": "docs/strategy.md",
    "design.md.j2": "docs/design.md",
    "decisions.md.j2": "docs/decisions.md",
    "risk-register.md.j2": "docs/risk-register.md",
    "CONTRACTS.md.j2": "docs/CONTRACTS.md",
    "adr-0001.md.j2": "docs/adr/0001-adopt-agentic-kit.md",
    "ownership-guard.sh.j2": ".claude/hooks/ownership-guard.sh",
}

# Written on a fresh install and never re-rendered over: see design spec §7.1a.
# plan/README.md is pure dispatch state after the first task, and adr-0001 stamps
# the install's date and kit version.
GENERATE_ONCE = frozenset({
    "docs/plan/README.md",
    "docs/adr/0001-adopt-agentic-kit.md",
})

# Living documents, §7.1a: the kit renders their headings and the project writes
# everything underneath. Re-rendering one restores the empty scaffold, which is
# not a diff to review but a deletion -- and worse than a deletion where an index
# is involved: blanking `decisions.md` leaves `docs/adr/0002-*.md` on disk while
# nothing points at it, so the project reads as though the decision was never
# recorded. `strategy.md` is here for §11, whose task graph is hand-expanded at
# every gate; §1-§10 are stable scaffolding, and reconciling the two halves is
# what /kit-upgrade's diff is for (M2), not something a blind overwrite can do.
LIVING = frozenset({
    "docs/strategy.md",
    "docs/design.md",
    "docs/decisions.md",
    "docs/CONTRACTS.md",
    "docs/risk-register.md",
})

# Per-role agent memory. Matched by prefix rather than listed, because the roster
# is per-profile: a literal set would miss the memory of any role not in the
# profile being rendered, which is exactly the file a re-render is likeliest to
# find on disk.
MEMORY_PREFIX = ".claude/agent-memory/"


def is_preserved(path: str) -> bool:
    """True when an existing copy of `path` must survive `--force`.

    `--force` means "replace the generated scaffolding", not "discard the work".
    CLAUDE.md told the user to re-render after every plugin update, so this set
    is the difference between an upgrade and a silent amputation of the project's
    written record.
    """
    return (path in GENERATE_ONCE or path in LIVING
            or path.startswith(MEMORY_PREFIX))


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(cfg: KitConfig) -> dict[str, str]:
    env = _env()
    ctx = {"cfg": cfg, "forge": cfg.forge, "project": cfg.project,
           "roles": cfg.roles, "veto": cfg.veto_role}

    out: dict[str, str] = {}
    for template, path in SINGLETONS.items():
        out[path] = env.get_template(template).render(**ctx)

    # Order matters: the CLI writes in insertion order, and §5.1 reads
    # mtime(kit.yaml) > mtime(kit.lock.json) as hand-edited drift. Emit the yaml
    # FIRST so the lock is always the newer file on a clean render.
    lock = cfg.to_lock()
    out[".claude/kit.yaml"] = yaml.safe_dump(lock, sort_keys=False, width=100)
    out[".claude/kit.lock.json"] = json.dumps(lock, indent=2, sort_keys=True) + "\n"

    role_card = env.get_template("role.md.j2")
    memory = env.get_template("MEMORY.md.j2")
    for r in cfg.roles:
        out[f".claude/agents/{r.name}.md"] = role_card.render(role=r, **ctx)
        out[f".claude/agent-memory/{r.name}/MEMORY.md"] = memory.render(role=r, **ctx)

    return out
