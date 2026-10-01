"""Project profile model. Pure data plus validation; no filesystem access."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

CLI_FOR_FORGE = {"gitlab": "glab", "github": "gh", "none": "none"}


class ConfigError(ValueError):
    """A project profile violated a constraint from the design spec, §5.2."""


def _glob_prefix(pattern: str) -> str:
    """The literal directory prefix of a glob, used for overlap detection."""
    head = pattern.split("*", 1)[0]
    return head.rstrip("/")


def _overlaps(a: str, b: str) -> bool:
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
    tools: list[str] = field(default_factory=lambda: [
        "Read", "Write", "Edit", "Glob", "Grep", "Bash"])
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
        return next(r for r in self.roles if r.veto)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KitConfig:
        roles = [Role(**r) for r in d["roles"]]
        cfg = cls(
            kit_version=d["kit_version"],
            rendered_on=d["rendered_on"],
            project=Project(**d["project"]),
            forge=Forge(**d["forge"]),
            attribution=d["attribution"],
            spine=d["spine"],
            load_order=d["load_order"],
            milestones=d["milestones"],
            roles=roles,
            floors=list(d["floors"]),
            test_tiers=d["test_tiers"],
            toolchain=d["toolchain"],
            secrets=list(d["secrets"]),
            observability=bool(d["observability"]),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
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
