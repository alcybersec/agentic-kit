"""Project profile model. Pure data plus validation; no filesystem access."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, asdict
from typing import Any

CLI_FOR_FORGE = {"gitlab": "glab", "github": "gh", "none": "none"}

# Subagent `model` frontmatter: an alias, a full model ID, or `inherit`.
MODEL_ALIASES = ("opus", "sonnet", "haiku", "fable")

# The one alias whose purpose is speed over capability. Deliberately a set of ONE rather
# than a ranking of the whole lineup: a tier table would be wrong within two releases,
# and the only judgement the kit actually needs is "is this the cheap one". An alias or
# a full ID the kit does not recognise is allowed anywhere, because guessing a stranger's
# capability is worse than trusting the person who typed it.
CHEAP_MODELS = frozenset({"haiku"})
# `NotebookEdit` was absent while BOTH guards matched it, so the kit policed a tool its
# own roles could not use — harmless until someone installs this on a notebook-heavy
# project, where a role then cannot edit a notebook at all. `TodoWrite` was absent too,
# which left a role working a multi-step task with no way to track it. Neither was a
# decision; both are per-role overridable.
DEFAULT_TOOLS = ["Read", "Write", "Edit", "NotebookEdit", "Glob", "Grep", "Bash",
                 "Skill", "TodoWrite"]

# Where a role's `memory: ` directory lives. `project` is `.claude/agent-memory/<role>/`,
# which is exactly where the kit renders MEMORY.md — the kit's convention and Claude
# Code's own subagent memory are the same directory by design. `local` puts it in
# `.claude/agent-memory-local/` instead, for memory you would rather not commit, and
# `user` shares it across every project, which defeats per-project ownership.
MEMORY_SCOPES = ("project", "local", "user")


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


_ROLE_KEYS = {"name", "description", "owns", "handoff_extra", "tools", "veto",
              "model", "memory"}
_MAPPING_SECTIONS = ("attribution", "spine", "milestones", "test_tiers",
                     "toolchain")
_LIST_SECTIONS = ("load_order", "roles", "floors", "secrets")
# Optional, so it is shape-checked only when present.
_OPTIONAL_LIST_SECTIONS = ("critical",)


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
    for section in _OPTIONAL_LIST_SECTIONS:
        if section in d and not isinstance(d[section], list):
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
    # Which model this role is dispatched on. `inherit` means the session's, which is
    # what the Orchestrator always uses — it *is* the session. Per role because the
    # roster already splits along the line that matters: `architect` and the veto role
    # exercise judgement, while an implementing role works against a contract that
    # contract-first required to exist before it was dispatched, which is the condition
    # under which a cheaper model is reasonable.
    model: str = "inherit"
    # `project` keeps a role's memory in the repository, where the ownership guard already
    # keeps each role out of the others'. `local` is for a project that would rather not
    # commit it. Hardcoded until 2026-10-03, which was an unexamined default rather than
    # a decision — the kit renders MEMORY.md into the `project` location either way, so
    # choosing `local` means the index is committed and the facts beside it are not.
    memory: str = "project"


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
    # Paths the veto role holds outright, wherever they sit in the ownership map.
    #
    # Ownership is directory-granular (§6.4): a kill switch, a permission table or a
    # migration guard lives with the code that reads it, so the role that must guard
    # it cannot own the directory, and claiming the file alone is an overlap. This is
    # the narrow exception rather than a precedence engine — every role is refused
    # these paths, including the one that owns the surrounding tree, and the veto role
    # is allowed them even where another role owns everything around them.
    critical: list[str] = field(default_factory=list)

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
                model=r.get("model", "inherit"),
                memory=r.get("memory", "project"),
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
            critical=list(d.get("critical", [])),
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

        # `secrets` reaches TWO matchers with different owners: the kit's own hooks,
        # which are root-anchored and match the whole candidate path, and the
        # `Read()`/`Edit()` deny rules in settings.json, whose matching is Claude
        # Code's. They agree while every pattern is written in the `./` form the
        # schema establishes; a bare `secrets/**` would be root-anchored in the hook
        # and could match at any depth in the deny rule, so the two layers would be
        # protecting different sets of files while the profile named one. Rejected
        # rather than rewritten, for the same reason as `owns` above: a silently
        # corrected pattern teaches the author nothing.
        for secret in self.secrets:
            if not isinstance(secret, str) or not secret.strip():
                raise ConfigError(
                    f"secrets entries must be non-empty strings, got {secret!r}: an "
                    f"empty one renders the deny rule 'Read()'")
            bad = None
            if not secret.startswith("./"):
                bad = ("it does not start with './'. Write './.env', not '.env' or "
                       "'/abs/.env'; for a secret that can appear at more than one "
                       "depth write './**/.env'")
            elif "\\" in secret:
                bad = "it uses a backslash separator"
            elif any(seg in ("", ".", "..") for seg in secret[2:].split("/")):
                bad = "it has an empty, '.' or '..' segment after the './'"
            if bad:
                raise ConfigError(
                    f"secret pattern {secret!r} is not normalised: {bad}. The hooks "
                    f"match it root-anchored against the whole path while "
                    f"settings.json hands it to Claude Code's own path matching, and "
                    f"the two only agree on the './' form.")

        for role in self.roles:
            m = role.model
            if not isinstance(m, str) or not m.strip():
                raise ConfigError(
                    f"role {role.name!r} model must be a non-empty string, got {m!r}")
            if m != "inherit" and m not in MODEL_ALIASES and not m.startswith("claude-"):
                raise ConfigError(
                    f"role {role.name!r} model {m!r} is not 'inherit', one of "
                    f"{list(MODEL_ALIASES)}, or a full model ID beginning 'claude-'. A "
                    f"value Claude Code cannot resolve is not reported until the "
                    f"subagent is dispatched — which is mid-task, with a role card "
                    f"already written and a task already assigned.")

        for role in self.roles:
            if role.memory not in MEMORY_SCOPES:
                raise ConfigError(
                    f"role {role.name!r} memory {role.memory!r} is not one of "
                    f"{list(MEMORY_SCOPES)}. A value Claude Code cannot resolve is not "
                    f"reported until the subagent is dispatched.")
            if role.memory == "user":
                raise ConfigError(
                    f"role {role.name!r} may not use memory: 'user'. That shares one "
                    f"directory across every project on the machine, so a fact learned "
                    f"about one codebase would be presented as true of another — and the "
                    f"ownership guard, which keeps each role out of the others' memory, "
                    f"only governs paths inside this project. Use 'project' (committed, "
                    f"the default) or 'local' (not committed).")

        # The one combination the kit refuses. The veto role produces the Floors
        # dimension of every gate and signs it APPROVE or VETO, which the Orchestrator
        # cannot override; it is also the role whose misses are silent, because a floor
        # nobody tests reads exactly like a floor that holds. Downgrading it is the one
        # model choice that weakens the kit's only hard gate, so it is an error and not
        # an advisory — advice is for findings whose remedy is a judgement call, and this
        # one has a clear answer. To run the whole project on a cheap model, choose it
        # for the session; `inherit` then carries it everywhere, deliberately.
        if self.veto_role.model in CHEAP_MODELS:
            raise ConfigError(
                f"veto role {self.veto_role.name!r} may not run on "
                f"{self.veto_role.model!r}: it produces the Floors dimension of every "
                f"gate and its VETO is not overridable, and a floor it fails to test "
                f"reads exactly like a floor that holds. Use 'inherit' or a more capable "
                f"model. If you want the cheap model everywhere, set it for the session "
                f"instead.")

        # `critical` reaches the same matcher as `owns`, so it carries the same
        # normalisation rule — which also rules out a leading './', because '.' is a
        # rejected segment. One rule, one spelling, one matcher.
        for pattern in self.critical:
            if not isinstance(pattern, str) or not pattern.strip():
                raise ConfigError(
                    f"critical entries must be non-empty strings, got {pattern!r}")
            bad = None
            if pattern.startswith("/"):
                bad = "it is absolute"
            elif "\\" in pattern:
                bad = "it uses a backslash separator"
            elif any(seg in ("", ".", "..") for seg in pattern.split("/")):
                bad = "it has an empty, '.' or '..' segment"
            if bad:
                raise ConfigError(
                    f"critical path {pattern!r} is not normalised: {bad}. Write it "
                    f"relative to the repository root using forward slashes, the same "
                    f"way as an `owns` glob — the ownership guard matches both with the "
                    f"same code.")

        names = [r.name for r in self.roles]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ConfigError(f"duplicate role names: {sorted(dupes)}")

        for i, a in enumerate(self.roles):
            for b in self.roles[i + 1:]:
                for pa in a.owns:
                    for pb in b.owns:
                        if _overlaps(pa, pb):
                            # Name the CAUSE, not just the pair. A glob whose first
                            # segment is wild has no literal prefix and so overlaps
                            # everything, which means the partner reported alongside
                            # it is usually innocent -- and an author shown
                            # "src/api/** overlaps *.py" reaches for the wrong one.
                            why = ""
                            if not _glob_prefix(pa) or not _glob_prefix(pb):
                                wild = pa if not _glob_prefix(pa) else pb
                                why = (f" -- {wild!r} begins with a wildcard segment, so "
                                       f"it has no literal directory prefix and is "
                                       f"treated as overlapping every other glob. The "
                                       f"other pattern here may be fine: root it in a "
                                       f"directory (§5.2)")
                            raise ConfigError(
                                f"ownership overlap: {a.name}:{pa} and "
                                f"{b.name}:{pb}{why}")

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
