# plugins/agentic-kit/kitgen/src/kitgen/render.py
"""Pure rendering: a KitConfig becomes a {path: content} manifest.

Reads nothing from the project tree and writes nothing. See design spec §4.4.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .model import KitConfig, ci_forge

TEMPLATES = Path(__file__).parent / "templates"

# template file -> output path; one entry per singleton output.
#
# Complete: every template here must exist, since render() loads each one.
# Templates whose output path is FIXED by Claude Code, not by the profile.
FIXED_SINGLETONS = {
    "CLAUDE.md.j2": "CLAUDE.md",
    "orchestrator.md.j2": ".claude/agents/orchestrator.md",
    "settings.json.j2": ".claude/settings.json",
}

# Templates whose output path comes from `cfg.spine[<key>]`.
#
# These were hardcoded until 2026-10-03 while §5 presented `spine.*` as configuration, so
# setting `spine.strategy` to anything else rendered `docs/strategy.md` anyway and then
# failed verification. Found by retrofitting a real repository where "strategy" already
# means trading strategy and `docs/strategy.md` was the wrong name for the operating model.
SPINE_SINGLETONS = {
    "plan.md.j2": "plan",
    "strategy.md.j2": "strategy",
    "design.md.j2": "design",
    "decisions.md.j2": "decisions",
    "risk-register.md.j2": "risks",
    "CONTRACTS.md.j2": "contracts",
}

# The adoption ADR is not a spine key: it is one record inside `docs/adr/`, which the
# architect owns by convention in every generated roster.
ADR_0001 = "docs/adr/0001-adopt-agentic-kit.md"

# Written on a fresh install and never re-rendered over: see design spec §7.1a.
# plan/README.md is pure dispatch state after the first task, and adr-0001 stamps
# the install's date and kit version.
# Written on a fresh install and never re-rendered over: see design spec §7.1a. The plan
# IS dispatch state after the first task, and adr-0001 stamps the install's date and kit
# version. Keyed by spine key rather than by path, since the paths are configurable.
GENERATE_ONCE_KEYS = frozenset({"plan"})

# Living documents, §7.1a: the kit renders their headings and the project writes
# everything underneath. Re-rendering one restores the empty scaffold, which is
# not a diff to review but a deletion -- and worse than a deletion where an index
# is involved: blanking `decisions.md` leaves `docs/adr/0002-*.md` on disk while
# nothing points at it, so the project reads as though the decision was never
# recorded. `strategy.md` is here for §11, whose task graph is hand-expanded at
# every gate; §1-§10 are stable scaffolding, and reconciling the two halves is
# what /kit-upgrade's diff is for (M2), not something a blind overwrite can do.
LIVING_KEYS = frozenset({"strategy", "design", "decisions", "contracts", "risks"})

# Per-role agent memory. Matched by prefix rather than listed, because the roster
# is per-profile: a literal set would miss the memory of any role not in the
# profile being rendered, which is exactly the file a re-render is likeliest to
# find on disk.
MEMORY_PREFIX = ".claude/agent-memory/"


def preserved_paths(cfg: KitConfig) -> frozenset[str]:
    """Every path whose existing copy must survive `--force`, for this profile.

    Resolved from the profile rather than listed literally, because the spine paths are
    configurable: a literal set would protect `docs/strategy.md` in a project that had
    asked for the operating model to live somewhere else, and silently overwrite the file
    that actually holds the work.
    """
    return frozenset(
        [cfg.spine[k] for k in GENERATE_ONCE_KEYS | LIVING_KEYS] + [ADR_0001])


def is_preserved(path: str, cfg: KitConfig) -> bool:
    """True when an existing copy of `path` must survive `--force`.

    `--force` means "replace the generated scaffolding", not "discard the work".
    CLAUDE.md told the user to re-render after every plugin update, so this is the
    difference between an upgrade and a silent amputation of the project's written record.
    """
    return path in preserved_paths(cfg) or path.startswith(MEMORY_PREFIX)


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
    # `ci_elsewhere`: the tracker and CI are on different forges. Computed here from the
    # model's own convention rather than re-derived in Jinja, so there is one definition.
    ci_owner = ci_forge(cfg.forge.ci)
    ctx = {"cfg": cfg, "forge": cfg.forge, "project": cfg.project,
           "roles": cfg.roles, "veto": cfg.veto_role,
           "ci_elsewhere": (ci_owner is not None and cfg.forge.kind != "none"
                            and ci_owner != cfg.forge.kind)}

    out: dict[str, str] = {}
    for template, path in FIXED_SINGLETONS.items():
        out[path] = env.get_template(template).render(**ctx)
    for template, key in SPINE_SINGLETONS.items():
        out[cfg.spine[key]] = env.get_template(template).render(**ctx)
    out[ADR_0001] = env.get_template("adr-0001.md.j2").render(**ctx)

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
