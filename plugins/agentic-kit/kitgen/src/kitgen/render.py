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
# This table GROWS as templates land, and render() loads every template it names.
# Listing a template before it exists would make the whole suite raise
# TemplateNotFound, so each task adds its own entries:
#   Task 5 -> orchestrator.md.j2  (plus the per-role loop below)
#   Task 6 -> settings.json.j2
#   Task 7 -> plan/strategy/design/decisions/risk-register/CONTRACTS/adr-0001
SINGLETONS = {
    "CLAUDE.md.j2": "CLAUDE.md",
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

    # Task 5 adds the per-role loop here (role.md.j2 and MEMORY.md.j2).

    return out
