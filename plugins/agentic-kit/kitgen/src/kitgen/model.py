"""Project profile model. Pure data plus validation; no filesystem access."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any

CLI_FOR_FORGE = {"gitlab": "glab", "github": "gh", "none": "none"}
DEFAULT_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]


class ConfigError(ValueError):
    """A project profile violated a constraint from the design spec, §5.2."""


_WILD = re.compile(r"[*?\[{]")


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
    """
    pa, pb = _glob_prefix(a), _glob_prefix(b)
    if not pa or not pb:
        return True
    return pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/")


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
            attribution=dict(d["attribution"]),
            spine=dict(d["spine"]),
            load_order=[dict(e) for e in d["load_order"]],
            milestones=dict(d["milestones"]),
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

        if not isinstance(self.observability, bool):
            raise ConfigError(
                f"observability must be a boolean, got "
                f"{type(self.observability).__name__} {self.observability!r}")

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

        if self.forge.mirror == self.forge.kind:
            raise ConfigError("forge mirror must differ from forge kind")

    def to_lock(self) -> dict[str, Any]:
        return asdict(self)
