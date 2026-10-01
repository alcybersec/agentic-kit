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
}


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
