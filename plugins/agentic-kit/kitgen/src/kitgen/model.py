"""Project profile model. Pure data plus validation; no filesystem access."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, asdict
from typing import Any

CLI_FOR_FORGE = {"gitlab": "glab", "github": "gh", "none": "none"}
DEFAULT_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"]


class ConfigError(ValueError):
    """A project profile violated a constraint from the design spec, §5.2."""


_WILD = re.compile(r"[*?\[{]")

# A whole-tree target in a formatter command. `post-edit-format.sh` appends the
# edited file to `toolchain.format`, so a command that already names its own
# target formats that target *as well as* the file -- `black .` becomes
# `black . <file>`, rewriting every other role's files from a PostToolUse hook
# that no ownership matcher sees.
# `-a`/`-r`/`-R` are deliberately absent: they mean "recursive" in some tools
# and take a value in others (`gofmt -r '<rewrite rule>'`), so rejecting them
# would refuse legitimate commands. A path-shaped target is caught below instead.
_TREE_TARGETS = frozenset({".", "./", "..", "../", "--all"})
# Shape of a trailing argument that is a path or a glob rather than a flag.
# Checked only on the final token, and only when the command has more than one:
# a single-token command is the executable itself, and `./scripts/fmt.sh` is a
# legitimate one. Mid-command path-shaped tokens are left alone because they are
# usually a flag's value (`--config ./p.toml`), which is not a target.
_PATH_SHAPED = re.compile(r"[/*?]|\.(py|pyi|ts|tsx|js|jsx|go|rs|rb|java|kt|css|scss)$")


def _glob_prefix(pattern: str) -> str:
    """The literal *directory* prefix of a glob, used for overlap detection.

    Truncates at the first wildcard metacharacter and then back to the last
    path separator, so a mid-segment wildcard cannot leave a partial segment
    behind: `src/a*/x/**` yields `src`, not `src/a`. A pattern whose first
    segment is already wild yields `""`.
    """
    m = _WILD.search(pattern)
    if not m:
        return pattern.rstrip("/")
    head = pattern[:m.start()]
    return head[:head.rfind("/")] if "/" in head else ""


def _overlaps(a: str, b: str) -> bool:
    """Whether two ownership globs may match the same file.

    Overlap is tested on literal directory prefixes, so `owns` globs must be
    directory-rooted. A glob whose first segment is wild has no prefix and is
    treated as overlapping everything, which means a profile containing one can
    never validate: extension-partitioned ownership of a shared tree
    (`app/**/*.py` vs `app/**/*.tsx`) is rejected by design.

    Detection also assumes normalised, repository-root-relative globs (no
    leading `./`, no `//`, no `../`); `KitConfig.validate()` enforces this
    before it calls here.
    """
    pa, pb = _glob_prefix(a), _glob_prefix(b)
    if not pa or not pb:
        return True
    return pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/")


_ROLE_KEYS = {"name", "description", "owns", "handoff_extra", "tools", "veto"}
_MAPPING_SECTIONS = ("attribution", "spine", "milestones", "test_tiers",
                     "toolchain")
_LIST_SECTIONS = ("load_order", "roles", "floors", "secrets")


def _check_shapes(d: dict[str, Any]) -> None:
    """Reject a scalar where a mapping or list belongs, before any copying."""
    for section in _MAPPING_SECTIONS:
        if not isinstance(d[section], dict):
            raise ConfigError(
                f"{section} must be a mapping, got {type(d[section]).__name__}")
    for section in _LIST_SECTIONS:
        if not isinstance(d[section], list):
            raise ConfigError(
                f"{section} must be a list, got {type(d[section]).__name__}")
    for r in d["roles"]:
        if not isinstance(r, dict):
            raise ConfigError(f"each role must be a mapping, got {type(r).__name__}")
        unknown = set(r) - _ROLE_KEYS
        if unknown:
            raise ConfigError(
                f"role {r.get('name', '<unnamed>')!r} has unknown keys: "
                f"{sorted(unknown)}")


@dataclass(frozen=True)
class Role:
    name: str
    description: str
    owns: list[str]
    handoff_extra: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    veto: bool = False


@dataclass(frozen=True)
class Project:
    name: str
    slug: str
    summary: str


@dataclass(frozen=True)
class Forge:
    kind: str
    remote: str | None
    cli: str
    ci: str | None
    exclusive: bool = True
    mirror: str | None = None


@dataclass(frozen=True)
class KitConfig:
    kit_version: str
    rendered_on: str   # ISO date, supplied by the caller: render() must stay pure (§4.4)
    project: Project
    forge: Forge
    attribution: dict[str, Any]
    spine: dict[str, Any]
    load_order: list[dict[str, Any]]
    milestones: dict[str, Any]
    roles: list[Role]
    floors: list[str]
    test_tiers: dict[str, int]
    toolchain: dict[str, str]
    secrets: list[str]
    observability: bool

    @property
    def veto_role(self) -> Role:
        role = next((r for r in self.roles if r.veto), None)
        if role is None:
            raise ConfigError("no role carries veto: true")
        return role

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KitConfig:
        _check_shapes(d)
        roles = [
            Role(
                name=r["name"],
                description=r["description"],
                owns=list(r["owns"]),
                handoff_extra=list(r.get("handoff_extra", [])),
                tools=list(r.get("tools", DEFAULT_TOOLS)),
                veto=r.get("veto", False),
            )
            for r in d["roles"]
        ]
        cfg = cls(
            kit_version=d["kit_version"],
            rendered_on=d["rendered_on"],
            project=Project(**d["project"]),
            forge=Forge(**d["forge"]),
            attribution=copy.deepcopy(d["attribution"]),
            spine=copy.deepcopy(d["spine"]),
            load_order=copy.deepcopy(d["load_order"]),
            milestones=copy.deepcopy(d["milestones"]),
            roles=roles,
            floors=list(d["floors"]),
            test_tiers=dict(d["test_tiers"]),
            toolchain=dict(d["toolchain"]),
            secrets=list(d["secrets"]),
            observability=d["observability"],
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        required = {
            "spine": ("plan", "strategy", "design", "decisions", "risks",
                      "contracts", "inherited"),
            "toolchain": ("pm", "test", "format", "lint", "types"),
            "milestones": ("prefix", "id_format", "outline"),
            "attribution": ("mention_assistant_in_commits",),
        }
        for section, keys in required.items():
            present = getattr(self, section)
            for key in keys:
                if key not in present:
                    raise ConfigError(f"{section} is missing {key!r}")

        outline = self.milestones["outline"]
        if not isinstance(outline, list) or not outline:
            raise ConfigError(
                "milestones.outline must be a non-empty list: strategy.md and "
                "plan/README.md both index outline[0], so an empty one would "
                "surface as a template UndefinedError instead of this message")

        for key, value in self.toolchain.items():
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(
                    f"toolchain.{key} must be a non-empty command string; an empty "
                    f"value renders the permission rule 'Bash(:*)', whose meaning "
                    f"depends on how the host parses an empty prefix")

        # `toolchain.format` is the one command the kit appends an argument to,
        # so it must be a prefix that takes exactly one file. This is a lexical
        # test only: §4.4 forbids the model from touching the project tree, so
        # "is this token an existing path" is not a question it may ask.
        fmt_tokens = self.toolchain["format"].split()
        bad_token = next((t for t in fmt_tokens[1:] if t in _TREE_TARGETS), None)
        if bad_token is None and len(fmt_tokens) > 1 and _PATH_SHAPED.search(fmt_tokens[-1]):
            bad_token = fmt_tokens[-1]
        if bad_token is not None:
            raise ConfigError(
                f"toolchain.format must name no target of its own, but carries "
                f"{bad_token!r}: the post-edit hook appends the edited file, so "
                f"this would run '{self.toolchain['format']} <file>' and reformat "
                f"that target too -- every other role's files, from a hook no "
                f"ownership matcher covers. Drop the target: 'black .' -> 'black'")

        if not isinstance(self.observability, bool):
            raise ConfigError(
                f"observability must be a boolean, got "
                f"{type(self.observability).__name__} {self.observability!r}")

        for role in self.roles:
            for glob in role.owns:
                bad = None
                if glob.startswith("/"):
                    bad = "it is absolute"
                elif "\\" in glob:
                    bad = "it uses a backslash separator"
                elif any(seg in ("", ".", "..") for seg in glob.split("/")):
                    bad = "it has an empty, '.' or '..' segment"
                if bad:
                    raise ConfigError(
                        f"role {role.name!r} owns glob {glob!r} is not normalised: "
                        f"{bad}. Write it relative to the repository root using "
                        f"forward slashes, with no leading '/', no '.' or '..' "
                        f"segment and no empty segment. Overlap is decided on "
                        f"literal path prefixes, so a non-normalised glob would "
                        f"not be detected as overlapping an equivalent one.")

        names = [r.name for r in self.roles]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ConfigError(f"duplicate role names: {sorted(dupes)}")

        for i, a in enumerate(self.roles):
            for b in self.roles[i + 1:]:
                for pa in a.owns:
                    for pb in b.owns:
                        if _overlaps(pa, pb):
                            raise ConfigError(
                                f"ownership overlap: {a.name}:{pa} and {b.name}:{pb}")

        if not self.floors:
            raise ConfigError("floors must be non-empty; they scope the veto role")

        vetoes = [r.name for r in self.roles if r.veto]
        if len(vetoes) != 1:
            raise ConfigError(
                f"exactly one role must carry veto: true, found {vetoes}")

        expected = CLI_FOR_FORGE.get(self.forge.kind)
        if expected is None:
            raise ConfigError(f"unknown forge kind: {self.forge.kind}")
        if self.forge.cli != expected:
            raise ConfigError(
                f"forge cli {self.forge.cli!r} does not match kind "
                f"{self.forge.kind!r}; expected {expected!r}")

        if self.forge.kind == "none":
            for field in ("remote", "ci", "mirror"):
                if getattr(self.forge, field) is not None:
                    raise ConfigError(
                        f"forge.kind is 'none' but forge.{field} is "
                        f"{getattr(self.forge, field)!r}; a project with no forge has no "
                        f"remote, no CI file and no mirror")

        if self.forge.mirror == self.forge.kind:
            raise ConfigError("forge mirror must differ from forge kind")

    def to_lock(self) -> dict[str, Any]:
        return asdict(self)
