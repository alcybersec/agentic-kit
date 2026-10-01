"""Cross-reference checks over a rendered manifest. Returns a list of problems.

An empty list means the manifest is internally consistent. Run this before writing
anything to disk. See design spec §9.1.

Division of labour with model.py: KitConfig.validate() rejects an inconsistent
*profile* (overlapping ownership, one veto role, non-empty floors, normalised
globs, non-empty milestones.outline). This module checks the *rendered output*
against the profile and never repeats those checks.

Several checks read rendered prose (markdown tables). They are deliberately narrow
and explicit: each parses one table shape the templates emit. If a template's
table layout changes, the check fails loudly ("table not found") rather than
passing vacuously.
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

import yaml

from .model import KitConfig, _glob_prefix

_TICKS = re.compile(r"`([^`]+)`")
_TASK_ROW = re.compile(r"^\|\s*[\w]+-S\d+-[\w-]+-\d+\s*\|\s*`([^`]+)`\s*\|")


def _section(text: str, start: str, end: str | None) -> list[str] | None:
    """Lines from the heading starting with `start` to the next heading `end`."""
    lines = text.splitlines()
    try:
        i = next(n for n, l in enumerate(lines) if l.startswith(start))
    except StopIteration:
        return None
    out = []
    for l in lines[i + 1:]:
        if end and l.startswith(end):
            break
        out.append(l)
    return out


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _covers(glob: str, path: str) -> bool:
    """Whether an ownership glob covers, or lies inside, a literal path."""
    prefix = _glob_prefix(glob)
    return (fnmatch.fnmatch(path, glob) or prefix == path
            or (prefix != "" and path.startswith(prefix + "/"))
            or prefix.startswith(path + "/"))


def verify(manifest: dict[str, str], cfg: KitConfig,
           project_root: Path | None = None) -> list[str]:
    problems: list[str] = []
    role_names = [r.name for r in cfg.roles]

    # --- roles <-> CLAUDE.md table <-> agent cards <-> kit.yaml -------------
    claude_md = manifest.get("CLAUDE.md", "")
    table = _section(claude_md, "| Agent | Owns |", None)
    if table is None:
        problems.append("CLAUDE.md: agent table (header '| Agent | Owns |') not found")
    else:
        rows = []
        for l in table[1:]:
            if not l.startswith("|"):
                break
            m = _TICKS.match(_cells(l)[0])
            if m:
                rows.append(m.group(1))
        for n in role_names:
            if n not in rows:
                problems.append(f"role {n!r}: absent from the CLAUDE.md agent table")
        for n in rows:
            if n not in role_names:
                problems.append(
                    f"CLAUDE.md agent table lists {n!r}, which is not in roles[]")

    for r in cfg.roles:
        card = f".claude/agents/{r.name}.md"
        if card not in manifest:
            problems.append(f"role {r.name!r}: no {card} in the manifest")
        mem = f".claude/agent-memory/{r.name}/MEMORY.md"
        if mem not in manifest:
            problems.append(f"role {r.name!r}: no {mem} in the manifest")
        for extra in r.handoff_extra:
            if extra not in manifest.get(card, ""):
                problems.append(
                    f"role {r.name!r}: handoff line {extra!r} missing from {card}")

    declared = {p.split("/")[-1].removesuffix(".md")
                for p in manifest if re.fullmatch(r"\.claude/agents/[^/]+\.md", p)}
    for extra in sorted(declared - set(role_names) - {"orchestrator"}):
        problems.append(f"agent card {extra!r} has no matching role in kit.yaml")

    try:
        yaml_roles = [r["name"] for r in
                      yaml.safe_load(manifest[".claude/kit.yaml"])["roles"]]
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        problems.append(f".claude/kit.yaml is not usable: {exc!r}")
    else:
        if yaml_roles != role_names:
            problems.append(
                f".claude/kit.yaml roles {yaml_roles} do not match the config's "
                f"roles {role_names}")

    # --- strategy ownership table == roles[].owns / handoff_extra -----------
    strategy_path = cfg.spine["strategy"]
    strategy = manifest.get(strategy_path, "")
    own = _section(strategy, "## 2.", "## 3.")
    if own is None:
        problems.append(f"{strategy_path}: §2 ownership map not found")
    else:
        seen: dict[str, tuple[set[str], set[str]]] = {}
        for l in own:
            if not l.startswith("| `"):
                continue
            c = _cells(l)
            seen[_TICKS.match(c[0]).group(1)] = (
                set(_TICKS.findall(c[1])), set(_TICKS.findall(c[2])))
        for r in cfg.roles:
            if r.name not in seen:
                problems.append(
                    f"{strategy_path} §2: no ownership row for role {r.name!r}")
                continue
            globs, extras = seen[r.name]
            if globs != set(r.owns):
                problems.append(
                    f"{strategy_path} §2: role {r.name!r} owns {sorted(globs)} but "
                    f"kit.yaml says {sorted(r.owns)}")
            if extras != set(r.handoff_extra):
                problems.append(
                    f"{strategy_path} §2: role {r.name!r} handoff extras "
                    f"{sorted(extras)} but kit.yaml says {sorted(r.handoff_extra)}")
        for n in seen.keys() - set(role_names):
            problems.append(
                f"{strategy_path} §2 lists role {n!r}, which is not in roles[]")

    # --- M0 task table (strategy §11) ---------------------------------------
    sec11 = _section(strategy, "## 11.", None)
    if sec11 is None:
        problems.append(f"{strategy_path}: §11 task graph not found")
        sec11 = []
    task_rows = [(l, m.group(1)) for l in sec11 if (m := _TASK_ROW.match(l))]
    if not task_rows:
        problems.append(f"{strategy_path} §11: no M0 task rows found")
    owners = {o for _, o in task_rows}

    # Every owner the table names exists; every role the table is required to
    # name is both named and in the roster.
    for o in sorted(owners):
        if o not in role_names:
            problems.append(
                f"{strategy_path} §11: an M0 task is assigned to {o!r}, which is "
                f"not in roles[]")
    for needed in ("architect", "devops", "qa", cfg.veto_role.name):
        if needed not in role_names:
            problems.append(
                f"roles[] has no {needed!r}, but the M0 task table assigns it a "
                f"task, so that task is assigned to nobody")
        elif task_rows and needed not in owners:
            problems.append(
                f"{strategy_path} §11: the M0 table assigns no task to {needed!r}")

    # The veto role owns at least one path (it cannot build the floor tier otherwise).
    if not cfg.veto_role.owns:
        problems.append(
            f"veto role {cfg.veto_role.name!r} owns no path, so it cannot build "
            f"the floor test tier the M0 gate requires")

    # Rows that tell a role to write "in a path <role> owns per §2" are
    # unexecutable if that role owns nothing. Catches only that; it cannot judge
    # whether a role's owned paths are *suitable* for tests. The veto role is
    # reported by the check above. Rows saying "or an unowned path" are exempt.
    #
    # NOT implemented as worded: §9.1's "every role named in the M0 table either
    # owns a test path or no role owns one". Read literally it fires on all three
    # fixtures (architect and devops own no test path in any of them, while qa or
    # the veto role does), and the rows already allow an unowned fallback for
    # devops and qa. See the report for Task 8.
    for line, owner in task_rows:
        # (veto excluded: the veto-owns-a-path check reports it; avoid a duplicate)
        if (owner in role_names and owner != cfg.veto_role.name
                and re.search(r"owns per §2(?! or an unowned)", line)):
            if not next(r for r in cfg.roles if r.name == owner).owns:
                problems.append(
                    f"{strategy_path} §11: a task tells {owner!r} to write in a "
                    f"path it owns per §2, but {owner!r} owns no path")

    # A task's owner must be able to write the task's outputs. Checked for
    # spine.contracts because the M0 contract task is the first task of every
    # install: when another role owns that path the guard blocks the assigned role,
    # /handoff tells it to request the file from someone else, and the task can
    # only ever be PARTIAL -- a deadlock on move one. Unowned is the intended
    # state and is fine: the guard blocks a path only when ANOTHER role owns it.
    contracts = cfg.spine["contracts"]
    owning_contracts = [r.name for r in cfg.roles
                        if any(_covers(g, contracts) for g in r.owns)]
    for line, owner in task_rows:
        if f"`{contracts}`" not in line:
            continue
        blocked_by = [o for o in owning_contracts if o != owner]
        if blocked_by:
            problems.append(
                f"{strategy_path} §11: the task writing {contracts!r} is assigned "
                f"to {owner!r}, but {blocked_by} own that path, so the ownership "
                f"guard blocks it and the task cannot be completed")

    # The role owning forge.ci is the role the CI-wiring row names. Matches the one
    # row that has "wired into `<forge.ci>`"; it does not catch a CI path that is
    # unowned (any role may write an unowned path) or a CI row phrased differently.
    ci = cfg.forge.ci
    # model.py rejects kind "none" with a ci value; this guard is belt-and-braces.
    if cfg.forge.kind != "none" and ci:
        ci_rows = [(l, o) for l, o in task_rows if f"wired into `{ci}`" in l]
        if not ci_rows:
            problems.append(
                f"{strategy_path} §11: no CI-wiring task row mentions `{ci}`")
        for _, row_owner in ci_rows:
            owning = [r.name for r in cfg.roles
                      if any(_covers(g, ci) for g in r.owns)]
            if owning and row_owner not in owning:
                problems.append(
                    f"forge.ci {ci!r} is owned by {owning}, but the CI-wiring "
                    f"task in {strategy_path} §11 is assigned to {row_owner!r}")

    # --- settings.json denies every secret ----------------------------------
    try:
        deny = json.loads(manifest[".claude/settings.json"])["permissions"]["deny"]
    except (KeyError, json.JSONDecodeError) as exc:
        problems.append(f".claude/settings.json is not usable: {exc!r}")
    else:
        for s in cfg.secrets:
            for tool in ("Read", "Edit"):
                if f"{tool}({s})" not in deny:
                    problems.append(
                        f".claude/settings.json: secret {s!r} is not denied for {tool}")

    # --- lock == config ------------------------------------------------------
    try:
        lock = json.loads(manifest[".claude/kit.lock.json"])
    except (KeyError, json.JSONDecodeError) as exc:
        problems.append(f".claude/kit.lock.json is not usable: {exc!r}")
    else:
        if lock != json.loads(json.dumps(cfg.to_lock())):
            problems.append(
                ".claude/kit.lock.json does not match the config it came from")

    # --- spine / load_order paths -------------------------------------------
    # render() hardcodes its output paths while cfg.spine.* is configurable, so this
    # is the only check connecting them.
    #
    # Non-inherited paths must be in the manifest: they are rendered, so absence
    # cannot be intentional and needs no disk access to detect. A project_root
    # only lets an existing file stand in for a rendered one.
    #
    # spine.inherited names pre-existing authoritative docs that are deliberately
    # never rendered (§7.1), so they are checked ONLY when project_root is given:
    # with None we cannot inspect the disk, and "absent from the manifest" would
    # make every clean render verify dirty.
    inherited = set(cfg.spine["inherited"])

    def _present(p: str) -> bool:
        return p in manifest or (project_root is not None
                                 and (project_root / p).exists())

    for label, value in cfg.spine.items():
        for p in value if isinstance(value, list) else [value]:
            if p in inherited and project_root is None:
                continue
            if not _present(p):
                problems.append(
                    f"spine.{label} path {p!r} is neither rendered nor present "
                    f"on disk")
    for entry in cfg.load_order:
        p = entry["path"]
        if p in inherited and project_root is None:
            continue
        if not _present(p):
            problems.append(
                f"load_order path {p!r} is neither rendered nor on disk")

    return problems
