# Agentic Kit — M1 (kit + renderer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `agentic-kit` Claude Code plugin — universal process skills, four guard hooks, and a pure renderer that turns a project profile into a complete orchestrator kit — verified against three fixtures.

**Architecture:** One repository that is also its own plugin marketplace. `kitgen` is a Python package exposing a pure `render(answers, facts) -> {path: content}` and a `verify(manifest, config)` cross-reference checker; it never touches the project tree. Hooks and skills read a generated `.claude/kit.lock.json` and are inert without it, so the globally installed plugin cannot disturb non-kit repositories.

**Tech Stack:** Python 3.12, Jinja2, pytest, `uv`; Bash + `jq` for hooks; Claude Code plugin format (`.claude-plugin/`, `hooks/hooks.json`, `skills/*/SKILL.md`).

**Spec:** `docs/2026-09-30-agentic-kit-design.md`

---

## File Structure

| Path | Responsibility |
|---|---|
| `.claude-plugin/marketplace.json` | Marketplace listing one plugin |
| `plugins/agentic-kit/.claude-plugin/plugin.json` | Plugin manifest |
| `plugins/agentic-kit/kitgen/src/kitgen/model.py` | `KitConfig` dataclasses, YAML load, all §5.2 constraint validation |
| `plugins/agentic-kit/kitgen/src/kitgen/render.py` | Pure render: config → `{path: content}` |
| `plugins/agentic-kit/kitgen/src/kitgen/verify.py` | Cross-reference checks over a rendered manifest |
| `plugins/agentic-kit/kitgen/src/kitgen/cli.py` | `kitgen render`, `kitgen verify`, `kitgen lock` |
| `plugins/agentic-kit/kitgen/src/kitgen/templates/*.j2` | One template per rendered file |
| `plugins/agentic-kit/hooks/lib/kitlock.sh` | Shared: locate project root, load lock, inertness exit |
| `plugins/agentic-kit/hooks/*.sh` | The four guards |
| `plugins/agentic-kit/skills/*/SKILL.md` | Eight universal process skills |
| `plugins/agentic-kit/kitgen/tests/` | Model, render, verify, hook tests; three fixtures |

Templates are split one-per-output-file so a change to `strategy.md` prose cannot break `CLAUDE.md`.

---

## Task 1: Repository and plugin manifests

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `plugins/agentic-kit/.claude-plugin/plugin.json`
- Create: `plugins/agentic-kit/kitgen/pyproject.toml`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/__init__.py` (empty; hatchling needs a package to ship)
- Create: `plugins/agentic-kit/kitgen/tests/__init__.py` (empty; Task 10's `from .hooks_conftest import` needs `tests` to be a package)
- Generated: `plugins/agentic-kit/kitgen/uv.lock` (commit it)
- Test: `plugins/agentic-kit/kitgen/tests/test_manifests.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_manifests.py
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_marketplace_lists_the_plugin():
    mp = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
    assert mp["name"] == "agentic-kit"
    names = [p["name"] for p in mp["plugins"]]
    assert names == ["agentic-kit"]
    assert mp["plugins"][0]["source"] == "./plugins/agentic-kit"


def test_plugin_manifest_is_valid():
    pj = json.loads(
        (REPO / "plugins/agentic-kit/.claude-plugin/plugin.json").read_text()
    )
    assert pj["name"] == "agentic-kit"
    assert pj["description"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_manifests.py -v`
Expected: FAIL — `FileNotFoundError: .../.claude-plugin/marketplace.json`

- [ ] **Step 3: Write minimal implementation**

```json
// .claude-plugin/marketplace.json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "agentic-kit",
  "description": "Orchestrator-model Claude Code kit: role agents with path ownership, gates, risk register, handoff protocol.",
  "owner": { "name": "Alex" },
  "plugins": [
    {
      "name": "agentic-kit",
      "description": "Drop-in agentic development kit: universal process skills, guard hooks, and a renderer that generates a project's orchestrator kit.",
      "category": "workflow",
      "source": "./plugins/agentic-kit"
    }
  ]
}
```

```json
// plugins/agentic-kit/.claude-plugin/plugin.json
{
  "name": "agentic-kit",
  "description": "Orchestrator-model agentic development kit: role agents with file-path ownership, gates, risk register, handoff protocol, agent memory, and guard hooks that are inert outside kit projects.",
  "author": { "name": "Alex" }
}
```

```toml
# plugins/agentic-kit/kitgen/pyproject.toml
[project]
name = "kitgen"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["jinja2>=3.1", "pyyaml>=6.0"]

[project.scripts]
kitgen = "kitgen.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/kitgen"]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Without the `[tool.hatch.build.targets.wheel]` block **and** an existing `src/kitgen/__init__.py`, the
build fails with `ValueError: Unable to determine which files to ship inside the wheel` and `uv run`
never reaches pytest. `packages = [...]` also ships every non-ignored file under the package
directory, which is how `templates/*.j2` reach the wheel in Task 4 — so never narrow it to an
`include = [...]` of `*.py`, and never add a `.gitignore` rule matching `*.j2` or `templates/`
(hatch honours `.gitignore`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_manifests.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin plugins/agentic-kit/.claude-plugin plugins/agentic-kit/kitgen/pyproject.toml plugins/agentic-kit/kitgen/tests/test_manifests.py plugins/agentic-kit/kitgen/tests/__init__.py plugins/agentic-kit/kitgen/src/kitgen/__init__.py plugins/agentic-kit/kitgen/uv.lock
git commit -m "feat: marketplace and plugin manifests with validation tests"
```

---

## Task 2: `KitConfig` model and the §5.2 constraints

The verifier constraints from the spec live here so a bad profile is rejected before any file is
rendered.

> **Amended after code review.** The implementation below is the first draft. Six fixes landed on top
> of it and the committed module is the authority: `_glob_prefix` truncates at the first wildcard
> metacharacter (`[*?\[{]`) and then back to the last `/`, so a mid-segment wildcard cannot leave a
> partial segment (`src/a*/x/**` → `src`, not `src/a`); `validate()` checks required keys in `spine`,
> `toolchain`, `milestones` and `attribution` first; `observability` must be a real boolean rather
> than being coerced; `veto_role` raises `ConfigError` rather than `StopIteration`; `from_dict` copies
> every mutable section; and five further negative tests cover the mirror, unknown-kind,
> missing-key, non-boolean and segment-truncation paths.

**Files:**
- Create: `plugins/agentic-kit/kitgen/src/kitgen/model.py`
- Test: `plugins/agentic-kit/kitgen/tests/test_model.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_model.py
import pytest
from kitgen.model import KitConfig, ConfigError

MINIMAL = {
    "kit_version": "1.0.0",
    "rendered_on": "2026-09-30",
    "project": {"name": "Demo", "slug": "demo", "summary": "A demo."},
    "forge": {"kind": "gitlab", "remote": "git@host:o/r.git", "cli": "glab",
              "ci": ".gitlab-ci.yml", "exclusive": True},
    "attribution": {"mention_assistant_in_commits": False},
    "spine": {"plan": "docs/plan/README.md", "strategy": "docs/strategy.md",
              "design": "docs/design.md", "decisions": "docs/decisions.md",
              "risks": "docs/risk-register.md", "contracts": "docs/CONTRACTS.md",
              "inherited": []},
    "load_order": [{"path": "docs/plan/README.md", "mode": "full"}],
    "milestones": {"prefix": "M", "id_format": "{milestone}-S{sprint}-{OWNER}-{nnn}",
                   "outline": [{"id": "M0", "name": "Foundations"}]},
    "roles": [
        {"name": "architect", "description": "Contracts and ADRs.",
         "owns": ["docs/adr/**"], "handoff_extra": [], "veto": False},
        {"name": "safety", "description": "Floors.",
         "owns": ["tests/safety/**"], "handoff_extra": ["VETO:"], "veto": True},
    ],
    "floors": ["tests/safety/** is append-only"],
    "test_tiers": {"unit": 80, "integration": 70, "floor": 95},
    "toolchain": {"pm": "uv", "test": "uv run pytest", "format": "ruff format",
                  "lint": "ruff check", "types": "mypy"},
    "secrets": ["./.env"],
    "observability": True,
}


def test_minimal_config_loads():
    cfg = KitConfig.from_dict(MINIMAL)
    assert cfg.project.slug == "demo"
    assert cfg.rendered_on == "2026-09-30"
    assert [r.name for r in cfg.roles] == ["architect", "safety"]
    assert cfg.veto_role.name == "safety"


def test_overlapping_ownership_is_rejected():
    bad = {**MINIMAL, "roles": [
        {"name": "a", "description": "d", "owns": ["src/**"], "handoff_extra": [], "veto": False},
        {"name": "b", "description": "d", "owns": ["src/core/**"], "handoff_extra": [], "veto": True},
    ]}
    with pytest.raises(ConfigError, match="overlap"):
        KitConfig.from_dict(bad)


def test_empty_floors_is_rejected():
    with pytest.raises(ConfigError, match="floors"):
        KitConfig.from_dict({**MINIMAL, "floors": []})


def test_floors_require_exactly_one_veto_role():
    bad = {**MINIMAL, "roles": [
        {"name": "a", "description": "d", "owns": ["src/**"], "handoff_extra": [], "veto": False},
    ]}
    with pytest.raises(ConfigError, match="veto"):
        KitConfig.from_dict(bad)


def test_two_veto_roles_is_rejected():
    bad = {**MINIMAL, "roles": [
        {"name": "a", "description": "d", "owns": ["a/**"], "handoff_extra": [], "veto": True},
        {"name": "b", "description": "d", "owns": ["b/**"], "handoff_extra": [], "veto": True},
    ]}
    with pytest.raises(ConfigError, match="veto"):
        KitConfig.from_dict(bad)


def test_forge_cli_must_match_kind():
    bad = {**MINIMAL, "forge": {**MINIMAL["forge"], "cli": "gh"}}
    with pytest.raises(ConfigError, match="cli"):
        KitConfig.from_dict(bad)


def test_duplicate_role_names_rejected():
    bad = {**MINIMAL, "roles": [
        {"name": "a", "description": "d", "owns": ["a/**"], "handoff_extra": [], "veto": True},
        {"name": "a", "description": "d", "owns": ["b/**"], "handoff_extra": [], "veto": False},
    ]}
    with pytest.raises(ConfigError, match="duplicate"):
        KitConfig.from_dict(bad)


def test_lock_json_roundtrips():
    cfg = KitConfig.from_dict(MINIMAL)
    assert KitConfig.from_dict(cfg.to_lock()).to_lock() == cfg.to_lock()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kitgen.model'`

- [ ] **Step 3: Write minimal implementation**

```python
# plugins/agentic-kit/kitgen/src/kitgen/model.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_model.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/kitgen/src/kitgen/model.py plugins/agentic-kit/kitgen/tests/test_model.py
git commit -m "feat(kitgen): KitConfig model enforcing the profile constraints"
```

---

## Task 3: The three fixtures

**Files:**
- Create: `plugins/agentic-kit/kitgen/tests/fixtures/greenfield_prd/profile.yaml`
- Create: `plugins/agentic-kit/kitgen/tests/fixtures/python_monolith/profile.yaml`
- Create: `plugins/agentic-kit/kitgen/tests/fixtures/services_layout/profile.yaml`
- Create: `plugins/agentic-kit/kitgen/tests/conftest.py`
- Test: `plugins/agentic-kit/kitgen/tests/test_fixtures.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_fixtures.py
from kitgen.model import KitConfig

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def test_every_fixture_is_a_valid_profile(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        assert isinstance(cfg, KitConfig)
        assert cfg.veto_role


def test_fixtures_cover_all_three_forge_kinds(load_fixture):
    kinds = {load_fixture(n).forge.kind for n in FIXTURES}
    assert kinds == {"gitlab", "github", "none"}
```

```python
# plugins/agentic-kit/kitgen/tests/conftest.py
from pathlib import Path

import pytest
import yaml

from kitgen.model import KitConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> KitConfig:
        raw = yaml.safe_load((FIXTURE_DIR / name / "profile.yaml").read_text())
        return KitConfig.from_dict(raw)
    return _load
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_fixtures.py -v`
Expected: FAIL — `FileNotFoundError: .../fixtures/greenfield_prd/profile.yaml`

- [ ] **Step 3: Write minimal implementation**

`greenfield_prd/profile.yaml` — a new project with a PRD only, forge `none`, three roles:

```yaml
kit_version: 1.0.0
rendered_on: '2026-09-30'
project: {name: Nimbus, slug: nimbus, summary: "Local-first notes sync service."}
forge: {kind: none, remote: null, cli: none, ci: null, exclusive: false}
attribution: {mention_assistant_in_commits: false}
spine:
  plan: docs/plan/README.md
  strategy: docs/strategy.md
  design: docs/design.md
  decisions: docs/decisions.md
  risks: docs/risk-register.md
  contracts: docs/CONTRACTS.md
  inherited: [docs/PRD.md]
load_order:
  - {path: docs/plan/README.md, mode: full}
  - {path: docs/strategy.md, mode: sections, sections: ["2", "3", "5", "6", "11"]}
  - {path: docs/decisions.md, mode: full}
  - {path: docs/risk-register.md, mode: full}
  - {path: docs/design.md, mode: on_demand}
milestones:
  prefix: M
  id_format: "{milestone}-S{sprint}-{OWNER}-{nnn}"
  outline:
    - {id: M0, name: Foundations}
    - {id: M1, name: Sync engine}
roles:
  - {name: architect, description: "ADRs, contracts, data model.", owns: ["docs/adr/**", "docs/contracts/**"], handoff_extra: [], veto: false}
  - {name: devops, description: "Compose, CI, packaging.", owns: ["docker/**", "compose.yaml"], handoff_extra: ["SERVICES:", "RUNBOOK:"], veto: false}
  - {name: qa, description: "Integration and e2e tiers.", owns: ["tests/e2e/**", "tests/integration/**"], handoff_extra: ["COVERAGE DELTA:"], veto: false}
  - {name: safety, description: "Floors and threat model.", owns: ["tests/safety/**", "docs/security/**"], handoff_extra: ["FLOOR DELTA:", "VETO:"], veto: true}
floors:
  - "no plaintext credentials in the tree"
  - "tests/safety/** is append-only"
test_tiers: {unit: 80, integration: 70, floor: 95}
toolchain: {pm: uv, test: "uv run pytest", format: "ruff format", lint: "ruff check", types: mypy}
secrets: ["./.env", "./secrets/**"]
observability: true
```

`python_monolith/profile.yaml` — forge `github`, adds `data` and `backend`:

```yaml
kit_version: 1.0.0
rendered_on: '2026-09-30'
project: {name: Ledger, slug: ledger, summary: "Single-tenant bookkeeping API."}
forge: {kind: github, remote: "git@github.com:acme/ledger.git", cli: gh, ci: .github/workflows, exclusive: true}
attribution: {mention_assistant_in_commits: true}
spine:
  plan: docs/plan/README.md
  strategy: docs/strategy.md
  design: docs/design.md
  decisions: docs/decisions.md
  risks: docs/risk-register.md
  contracts: docs/CONTRACTS.md
  inherited: []
load_order:
  - {path: docs/plan/README.md, mode: full}
  - {path: docs/strategy.md, mode: sections, sections: ["2", "3", "5", "6", "11"]}
  - {path: docs/decisions.md, mode: full}
  - {path: docs/risk-register.md, mode: full}
  - {path: docs/design.md, mode: on_demand}
milestones:
  prefix: M
  id_format: "{milestone}-S{sprint}-{OWNER}-{nnn}"
  outline: [{id: M0, name: Foundations}]
roles:
  - {name: architect, description: "ADRs and contracts.", owns: ["docs/adr/**"], handoff_extra: [], veto: false}
  - {name: backend, description: "API and business logic.", owns: ["src/ledger/api/**", "src/ledger/services/**"], handoff_extra: [], veto: false}
  - {name: data, description: "Models, migrations, repositories.", owns: ["src/ledger/models/**", "alembic/**"], handoff_extra: ["MIGRATION:", "PII COLUMNS:"], veto: false}
  - {name: devops, description: "CI and containers.", owns: ["docker/**", ".github/workflows/**"], handoff_extra: ["SERVICES:", "RUNBOOK:"], veto: false}
  - {name: qa, description: "Test tiers.", owns: ["tests/integration/**", "tests/e2e/**"], handoff_extra: ["COVERAGE DELTA:"], veto: false}
  - {name: safety, description: "Floors.", owns: ["tests/safety/**"], handoff_extra: ["FLOOR DELTA:", "VETO:"], veto: true}
floors: ["no plaintext credentials in the tree"]
test_tiers: {unit: 85, integration: 75, floor: 95}
toolchain: {pm: poetry, test: "poetry run pytest", format: "black .", lint: "ruff check", types: mypy}
secrets: ["./.env", "./config/secrets.yaml"]
observability: true
```

`services_layout/profile.yaml` — forge `gitlab` with a `github` mirror, eight roles including `frontend` and `worker`:

```yaml
kit_version: 1.0.0
rendered_on: '2026-09-30'
project: {name: Atlas, slug: atlas, summary: "Multi-service document workspace."}
forge: {kind: gitlab, remote: "git@192.168.1.174:acme/atlas.git", cli: glab, ci: .gitlab-ci.yml, exclusive: true, mirror: github}
attribution: {mention_assistant_in_commits: false}
spine:
  plan: docs/plan/README.md
  strategy: docs/strategy.md
  design: docs/design.md
  decisions: docs/decisions.md
  risks: docs/risk-register.md
  contracts: docs/CONTRACTS.md
  inherited: [docs/PRD.md, docs/architecture.md]
load_order:
  - {path: docs/plan/README.md, mode: full}
  - {path: docs/strategy.md, mode: sections, sections: ["2", "3", "5", "6", "11"]}
  - {path: docs/decisions.md, mode: full}
  - {path: docs/risk-register.md, mode: full}
  - {path: docs/design.md, mode: on_demand}
milestones:
  prefix: M
  id_format: "{milestone}-S{sprint}-{OWNER}-{nnn}"
  outline: [{id: M0, name: Foundations}, {id: M1, name: Ingest}, {id: M2, name: Search}]
roles:
  - {name: architect, description: "ADRs, contracts, schemas.", owns: ["docs/adr/**", "packages/protocol/**"], handoff_extra: [], veto: false}
  - {name: backend, description: "API gateway service.", owns: ["services/api/**"], handoff_extra: [], veto: false}
  - {name: worker, description: "Pipeline worker service.", owns: ["services/worker/**"], handoff_extra: [], veto: false}
  - {name: frontend, description: "Web client.", owns: ["services/ui/**"], handoff_extra: ["A11Y:"], veto: false}
  - {name: data, description: "Schema and migrations.", owns: ["services/db/**", "migrations/**"], handoff_extra: ["MIGRATION:", "PII COLUMNS:"], veto: false}
  - {name: devops, description: "Compose, CI, deploy.", owns: ["infra/**", ".gitlab-ci.yml"], handoff_extra: ["SERVICES:", "RUNBOOK:"], veto: false}
  - {name: qa, description: "Integration and e2e.", owns: ["tests/**"], handoff_extra: ["COVERAGE DELTA:"], veto: false}
  - {name: safety, description: "Floors and threat model.", owns: ["services/safety/**", "docs/security/**"], handoff_extra: ["FLOOR DELTA:", "VETO:"], veto: true}
floors:
  - "no plaintext credentials in the tree"
  - "the safety regression tier is append-only"
  - "no telemetry without explicit opt-in"
test_tiers: {unit: 80, integration: 70, floor: 95}
toolchain: {pm: uv, test: "uv run pytest", format: "ruff format", lint: "ruff check", types: mypy}
secrets: ["./.env", "./secrets/**"]
observability: true
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_fixtures.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/kitgen/tests/fixtures plugins/agentic-kit/kitgen/tests/conftest.py plugins/agentic-kit/kitgen/tests/test_fixtures.py
git commit -m "test(kitgen): three profile fixtures covering all forge kinds"
```

---

## Task 4: `render()` skeleton and the manifest contract

**Files:**
- Create: `plugins/agentic-kit/kitgen/src/kitgen/render.py`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/CLAUDE.md.j2`
- Test: `plugins/agentic-kit/kitgen/tests/test_render.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_render.py
import json

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def expected_paths(cfg):
    paths = {
        "CLAUDE.md",
        ".claude/kit.yaml",
        ".claude/kit.lock.json",
        ".claude/settings.json",
        ".claude/agents/orchestrator.md",
        "docs/plan/README.md",
        "docs/strategy.md",
        "docs/design.md",
        "docs/decisions.md",
        "docs/risk-register.md",
        "docs/CONTRACTS.md",
        "docs/adr/0001-adopt-agentic-kit.md",
    }
    for r in cfg.roles:
        paths.add(f".claude/agents/{r.name}.md")
        paths.add(f".claude/agent-memory/{r.name}/MEMORY.md")
    return paths


def test_manifest_has_exactly_the_expected_paths(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        assert set(render(cfg)) == expected_paths(cfg), name


def test_render_is_pure_and_deterministic(load_fixture):
    cfg = load_fixture("services_layout")
    assert render(cfg) == render(cfg)


def test_the_lock_is_written_after_the_yaml(load_fixture):
    """§5.1 reads a yaml newer than the lock as hand-edited drift, and the CLI
    writes in manifest insertion order -- so a clean render must emit yaml first."""
    paths = list(render(load_fixture("services_layout")))
    assert paths.index(".claude/kit.yaml") < paths.index(".claude/kit.lock.json")


def test_lock_is_valid_json_matching_the_config(load_fixture):
    cfg = load_fixture("python_monolith")
    lock = json.loads(render(cfg)[".claude/kit.lock.json"])
    assert lock["project"]["slug"] == "ledger"
    assert [r["name"] for r in lock["roles"]] == [r.name for r in cfg.roles]


def test_claude_md_agent_table_lists_every_role(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        body = render(cfg)["CLAUDE.md"]
        for r in cfg.roles:
            assert f"`{r.name}`" in body, (name, r.name)


def test_claude_md_names_only_the_chosen_forge(load_fixture):
    """The chosen CLI appears as the project's tool. The other CLI may appear ONLY
    inside the "do not propose" sentence -- naming it there is deliberate, and Task 6
    asserts the same intent in the deny rules. So test placement, not absence."""
    gl = render(load_fixture("services_layout"))["CLAUDE.md"]
    assert "`glab` for issues" in gl
    assert "GitHub Actions" in gl and "Do not propose" in gl
    assert "`glab` for issues" in gl.split("Do not propose")[0]

    gh = render(load_fixture("python_monolith"))["CLAUDE.md"]
    assert "`gh` for issues" in gh
    assert "GitLab CI" in gh and "`glab`" in gh.split("Do not propose")[1]

    none = render(load_fixture("greenfield_prd"))["CLAUDE.md"]
    assert "Forge:" not in none
    assert "glab" not in none and "`gh`" not in none


def test_templates_actually_ship_in_the_installed_package():
    """`uv run` installs editable, so Path(__file__)/templates always resolves in
    tests even if the wheel omitted the .j2 files. Assert through the package's
    resource API instead, which is what a non-editable consumer install exercises."""
    from importlib.resources import files
    shipped = {p.name for p in (files("kitgen") / "templates").iterdir()}
    assert "CLAUDE.md.j2" in shipped
    assert all(n.endswith(".j2") for n in shipped), shipped


def test_no_template_placeholder_survives_rendering(load_fixture):
    for name in FIXTURES:
        for path, body in render(load_fixture(name)).items():
            if path.endswith((".md", ".yaml")):
                assert "{{" not in body and "{%" not in body, (name, path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kitgen.render'`

- [ ] **Step 3: Write minimal implementation**

```python
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

# template file -> output path; one entry per singleton output
SINGLETONS = {
    "CLAUDE.md.j2": "CLAUDE.md",
    "settings.json.j2": ".claude/settings.json",
    "orchestrator.md.j2": ".claude/agents/orchestrator.md",
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
```

`templates/CLAUDE.md.j2` — the project root instructions. Forge-neutral by construction:

```jinja
# {{ project.name }} — Project Root

You are in a Claude Code session inside **{{ project.name }}**: {{ project.summary }}

## Your default role: Orchestrator

Unless the user @-mentions a specific subagent, **you are the Orchestrator**: plan, dispatch,
validate handoffs, run gate checks, keep the risk register. You do not write implementation code
yourself — delegate via the Agent tool to a subagent from `.claude/agents/`:

| Agent | Owns |
|---|---|
{% for r in roles %}
| `{{ r.name }}` | {{ r.description }} |
{% endfor %}

Boundaries are file paths, listed per role in `.claude/kit.yaml` and in `{{ cfg.spine.strategy }}` §2.
If a task crosses a boundary, split it or route through `architect`.

## Session-start load order

On the first response of any session, silently read in order:

{% for entry in cfg.load_order %}
{{ loop.index }}. `{{ entry.path }}` — {% if entry.mode == 'full' %}read fully{% elif entry.mode == 'sections' %}§{{ entry.sections | join(', §') }} only{% else %}consult on demand; do not load whole unless the task needs it{% endif %}

{% endfor %}
{% if cfg.spine.inherited %}
Authoritative pre-existing documentation, referenced and never rewritten:
{% for p in cfg.spine.inherited %}
- `{{ p }}`
{% endfor %}
{% endif %}

Then ground the user in one short message: current milestone, next task ID, any open gate.

## How you operate

- **Pragmatic TDD.** Test-first for business logic, data layer, contracts and anything under a floor.
  Test-after with fixtures for adapters and glue; e2e for UI.
- **Trunk-based, one task per branch** `task/<TASK-ID>-<slug>`, Conventional Commits, `test(red):`
  for failing-test commits.
- **Contract-first.** New interfaces start as a spec entry in `{{ cfg.spine.contracts }}` before
  implementation.
- **Floors never regress.** {{ cfg.floors | join('; ') }}. `{{ veto.name }}` holds a veto on gates.
- **Test tiers.** {% for tier, pct in cfg.test_tiers.items() %}{{ tier }} ≥ {{ pct }}%{{ ", " if not loop.last }}{% endfor %}.
{% if cfg.observability %}
- **Observability with the feature.** Every stage lands with counters, latency metrics and
  structured logs, not as a follow-up.
{% endif %}
- **Secrets.** Never read or print {% for s in cfg.secrets %}`{{ s }}`{{ ", " if not loop.last }}{% endfor %}.

## Commands

| | |
|---|---|
| test | `{{ cfg.toolchain.test }}` |
| format | `{{ cfg.toolchain.format }}` |
| lint | `{{ cfg.toolchain.lint }}` |
| types | `{{ cfg.toolchain.types }}` |

{% if forge.kind != 'none' %}
## Forge: {{ forge.kind }}

| | |
|---|---|
| remote | `{{ forge.remote }}` |
| CLI | `{{ forge.cli }}` |
| CI | `{{ forge.ci }}` |
{% if forge.mirror %}
| mirror | `{{ forge.mirror }}` — **a push-mirror only.** Never open issues or PRs there, and never
  treat its issue list as current state. Fetching is fine. |
{% endif %}

- `git push` for code; `{{ forge.cli }}` for issues, reviews, CI.
{% if forge.exclusive %}
- **Only `{{ forge.cli }}`.** Do not propose {% if forge.kind == 'gitlab' %}GitHub Actions, pull
  requests, or `gh`{% else %}GitLab CI, merge requests, or `glab`{% endif %} for this project. The
  `pre-bash-guard` hook enforces this.
{% endif %}
- An issue or review is **outward-facing**: it notifies and is hard to unsay. Confirm with the user
  before creating, editing or closing one, unless they asked for it in that turn. Reading needs no
  confirmation.
- **A local test run is not the pipeline.** After a push, read the pipeline result by **job name**,
  never by its colour: a `skipped` job behind a failed one is not a pass, it is a claim going stale.
{% endif %}

## Task dispatch loop

When the user says "continue", "next task", or runs `/next-task`:

1. Open `{{ cfg.spine.plan }}` → next unblocked task (dependencies satisfied).
2. Read the task block from `{{ cfg.spine.strategy }}` §11 (inputs, outputs, tests, acceptance).
3. Spawn the owning subagent with the task block, its role card, and the referenced design sections.
   Pass file paths, not pasted documents.
4. On return, validate the handoff against acceptance criteria; run the named tests yourself if the
   note lacks evidence.
5. Update `{{ cfg.spine.plan }}`: move the task to Completed, advance the pointer, unblock downstream.
6. If a gate is now ready, tell the user and stop. Do not start `/gate-check` without confirmation.
7. Update `{{ cfg.spine.risks }}` if anything surfaced.

## What you never do

- Write implementation code yourself (delegate).
- Merge with a floor red, or bypass `{{ veto.name }}`'s veto.
- Advance a gate on a failed dimension.
- `git add -A`, `git add .`, `git commit -a`, or `git stash` — commit with
  `git commit --only <path>`. The `pre-bash-guard` hook enforces this.
- Promise dates; milestones complete when gates pass.
{% if not cfg.attribution.mention_assistant_in_commits %}
- Mention the assistant in commit messages, reviews or issue text.
{% endif %}

## Kit

This project uses the `agentic-kit` plugin ({{ cfg.kit_version }}). Its profile is
`.claude/kit.yaml`; `.claude/kit.lock.json` is generated from it and is what hooks read. Process
skills: `/next-task`, `/gate-check`, `/handoff`, `/new-adr`, `/risk`, `/plan-status`. Run
`/kit-upgrade` after updating the plugin.
```

- [ ] **Step 4: Run test to verify it passes**

The remaining templates do not exist yet, so run only the CLAUDE.md-specific tests now:

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render.py -k "agent_table or chosen_forge" -v`
Expected: FAIL — `TemplateNotFound: settings.json.j2`. This is expected: Task 5–7 add the missing templates and the full file passes at Task 7 Step 4. Commit the skeleton now.

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/kitgen/src/kitgen/render.py plugins/agentic-kit/kitgen/src/kitgen/templates/CLAUDE.md.j2 plugins/agentic-kit/kitgen/tests/test_render.py
git commit -m "feat(kitgen): pure render() with the CLAUDE.md template"
```

---

## Task 5: Role card, orchestrator card and agent-memory templates

**Files:**
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/role.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/orchestrator.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/MEMORY.md.j2`
- Test: `plugins/agentic-kit/kitgen/tests/test_render_agents.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_render_agents.py
import re

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def frontmatter(body: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", body, re.S)
    assert m, "role card must open with YAML frontmatter"
    import yaml
    return yaml.safe_load(m.group(1))


def test_every_role_card_declares_its_name_and_description(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        man = render(cfg)
        for r in cfg.roles:
            fm = frontmatter(man[f".claude/agents/{r.name}.md"])
            assert fm["name"] == r.name
            assert fm["description"]
            assert fm["model"] == "inherit"


def test_role_card_lists_its_owned_paths_and_forbids_others(load_fixture):
    cfg = load_fixture("services_layout")
    man = render(cfg)
    card = man[".claude/agents/backend.md"]
    assert "services/api/**" in card
    assert "Never:" in card
    assert "services/ui/**" in card  # named as another role's territory


def test_role_card_carries_the_atomic_commit_rule(load_fixture):
    cfg = load_fixture("python_monolith")
    for r in cfg.roles:
        card = render(cfg)[f".claude/agents/{r.name}.md"]
        assert "git commit --only" in card
        assert "git add -A" in card


def test_veto_role_card_states_the_veto_and_the_floors(load_fixture):
    cfg = load_fixture("services_layout")
    card = render(cfg)[f".claude/agents/{cfg.veto_role.name}.md"]
    assert "veto" in card.lower()
    for floor in cfg.floors:
        assert floor in card


def test_non_veto_cards_do_not_claim_a_veto(load_fixture):
    cfg = load_fixture("services_layout")
    man = render(cfg)
    for r in cfg.roles:
        if not r.veto:
            assert "veto on gates" not in man[f".claude/agents/{r.name}.md"]


def test_orchestrator_card_forbids_writing_code(load_fixture):
    card = render(load_fixture("greenfield_prd"))[".claude/agents/orchestrator.md"]
    assert "do not write implementation code" in card.lower()


def test_memory_stub_explains_the_linked_index_convention(load_fixture):
    cfg = load_fixture("python_monolith")
    stub = render(cfg)[".claude/agent-memory/data/MEMORY.md"]
    assert "one fact per file" in stub.lower()
    assert "[[" in stub
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render_agents.py -v`
Expected: FAIL — `TemplateNotFound: role.md.j2`

- [ ] **Step 3: Write minimal implementation**

`templates/role.md.j2`:

```jinja
---
name: {{ role.name }}
description: {{ role.description }}
tools: {{ role.tools | join(', ') }}
model: inherit
memory: project
---

You are the **{{ role.name }}** engineer for {{ project.name }}.

## Boundaries

Own:
{% for p in role.owns %}
- `{{ p }}`
{% endfor %}

Never edit another role's territory — request the change instead:
{% for other in roles %}
{% if other.name != role.name %}
- `{{ other.name }}`: {% for p in other.owns %}`{{ p }}`{{ ", " if not loop.last }}{% endfor %}

{% endif %}
{% endfor %}

## TDD

Test-first for logic, contracts and anything under a floor; test-after with fixtures for glue.
Tiers: {% for tier, pct in cfg.test_tiers.items() %}{{ tier }} ≥ {{ pct }}%{{ ", " if not loop.last }}{% endfor %}.
Run `{{ cfg.toolchain.test }}` and paste the command plus its last line in your handoff. Never claim
green without running it.

## Floors{% if role.veto %} — you hold the veto{% endif %}

{% for floor in cfg.floors %}
- {{ floor }}
{% endfor %}
{% if role.veto %}

You have a **veto on gates**. A gate cannot advance while a floor is red, and your verdict
(APPROVE / VETO) is a required signature on every gate bundle.
{% else %}

If your task touches a floor, request review from `{{ veto.name }}` before handoff.
{% endif %}

## Atomic-commit discipline

Commit with `git commit --only <path> [-- <path>...]` and explicit paths. `--only` commits **only**
the named paths even when other files are staged, which structurally prevents sweeping a peer
agent's staged work into your commit. Forbidden: `git add -A`, `git add .`, `git commit -a`.

If foreign files appear in `git status`, **stop and report to the Orchestrator**. Do not attempt
`git stash` recovery — restoring a stash has itself been a contamination vector.

## Memory

Keep `.claude/agent-memory/{{ role.name }}/MEMORY.md` current: one fact per file, a one-line index
entry per fact, `[[wikilinks]]` between related facts.

## Handoff

End every task by running `/handoff`. Your role-specific lines:
{% if role.handoff_extra %}
{% for line in role.handoff_extra %}
- `{{ line }}`
{% endfor %}
{% else %}
- none beyond the common note
{% endif %}
```

`templates/orchestrator.md.j2`:

```jinja
---
name: orchestrator
description: Plan, dispatch, validate handoffs, run gate checks, keep the risk register. The default role.
tools: Read, Glob, Grep, Bash, Agent
model: inherit
---

You are the **Orchestrator** for {{ project.name }}. You plan, dispatch, validate and record. You
**do not write implementation code yourself** — delegate to a role from `.claude/agents/`.

## Roster

| Agent | Owns |
|---|---|
{% for r in roles %}
| `{{ r.name }}` | {% for p in r.owns %}`{{ p }}`{{ ", " if not loop.last }}{% endfor %} |
{% endfor %}

## Dispatch

Follow the loop in `CLAUDE.md`. Pass file paths, never pasted documents. Include the atomic-commit
rule in every dispatch brief.

**Parallel dispatch requires worktree isolation.** When two or more agents are dispatched in one
message, or a dispatched agent's scope overlaps an in-flight peer, set `isolation: "worktree"` on the
Agent call. Agents sharing one working tree share one index, and that is the whole cause of
cross-agent staging leaks. On return: verify the handoff and commit SHA, cherry-pick onto the trunk,
remove the worktree, and record both SHAs in the handoff note.

## Validation

A handoff without a pasted test command and its result is not evidence. Run the named tests yourself
(`{{ cfg.toolchain.test }}`) before accepting. Accept, or record the gap and re-dispatch once; after
a second failure, stop and report to the user.

## Never

- Write implementation code yourself.
- Merge with a floor red, or bypass `{{ veto.name }}`'s veto.
- Advance a gate on a failed dimension.
- Promise dates.
```

`templates/MEMORY.md.j2`:

```jinja
# {{ role.name }} — agent memory

One fact per file in this directory; one line here per fact, newest last. Link related facts with
`[[filename-without-extension]]`. Write a fact when something cost you time to discover and would
cost the next session the same: an endpoint quirk, a tool that lied, a constraint the code does not
state.

Do not record what the repository already says — structure, history, or anything in `CLAUDE.md`.

<!-- Example, delete when the first real fact lands:
- [A guessed URL is not a measurement](a-guessed-url-is-not-a-measurement.md) — probe before
  asserting; see also [[fixture-provenance-rule]].
-->
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render_agents.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/kitgen/src/kitgen/templates/role.md.j2 plugins/agentic-kit/kitgen/src/kitgen/templates/orchestrator.md.j2 plugins/agentic-kit/kitgen/src/kitgen/templates/MEMORY.md.j2 plugins/agentic-kit/kitgen/tests/test_render_agents.py
git commit -m "feat(kitgen): role card, orchestrator card and agent-memory templates"
```

---

## Task 6: `settings.json` template

**Files:**
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/settings.json.j2`
- Test: `plugins/agentic-kit/kitgen/tests/test_render_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_render_settings.py
import json

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def settings(cfg):
    return json.loads(render(cfg)[".claude/settings.json"])


def test_settings_is_valid_json(load_fixture):
    for name in FIXTURES:
        assert settings(load_fixture(name))["permissions"]


def test_every_secret_path_is_denied_for_read_and_edit(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        deny = settings(cfg)["permissions"]["deny"]
        for s in cfg.secrets:
            assert f"Read({s})" in deny, (name, s)
            assert f"Edit({s})" in deny, (name, s)


def test_destructive_commands_are_denied(load_fixture):
    deny = settings(load_fixture("services_layout"))["permissions"]["deny"]
    for entry in ["Bash(rm -rf:*)", "Bash(git push --force:*)",
                  "Bash(git reset --hard:*)", "Bash(docker compose down -v:*)"]:
        assert entry in deny


def test_the_other_forge_cli_is_denied_when_exclusive(load_fixture):
    gl = settings(load_fixture("services_layout"))["permissions"]["deny"]
    assert "Bash(gh:*)" in gl
    gh = settings(load_fixture("python_monolith"))["permissions"]["deny"]
    assert "Bash(glab:*)" in gh


def test_no_forge_denies_neither_cli(load_fixture):
    deny = settings(load_fixture("greenfield_prd"))["permissions"]["deny"]
    assert "Bash(gh:*)" not in deny and "Bash(glab:*)" not in deny


def test_toolchain_commands_are_allowed(load_fixture):
    cfg = load_fixture("python_monolith")
    allow = settings(cfg)["permissions"]["allow"]
    assert "Bash(poetry run pytest:*)" in allow
    assert "Bash(black .:*)" in allow


def test_subagent_spawn_depth_is_capped(load_fixture):
    assert settings(load_fixture("greenfield_prd"))["env"][
        "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] == "1"


def test_orchestrator_cannot_spawn_itself(load_fixture):
    assert "Agent(orchestrator)" in settings(
        load_fixture("greenfield_prd"))["permissions"]["deny"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render_settings.py -v`
Expected: FAIL — `TemplateNotFound: settings.json.j2`

- [ ] **Step 3: Write minimal implementation**

```jinja
{# templates/settings.json.j2 #}
{
  "permissions": {
    "allow": [
      "Read",
      "Edit",
      "Write",
      "Glob",
      "Grep",
      "Bash({{ cfg.toolchain.test }}:*)",
      "Bash({{ cfg.toolchain.format }}:*)",
      "Bash({{ cfg.toolchain.lint }}:*)",
      "Bash({{ cfg.toolchain.types }}:*)",
      "Bash({{ cfg.toolchain.pm }}:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git commit --only:*)",
      "Bash(git switch:*)",
      "Bash(git worktree:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(sed -n:*)"
{% if forge.kind != 'none' %}
      ,"Bash({{ forge.cli }}:*)"
{% endif %}
    ],
    "deny": [
{% for s in cfg.secrets %}
      "Read({{ s }})",
      "Edit({{ s }})",
{% endfor %}
      "Edit(./.claude/settings.json)",
      "Edit(./.claude/kit.lock.json)",
      "Bash(rm -rf:*)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(git reset --hard:*)",
      "Bash(git add -A:*)",
      "Bash(git add .:*)",
      "Bash(git commit -a:*)",
      "Bash(git stash:*)",
      "Bash(docker compose down -v:*)",
      "Agent(orchestrator)"
{% if forge.exclusive and forge.kind == 'gitlab' %}
      ,"Bash(gh:*)"
{% elif forge.exclusive and forge.kind == 'github' %}
      ,"Bash(glab:*)"
{% endif %}
    ]
  },
  "env": {
    "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1"
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render_settings.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/kitgen/src/kitgen/templates/settings.json.j2 plugins/agentic-kit/kitgen/tests/test_render_settings.py
git commit -m "feat(kitgen): settings.json template with forge-neutral deny rules"
```

---

## Task 7: The docs spine templates

`strategy.md` renders its operating model in full and its task graph with milestone 0 only, per spec §7.4.

**Files:**
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/strategy.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/plan.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/design.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/decisions.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/risk-register.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/CONTRACTS.md.j2`
- Create: `plugins/agentic-kit/kitgen/src/kitgen/templates/adr-0001.md.j2`
- Test: `plugins/agentic-kit/kitgen/tests/test_render_spine.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_render_spine.py
import re

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def test_strategy_ownership_table_matches_the_roles(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        body = render(cfg)["docs/strategy.md"]
        for r in cfg.roles:
            assert f"`{r.name}`" in body, (name, r.name)
            for p in r.owns:
                assert p in body, (name, p)


def test_strategy_states_every_floor_and_the_veto_holder(load_fixture):
    cfg = load_fixture("services_layout")
    body = render(cfg)["docs/strategy.md"]
    for floor in cfg.floors:
        assert floor in body
    assert cfg.veto_role.name in body


def test_strategy_expands_only_milestone_zero(load_fixture):
    cfg = load_fixture("services_layout")
    body = render(cfg)["docs/strategy.md"]
    assert "M0-S1-" in body
    assert "M1-S1-" not in body
    assert "M1 — Ingest" in body  # later milestones present as outline only


def test_plan_pointer_starts_at_the_first_m0_task(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        body = render(cfg)["docs/plan/README.md"]
        assert re.search(r"Next task\W+.*M0-S1-", body), name
        assert "## Completed" in body


def test_plan_forbids_subagent_edits(load_fixture):
    body = render(load_fixture("greenfield_prd"))["docs/plan/README.md"]
    assert "Subagents never edit this file" in body


def test_design_references_inherited_docs_without_restating(load_fixture):
    cfg = load_fixture("services_layout")
    body = render(cfg)["docs/design.md"]
    for p in cfg.spine["inherited"]:
        assert p in body
    assert "authoritative" in body.lower()


def test_design_has_no_inherited_section_when_none(load_fixture):
    body = render(load_fixture("python_monolith"))["docs/design.md"]
    assert "Inherited documentation" not in body


def test_risk_register_has_a_table_header_and_no_invented_rows(load_fixture):
    body = render(load_fixture("greenfield_prd"))["docs/risk-register.md"]
    assert "| ID | Risk |" in body
    assert "R-001" not in body


def test_adr_0001_records_the_install(load_fixture):
    cfg = load_fixture("python_monolith")
    body = render(cfg)["docs/adr/0001-adopt-agentic-kit.md"]
    assert "Accepted" in body
    assert cfg.rendered_on in body
    assert cfg.kit_version in body
    assert cfg.veto_role.name in body


def test_contracts_is_empty_but_structured(load_fixture):
    body = render(load_fixture("greenfield_prd"))["docs/CONTRACTS.md"]
    assert "## Change log" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render_spine.py -v`
Expected: FAIL — `TemplateNotFound: strategy.md.j2`

- [ ] **Step 3: Write minimal implementation**

`templates/strategy.md.j2`:

```jinja
# {{ project.name }} — Strategy

The operating model. `{{ cfg.spine.plan }}` holds current state; this file holds the rules and the
task graph.

## 1. Roles

The Orchestrator plans and dispatches and writes no implementation code. Each role below owns file
paths, exclusively.

## 2. Ownership map

| Role | Owns | Handoff extras |
|---|---|---|
{% for r in roles %}
| `{{ r.name }}` | {% for p in r.owns %}`{{ p }}`{{ ", " if not loop.last }}{% endfor %} | {% if r.handoff_extra %}{% for h in r.handoff_extra %}`{{ h }}`{{ ", " if not loop.last }}{% endfor %}{% else %}—{% endif %} |
{% endfor %}

A task crossing a boundary is split, or routed through `architect`. Ownership globs do not overlap;
`kitgen verify` enforces that.

## 3. Test tiers

| Tier | Floor |
|---|---|
{% for tier, pct in cfg.test_tiers.items() %}
| {{ tier }} | {{ pct }}% |
{% endfor %}

Pragmatic TDD: test-first for logic, contracts, the data layer and anything under a floor;
test-after with fixtures for adapters and glue; e2e for UI. `test(red):` prefixes a failing-test
commit.

## 4. Branching

Trunk-based, one task per branch `task/<TASK-ID>-<slug>`, Conventional Commits. Commits use
`git commit --only <path>`. Parallel dispatch uses worktree isolation.

## 5. Gates

A gate is checked across five dimensions: **Functional**, **Tests**, **Floors**, **Operational**,
and the milestone's own additions. Verdicts: **PASS**, **CONDITIONAL** (each condition carries an
owner and a deadline task ID), **BLOCK**. A failed dimension blocks; no dimension is averaged away.

`{{ veto.name }}` produces the Floors dimension and signs it APPROVE or VETO. A VETO is not
overridable by the Orchestrator.

A CONDITIONAL that survives two milestones is itself a finding and must be raised to the user, not
carried silently.

## 6. Floors — never regress

{% for floor in cfg.floors %}
{{ loop.index }}. {{ floor }}
{% endfor %}

Floors are append-only. Removing or weakening one requires an ADR and the user's explicit agreement.
{% if cfg.observability %}

## 7. Observability

Every stage lands with counters, latency metrics and structured logs in the same task that
implements it — never as a follow-up.
{% endif %}

## 8. Contracts

New or changed interfaces are recorded in `{{ cfg.spine.contracts }}` **before** implementation,
with a version and a diff entry.

## 9. Handoffs

Every task ends with a `/handoff` note. Evidence over prose: the test command and its last line. A
note without a pasted run is not evidence and the Orchestrator re-runs the tests itself.

## 10. Milestones

| ID | Name | Status |
|---|---|---|
{% for m in cfg.milestones.outline %}
| {{ m.id }} | {{ m.name }} | {% if loop.first %}open{% else %}not started{% endif %} |
{% endfor %}

## 11. Task graph

Task IDs follow `{{ cfg.milestones.id_format }}`. **Only the open milestone is expanded here.** The
Orchestrator expands the next milestone's tasks at gate time; a graph written further ahead than the
work is invented work.

### {{ cfg.milestones.outline[0].id }} — {{ cfg.milestones.outline[0].name }}

**Entry conditions**

- [ ] The user has reviewed {% if cfg.spine.inherited %}{% for p in cfg.spine.inherited %}`{{ p }}`{{ ", " if not loop.last }}{% endfor %} and {% endif %}this file.
- [ ] The role roster in §2 is accepted.
- [ ] The floors in §6 are accepted.
{% if forge.kind != 'none' %}
- [ ] `{{ forge.remote }}` is reachable and `{{ forge.cli }}` is authenticated.
{% endif %}

**Tasks**

| ID | Owner | Outputs | Tests | Acceptance |
|---|---|---|---|---|
| {{ cfg.milestones.outline[0].id }}-S1-ARCH-001 | `architect` | `{{ cfg.spine.contracts }}` first entry; ADR for the module boundaries | contract test skeleton | Boundaries match §2 and the user accepts them |
| {{ cfg.milestones.outline[0].id }}-S1-DEVOPS-002 | `devops` | dev environment reproducible from a clean clone; `{{ cfg.toolchain.test }}` runs | the suite runs green and empty | A clean clone reaches a green run in one documented command |
| {{ cfg.milestones.outline[0].id }}-S1-{{ veto.name | upper }}-003 | `{{ veto.name }}` | the floor test tier exists and is wired into CI, one test per floor in §6 | floor tier green | Each floor in §6 has at least one test that fails when it is violated |
| {{ cfg.milestones.outline[0].id }}-S1-QA-004 | `qa` | tier thresholds from §3 enforced in CI | coverage gate fails below floor | A deliberate coverage drop reddens the pipeline |

**Gate additions:** the floor tier must be non-empty and green, and every floor in §6 must map to a
named test.
```

`templates/plan.md.j2`:

```jinja
# Dispatch State

**Owner.** Orchestrator. **Updated.** After every task completion and every gate.

Source of truth for "what is next". Subagents never edit this file; they emit handoff notes and the
Orchestrator updates here.

---

## Current milestone

**{{ cfg.milestones.outline[0].id }} — {{ cfg.milestones.outline[0].name }}.** Not yet entered.
Confirm the entry conditions in `{{ cfg.spine.strategy }}` §11 with the user before dispatching
anything.

## Next task

**{{ cfg.milestones.outline[0].id }}-S1-ARCH-001** — owner `architect`. Depends: none.

## Active

_none_

## Completed

_none_

## Blocked

_none_

## Open gates

_none. {{ cfg.milestones.outline[0].id }} opens once its entry conditions are confirmed._
```

`templates/design.md.j2`:

```jinja
# {{ project.name }} — Design

{{ project.summary }}

{% if cfg.spine.inherited %}
## Inherited documentation

These files are **authoritative** and are not restated or rewritten here. Read them directly:

{% for p in cfg.spine.inherited %}
- `{{ p }}`
{% endfor %}

This file records design that those documents do not cover, and decisions taken after them.

{% endif %}
## Module boundaries

Each role in `{{ cfg.spine.strategy }}` §2 owns a boundary. The interfaces between them are recorded
in `{{ cfg.spine.contracts }}`.

{% for r in roles %}
### {{ r.name }}

{{ r.description }} Owns {% for p in r.owns %}`{{ p }}`{{ ", " if not loop.last }}{% endfor %}.

_Design notes: to be written by `{{ r.name }}` as the boundary takes shape._

{% endfor %}
```

`templates/decisions.md.j2`:

```jinja
# Decisions

Durable decisions, newest last. Anything with a real trade-off gets an ADR in `docs/adr/`; this file
is the index plus the small rulings that do not warrant one.

## ADR index

| ADR | Title | Status |
|---|---|---|
| [0001](adr/0001-adopt-agentic-kit.md) | Adopt the agentic-kit orchestrator model | Accepted |

## Rulings

_none yet_
```

`templates/risk-register.md.j2`:

```jinja
# Risk register

**Owner.** Orchestrator. Reviewed at every gate. A risk is closed by evidence, not by time passing.

| ID | Risk | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|

Add rows with `/risk`. Number them `R-001` upward and never reuse a number.
```

`templates/CONTRACTS.md.j2`:

```jinja
# Contracts

Every interface crossing a role boundary is recorded here **before** it is implemented: shape,
version, and what changed.

## Current

_none yet_

## Change log

| Date | Contract | Version | Change | Task |
|---|---|---|---|---|
```

`templates/adr-0001.md.j2`:

```jinja
# ADR 0001 — Adopt the agentic-kit orchestrator model

**Status** Accepted · **Date** {{ cfg.rendered_on }} · **Kit version** {{ cfg.kit_version }}

## Context

{{ project.name }} is developed with Claude Code sessions. Without an explicit operating model, work
arrives without owners, tests are claimed rather than run, and invariants regress silently.

## Decision

Adopt the `agentic-kit` orchestrator model:

- A default **Orchestrator** that plans, dispatches and validates, and writes no implementation code.
- {{ roles | length }} roles with **exclusive file-path ownership**, listed in
  `{{ cfg.spine.strategy }}` §2.
- **`{{ veto.name }}` holds a veto** on gates, scoped to the floors in §6.
- A docs spine as the source of truth: `{{ cfg.spine.plan }}` for state,
  `{{ cfg.spine.strategy }}` for rules and the task graph.
- Handoff notes carrying pasted test evidence.
- Guard hooks from the plugin that make the atomic-commit and secret-path rules executable rather
  than advisory.

## Consequences

- The first turn of a session costs a documented read of the load order in `CLAUDE.md`.
- Ownership boundaries must partition; adding a role means redistributing globs.
- Floors cannot be weakened without a further ADR.
{% if forge.kind != 'none' %}
- `{{ forge.cli }}` is the only forge CLI{% if forge.exclusive %}, enforced by `pre-bash-guard`{% endif %}.
{% endif %}
```

- [ ] **Step 4: Run all render tests to verify they pass**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_render.py tests/test_render_spine.py tests/test_render_agents.py tests/test_render_settings.py -v`
Expected: PASS — all four render test files green, including the Task 4 tests that were blocked on missing templates.

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/kitgen/src/kitgen/templates plugins/agentic-kit/kitgen/tests/test_render_spine.py
git commit -m "feat(kitgen): docs spine templates, M0-only task graph"
```

---

## Task 8: Cross-reference verifier

**Files:**
- Create: `plugins/agentic-kit/kitgen/src/kitgen/verify.py`
- Test: `plugins/agentic-kit/kitgen/tests/test_verify.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_verify.py
import json

from kitgen.render import render
from kitgen.verify import verify

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def test_freshly_rendered_manifests_verify_clean(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        assert verify(render(cfg), cfg) == [], name


def test_missing_role_card_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    del man[".claude/agents/data.md"]
    problems = verify(man, cfg)
    assert any("data" in p and "agents/data.md" in p for p in problems)


def test_role_absent_from_the_claude_md_table_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    man["CLAUDE.md"] = man["CLAUDE.md"].replace("`data`", "`dta`")
    assert any("CLAUDE.md" in p and "data" in p for p in verify(man, cfg))


def test_handoff_extra_missing_from_a_role_card_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    man[".claude/agents/data.md"] = man[".claude/agents/data.md"].replace(
        "MIGRATION:", "MIGRATIONS:")
    assert any("MIGRATION:" in p for p in verify(man, cfg))


def test_secret_not_denied_in_settings_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    s = json.loads(man[".claude/settings.json"])
    s["permissions"]["deny"] = [d for d in s["permissions"]["deny"]
                                if "./.env" not in d]
    man[".claude/settings.json"] = json.dumps(s)
    assert any("./.env" in p for p in verify(man, cfg))


def test_spine_path_neither_rendered_nor_on_disk_is_reported(load_fixture, tmp_path):
    cfg = load_fixture("services_layout")
    man = render(cfg)
    problems = verify(man, cfg, project_root=tmp_path)
    assert any("docs/PRD.md" in p for p in problems)


def test_inherited_path_present_on_disk_is_accepted(load_fixture, tmp_path):
    cfg = load_fixture("services_layout")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/PRD.md").write_text("prd")
    (tmp_path / "docs/architecture.md").write_text("arch")
    assert verify(render(cfg), cfg, project_root=tmp_path) == []


def test_lock_disagreeing_with_the_config_is_reported(load_fixture):
    cfg = load_fixture("python_monolith")
    man = render(cfg)
    lock = json.loads(man[".claude/kit.lock.json"])
    lock["project"]["slug"] = "tampered"
    man[".claude/kit.lock.json"] = json.dumps(lock)
    assert any("kit.lock.json" in p for p in verify(man, cfg))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_verify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kitgen.verify'`

- [ ] **Step 3: Write minimal implementation**

```python
# plugins/agentic-kit/kitgen/src/kitgen/verify.py
"""Cross-reference checks over a rendered manifest. Returns a list of problems.

An empty list means the manifest is internally consistent. Run this before writing
anything to disk. See design spec §9.1.
"""
from __future__ import annotations

import json
from pathlib import Path

from .model import KitConfig


def verify(manifest: dict[str, str], cfg: KitConfig,
           project_root: Path | None = None) -> list[str]:
    problems: list[str] = []
    claude_md = manifest.get("CLAUDE.md", "")

    for r in cfg.roles:
        card = f".claude/agents/{r.name}.md"
        if card not in manifest:
            problems.append(f"role {r.name!r}: no {card} in the manifest")
        mem = f".claude/agent-memory/{r.name}/MEMORY.md"
        if mem not in manifest:
            problems.append(f"role {r.name!r}: no {mem} in the manifest")
        if f"`{r.name}`" not in claude_md:
            problems.append(
                f"role {r.name!r}: absent from the CLAUDE.md agent table")
        for extra in r.handoff_extra:
            if extra not in manifest.get(card, ""):
                problems.append(
                    f"role {r.name!r}: handoff line {extra!r} missing from {card}")

    declared = {p.split("/")[-1].removesuffix(".md")
                for p in manifest if p.startswith(".claude/agents/")}
    expected = {r.name for r in cfg.roles} | {"orchestrator"}
    for extra in declared - expected:
        problems.append(f"agent card {extra!r} has no matching role in kit.yaml")

    strategy = manifest.get(cfg.spine["strategy"], "")
    for r in cfg.roles:
        for glob in r.owns:
            if glob not in strategy:
                problems.append(
                    f"ownership {r.name}:{glob} missing from the strategy §2 table")

    try:
        settings = json.loads(manifest[".claude/settings.json"])
        deny = settings["permissions"]["deny"]
    except (KeyError, json.JSONDecodeError) as exc:
        problems.append(f".claude/settings.json is not usable: {exc}")
    else:
        for s in cfg.secrets:
            if f"Read({s})" not in deny or f"Edit({s})" not in deny:
                problems.append(f"secret {s!r} is not denied for both Read and Edit")

    try:
        lock = json.loads(manifest[".claude/kit.lock.json"])
    except (KeyError, json.JSONDecodeError) as exc:
        problems.append(f".claude/kit.lock.json is not usable: {exc}")
    else:
        if lock != cfg.to_lock():
            problems.append(".claude/kit.lock.json does not match the config it came from")

    # With no project_root we cannot inspect the disk, so the on-disk half of this
    # check is SKIPPED rather than treated as a failure. spine.inherited names
    # pre-existing authoritative docs that are deliberately never rendered (§7.1),
    # so treating "absent from the manifest" as a problem would make every
    # freshly-rendered kit verify dirty.
    if project_root is not None:
        for label, path in cfg.spine.items():
            paths = path if isinstance(path, list) else [path]
            for p in paths:
                if p in manifest or (project_root / p).exists():
                    continue
                problems.append(
                    f"spine.{label} path {p!r} is neither rendered nor present on disk")

        for entry in cfg.load_order:
            p = entry["path"]
            if p not in manifest and not (project_root / p).exists():
                problems.append(
                    f"load_order path {p!r} is neither rendered nor on disk")

    return problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_verify.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/kitgen/src/kitgen/verify.py plugins/agentic-kit/kitgen/tests/test_verify.py
git commit -m "feat(kitgen): cross-reference verifier over rendered manifests"
```

---

## Task 9: CLI

**Files:**
- Create: `plugins/agentic-kit/kitgen/src/kitgen/cli.py`
- Modify: `plugins/agentic-kit/kitgen/src/kitgen/__init__.py` (exists from Task 1, currently empty)
- Test: `plugins/agentic-kit/kitgen/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_cli.py
import json
from pathlib import Path

import pytest

from kitgen.cli import main

FIXTURE = Path(__file__).parent / "fixtures/services_layout/profile.yaml"


def test_render_writes_the_manifest_to_a_target_tree(tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/PRD.md").write_text("prd")
    (tmp_path / "docs/architecture.md").write_text("arch")
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".claude/kit.lock.json").exists()
    assert (tmp_path / ".claude/agents/safety.md").exists()
    written = json.loads(capsys.readouterr().out)["written"]
    assert "CLAUDE.md" in written


def test_render_refuses_to_overwrite_without_force(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/PRD.md").write_text("prd")
    (tmp_path / "docs/architecture.md").write_text("arch")
    (tmp_path / "CLAUDE.md").write_text("existing")
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path)])
    assert rc == 3
    assert (tmp_path / "CLAUDE.md").read_text() == "existing"


def test_dry_run_writes_nothing_and_prints_the_manifest(tmp_path, capsys):
    rc = main(["render", "--profile", str(FIXTURE), "--out", str(tmp_path),
               "--dry-run"])
    assert rc == 0
    assert not (tmp_path / "CLAUDE.md").exists()
    assert "CLAUDE.md" in json.loads(capsys.readouterr().out)["manifest"]


def test_verify_reports_problems_and_exits_nonzero(tmp_path, capsys):
    rc = main(["verify", "--profile", str(FIXTURE), "--root", str(tmp_path)])
    assert rc == 1
    assert "docs/PRD.md" in capsys.readouterr().out


def test_invalid_profile_exits_two(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("kit_version: 1.0.0\n")
    rc = main(["verify", "--profile", str(bad), "--root", str(tmp_path)])
    assert rc == 2


def test_unparseable_yaml_exits_two(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("kit_version: [1.0.0\n")
    assert main(["verify", "--profile", str(bad), "--root", str(tmp_path)]) == 2
    assert "invalid profile" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kitgen.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# plugins/agentic-kit/kitgen/src/kitgen/__init__.py
from .model import ConfigError, KitConfig
from .render import render
from .verify import verify

__all__ = ["ConfigError", "KitConfig", "render", "verify"]
```

```python
# plugins/agentic-kit/kitgen/src/kitgen/cli.py
"""kitgen CLI. Exit codes: 0 ok, 1 verification problems, 2 bad profile, 3 refused."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jinja2 import UndefinedError

from .model import ConfigError, KitConfig
from .render import render
from .verify import verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kitgen")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a profile into a project tree")
    r.add_argument("--profile", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--rendered-on", default=None,
                   help="ISO date recorded in the kit; defaults to the profile's value")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--force", action="store_true",
                   help="overwrite files that already exist")

    v = sub.add_parser("verify", help="verify a rendered kit against its profile")
    v.add_argument("--profile", type=Path, required=True)
    v.add_argument("--root", type=Path, required=True)

    args = parser.parse_args(argv)

    try:
        raw = yaml.safe_load(args.profile.read_text())
        if getattr(args, "rendered_on", None):
            raw["rendered_on"] = args.rendered_on
        cfg = KitConfig.from_dict(raw)
    except (ConfigError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(f"invalid profile: {exc}", file=sys.stderr)
        return 2

    # jinja2.UndefinedError is NOT a ConfigError/KeyError/TypeError subclass, so
    # without this a profile that passed validation but still trips StrictUndefined
    # would exit 1 ("verification problems") instead of 2 ("bad profile").
    try:
        manifest = render(cfg)
    except UndefinedError as exc:
        print(f"invalid profile: template needs a field the profile lacks: {exc}",
              file=sys.stderr)
        return 2

    if args.cmd == "verify":
        problems = verify(manifest, cfg, project_root=args.root)
        for p in problems:
            print(p)
        return 1 if problems else 0

    if args.dry_run:
        print(json.dumps({"manifest": sorted(manifest)}, indent=2))
        return 0

    problems = verify(manifest, cfg, project_root=args.out)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    if not args.force:
        clashes = [p for p in manifest if (args.out / p).exists()]
        if clashes:
            print(f"refusing to overwrite: {sorted(clashes)}", file=sys.stderr)
            return 3

    for path, content in manifest.items():
        target = args.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    print(json.dumps({"written": sorted(manifest)}, indent=2))
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_cli.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Document how a consumer invokes it**

The installing skills will not have `kitgen` on `PATH` — the plugin lands in Claude Code's plugin
cache, not in a venv the project knows about. Add this line to the module docstring of `cli.py` and
use the same form in every skill that calls it:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}/kitgen" kitgen render --profile <p> --out <dir>
```

`--project` builds its venv under the plugin cache directory on first use, so treat a read-only or
non-writable plugin cache as a real failure mode and report it rather than falling back silently.

- [ ] **Step 6: Commit**

```bash
git add plugins/agentic-kit/kitgen/src/kitgen/cli.py plugins/agentic-kit/kitgen/src/kitgen/__init__.py plugins/agentic-kit/kitgen/tests/test_cli.py
git commit -m "feat(kitgen): CLI with render, verify, dry-run and overwrite refusal"
```

---

## Task 10: Hook library and the inertness rule

This is the task that keeps a globally installed plugin from disturbing every other repository on the machine.

**Files:**
- Create: `plugins/agentic-kit/hooks/lib/kitlock.sh`
- Test: `plugins/agentic-kit/kitgen/tests/test_hooks_inert.py`
- Test: `plugins/agentic-kit/kitgen/tests/hooks_conftest.py`
- (`tests/__init__.py` already exists from Task 1 — do not recreate it)

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/hooks_conftest.py
"""Helpers for driving the Bash hooks the way Claude Code does."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "hooks"


def run_hook(name: str, payload: dict, project_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOKS / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(HOOKS.parent),
             "CLAUDE_PROJECT_DIR": str(project_dir)},
    )


def bash_payload(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def file_payload(tool: str, file_path: str, cwd: Path) -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": file_path}, "cwd": str(cwd)}
```

```python
# plugins/agentic-kit/kitgen/tests/test_hooks_inert.py
"""The blast-radius test: with no kit.lock.json every hook must be a no-op."""
import json

import pytest

from .hooks_conftest import bash_payload, file_payload, run_hook

ALL_HOOKS = ["pre-bash-guard.sh", "pre-file-guard.sh",
             "post-edit-format.sh", "subagent-stop-check.sh"]


@pytest.fixture
def bare_project(tmp_path):
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_hook_is_inert_without_a_lock(hook, bare_project):
    payload = bash_payload("git add -A", bare_project)
    payload.update(file_payload("Edit", str(bare_project / ".env"), bare_project))
    r = run_hook(hook, payload, bare_project)
    assert r.returncode == 0, (hook, r.stderr)
    assert r.stdout.strip() in ("", '{"continue": true}'), (hook, r.stdout)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_hook_is_inert_when_the_lock_is_unparseable(hook, bare_project):
    (bare_project / ".claude").mkdir()
    (bare_project / ".claude/kit.lock.json").write_text("{ not json")
    r = run_hook(hook, bash_payload("git add -A", bare_project), bare_project)
    assert r.returncode == 0, (hook, r.stderr)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_hook_is_inert_on_empty_stdin(hook, bare_project):
    r = run_hook(hook, {}, bare_project)
    assert r.returncode == 0, (hook, r.stderr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_hooks_inert.py -v`
Expected: FAIL — `bash: .../hooks/pre-bash-guard.sh: No such file or directory`

- [ ] **Step 3: Write minimal implementation**

```bash
# plugins/agentic-kit/hooks/lib/kitlock.sh
# Shared hook preamble. Sourced, not executed.
#
# Contract: every hook in this plugin is INERT outside a kit project. A missing or
# unparseable .claude/kit.lock.json is the normal case — the plugin is installed
# machine-wide and most repositories are not kit projects.
#
# Exports: KIT_LOCK (path), KIT_INPUT (raw stdin), and kit_q() to query the lock.

kit_bail_ok() { exit 0; }

kit_init() {
  command -v jq >/dev/null 2>&1 || kit_bail_ok

  KIT_INPUT=$(cat)
  [ -n "$KIT_INPUT" ] || kit_bail_ok
  printf '%s' "$KIT_INPUT" | jq -e . >/dev/null 2>&1 || kit_bail_ok

  local root="${CLAUDE_PROJECT_DIR:-}"
  if [ -z "$root" ]; then
    root=$(printf '%s' "$KIT_INPUT" | jq -r '.cwd // empty')
  fi
  [ -n "$root" ] && [ -d "$root" ] || kit_bail_ok

  KIT_LOCK="$root/.claude/kit.lock.json"
  [ -f "$KIT_LOCK" ] || kit_bail_ok
  jq -e . "$KIT_LOCK" >/dev/null 2>&1 || kit_bail_ok

  export KIT_INPUT KIT_LOCK
}

# kit_q <jq-filter> — query the lock, empty string when absent
kit_q() { jq -r "$1 // empty" "$KIT_LOCK" 2>/dev/null; }

# kit_in <jq-filter> — query the hook payload
kit_in() { printf '%s' "$KIT_INPUT" | jq -r "$1 // empty"; }

# kit_deny <reason> — block the tool call, per the Claude Code hook contract
kit_deny() {
  jq -nc --arg m "$1" \
    '{hookSpecificOutput: {permissionDecision: "deny"}, systemMessage: $m}' >&2
  exit 2
}
```

Create all four hooks as inert stubs so the parametrized test can pass now; Tasks 11–13 give each its behaviour.

```bash
# plugins/agentic-kit/hooks/pre-bash-guard.sh
#!/usr/bin/env bash
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init
exit 0
```

```bash
# plugins/agentic-kit/hooks/pre-file-guard.sh
#!/usr/bin/env bash
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init
exit 0
```

```bash
# plugins/agentic-kit/hooks/post-edit-format.sh
#!/usr/bin/env bash
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init
exit 0
```

```bash
# plugins/agentic-kit/hooks/subagent-stop-check.sh
#!/usr/bin/env bash
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init
exit 0
```

```bash
chmod +x plugins/agentic-kit/hooks/*.sh
```

The hook tests import each other with `from .hooks_conftest import ...`, which requires the test
directory to be a package. `tests/__init__.py` was already created in Task 1, so there is nothing to
do here — just confirm it exists. Note that `hooks_conftest.py` is deliberately **not** named
`conftest.py`: pytest never auto-loads it, and it is only a helper module.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_hooks_inert.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/hooks plugins/agentic-kit/kitgen/tests/test_hooks_inert.py plugins/agentic-kit/kitgen/tests/hooks_conftest.py plugins/agentic-kit/kitgen/tests/__init__.py
git commit -m "feat(hooks): shared kitlock preamble, inert outside kit projects"
```

---

## Task 11: `pre-bash-guard`

**Files:**
- Modify: `plugins/agentic-kit/hooks/pre-bash-guard.sh`
- Test: `plugins/agentic-kit/kitgen/tests/test_pre_bash_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_pre_bash_guard.py
import json

import pytest

from .hooks_conftest import bash_payload, run_hook

HOOK = "pre-bash-guard.sh"


def make_project(tmp_path, **overrides):
    lock = {
        "forge": {"kind": "gitlab", "cli": "glab", "exclusive": True,
                  "mirror": None, "remote": "git@h:o/r.git", "ci": ".gitlab-ci.yml"},
        "attribution": {"mention_assistant_in_commits": False},
        "secrets": ["./.env"],
        "toolchain": {"format": "ruff format"},
    }
    lock.update(overrides)
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps(lock))
    return tmp_path


@pytest.mark.parametrize("command", [
    "git add -A",
    "git add .",
    "git add --all",
    "git commit -a -m wip",
    "git commit -am wip",
    "git stash",
    "git stash pop",
])
def test_staging_sweeps_are_blocked(tmp_path, command):
    p = make_project(tmp_path)
    r = run_hook(HOOK, bash_payload(command, p), p)
    assert r.returncode == 2, command
    assert "--only" in r.stderr


@pytest.mark.parametrize("command", [
    "git commit --only src/a.py -m 'feat: a'",
    "git add src/a.py",
    "git status",
    "git diff --cached",
])
def test_explicit_path_operations_are_allowed(tmp_path, command):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == 0, command


@pytest.mark.parametrize("command", [
    "rm -rf build",
    "git push --force origin main",
    "git push -f",
    "git reset --hard HEAD~1",
    "docker compose down -v",
])
def test_destructive_commands_are_blocked(tmp_path, command):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == 2, command


def test_the_other_forge_cli_is_blocked_when_exclusive(tmp_path):
    p = make_project(tmp_path)
    r = run_hook(HOOK, bash_payload("gh pr create", p), p)
    assert r.returncode == 2
    assert "glab" in r.stderr


def test_the_chosen_forge_cli_is_allowed(tmp_path):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload("glab mr list", p), p).returncode == 0


def test_neither_cli_is_blocked_when_forge_is_none(tmp_path):
    p = make_project(tmp_path, forge={"kind": "none", "cli": "none",
                                      "exclusive": False, "mirror": None,
                                      "remote": None, "ci": None})
    assert run_hook(HOOK, bash_payload("gh pr list", p), p).returncode == 0
    assert run_hook(HOOK, bash_payload("glab mr list", p), p).returncode == 0


def test_assistant_attribution_in_a_commit_message_is_blocked(tmp_path):
    p = make_project(tmp_path)
    cmd = "git commit --only a.py -m 'feat: x\n\nCo-Authored-By: Claude <x@y>'"
    r = run_hook(HOOK, bash_payload(cmd, p), p)
    assert r.returncode == 2
    assert "attribution" in r.stderr.lower()


def test_attribution_is_allowed_when_the_profile_permits_it(tmp_path):
    p = make_project(tmp_path,
                     attribution={"mention_assistant_in_commits": True})
    cmd = "git commit --only a.py -m 'feat: x\n\nCo-Authored-By: Claude <x@y>'"
    assert run_hook(HOOK, bash_payload(cmd, p), p).returncode == 0


def test_a_substring_match_does_not_cause_a_false_block(tmp_path):
    p = make_project(tmp_path)
    for safe in ["echo 'git add -A is forbidden'",
                 "grep -r 'git stash' docs/",
                 "ls github-notes/"]:
        assert run_hook(HOOK, bash_payload(safe, p), p).returncode == 0, safe
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_pre_bash_guard.py -v`
Expected: FAIL — every blocking test returns 0 (the stub allows everything)

- [ ] **Step 3: Write minimal implementation**

```bash
# plugins/agentic-kit/hooks/pre-bash-guard.sh
#!/usr/bin/env bash
# PreToolUse/Bash guard. Makes the atomic-commit, destructive-command and
# forge-exclusivity rules executable instead of advisory.
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init

cmd=$(kit_in '.tool_input.command')
[ -n "$cmd" ] || exit 0

# Only inspect the git/docker/forge words that actually start a command or follow
# a shell separator, so a command merely *mentioning* a rule is not blocked.
segments=$(printf '%s' "$cmd" | tr ';|&\n' '\n')

while IFS= read -r seg; do
  seg="${seg#"${seg%%[![:space:]]*}"}"   # ltrim
  [ -n "$seg" ] || continue

  case "$seg" in
    "git add -A"*|"git add --all"*|"git add ."|"git add . "*)
      kit_deny "Blocked: staging sweeps absorb other agents' work. Commit explicit paths with 'git commit --only <path>'." ;;
    "git commit -a"*|"git commit --all"*|"git commit -am"*)
      kit_deny "Blocked: 'git commit -a' commits whatever is staged. Use 'git commit --only <path> -m ...'." ;;
    "git stash"*)
      kit_deny "Blocked: restoring a stash has itself leaked a peer agent's working tree into a commit. If foreign files appear in git status, stop and report to the Orchestrator." ;;
    "rm -rf"*|"rm -fr"*)
      kit_deny "Blocked: 'rm -rf'. Delete named paths, and ask the user for anything broader." ;;
    "git push --force"*|"git push -f"*)
      kit_deny "Blocked: force push. Ask the user; a force push can destroy a peer session's commits." ;;
    "git reset --hard"*)
      kit_deny "Blocked: 'git reset --hard' discards uncommitted work that may not be yours." ;;
    "docker compose down -v"*|"docker-compose down -v"*)
      kit_deny "Blocked: '-v' deletes named volumes, i.e. the data. Use 'docker compose down' alone." ;;
  esac
done <<< "$segments"

forge_kind=$(kit_q '.forge.kind')
forge_cli=$(kit_q '.forge.cli')
exclusive=$(kit_q '.forge.exclusive')

if [ "$exclusive" = "true" ] && [ "$forge_kind" != "none" ]; then
  case "$forge_kind" in
    gitlab) other="gh" ;;
    github) other="glab" ;;
    *)      other="" ;;
  esac
  if [ -n "$other" ]; then
    while IFS= read -r seg; do
      seg="${seg#"${seg%%[![:space:]]*}"}"
      case "$seg" in
        "$other"|"$other "*)
          kit_deny "Blocked: this project's forge is ${forge_kind}; use '${forge_cli}', not '${other}'." ;;
      esac
    done <<< "$segments"
  fi
fi

if [ "$(kit_q '.attribution.mention_assistant_in_commits')" != "true" ]; then
  case "$cmd" in
    "git commit"*|*" git commit"*)
      if printf '%s' "$cmd" | grep -qiE 'claude|anthropic|co-authored-by:[^\n]*claude'; then
        kit_deny "Blocked by attribution policy: this project does not name the assistant in commit messages."
      fi ;;
  esac
fi

exit 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_pre_bash_guard.py tests/test_hooks_inert.py -v`
Expected: PASS — 34 passed (22 guard cases plus the 12 inertness cases still green)

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/hooks/pre-bash-guard.sh plugins/agentic-kit/kitgen/tests/test_pre_bash_guard.py
git commit -m "feat(hooks): pre-bash-guard enforcing atomic commits and forge exclusivity"
```

---

## Task 12: `pre-file-guard`

**Files:**
- Modify: `plugins/agentic-kit/hooks/pre-file-guard.sh`
- Test: `plugins/agentic-kit/kitgen/tests/test_pre_file_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_pre_file_guard.py
import json

import pytest

from .hooks_conftest import file_payload, run_hook

HOOK = "pre-file-guard.sh"


def make_project(tmp_path, secrets):
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps({
        "secrets": secrets,
        "forge": {"kind": "none", "cli": "none", "exclusive": False,
                  "mirror": None, "remote": None, "ci": None},
        "attribution": {"mention_assistant_in_commits": True},
        "toolchain": {"format": "ruff format"},
    }))
    return tmp_path


@pytest.mark.parametrize("tool", ["Read", "Edit", "Write"])
def test_a_secret_file_is_blocked_for_every_tool(tmp_path, tool):
    p = make_project(tmp_path, ["./.env", "./secrets/**"])
    r = run_hook(HOOK, file_payload(tool, str(p / ".env"), p), p)
    assert r.returncode == 2
    assert ".env" in r.stderr


def test_a_glob_secret_matches_nested_paths(tmp_path):
    p = make_project(tmp_path, ["./secrets/**"])
    r = run_hook(HOOK, file_payload("Read", str(p / "secrets/db/pw.txt"), p), p)
    assert r.returncode == 2


def test_an_ordinary_file_is_allowed(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    r = run_hook(HOOK, file_payload("Edit", str(p / "src/app.py"), p), p)
    assert r.returncode == 0


def test_a_relative_path_is_matched_too(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    assert run_hook(HOOK, file_payload("Read", ".env", p), p).returncode == 2


def test_a_lookalike_name_is_not_blocked(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    for safe in [".env.example", "docs/env.md", "src/environment.py"]:
        r = run_hook(HOOK, file_payload("Read", str(p / safe), p), p)
        assert r.returncode == 0, safe


def test_no_file_path_in_the_payload_is_allowed(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    r = run_hook(HOOK, {"tool_name": "Read", "tool_input": {}, "cwd": str(p)}, p)
    assert r.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_pre_file_guard.py -v`
Expected: FAIL — blocking cases return 0

- [ ] **Step 3: Write minimal implementation**

```bash
# plugins/agentic-kit/hooks/pre-file-guard.sh
#!/usr/bin/env bash
# PreToolUse/Read,Edit,Write guard. Denies the paths named in kit.lock.json
# "secrets", matched relative to the project root.
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init

path=$(kit_in '.tool_input.file_path')
[ -n "$path" ] || exit 0

root=$(dirname "$(dirname "$KIT_LOCK")")
# Normalise to a path relative to the project root, no leading "./".
rel="$path"
case "$rel" in
  "$root"/*) rel="${rel#"$root"/}" ;;
  /*)        exit 0 ;;   # outside the project: not ours to police
esac
rel="${rel#./}"

while IFS= read -r pattern; do
  [ -n "$pattern" ] || continue
  pat="${pattern#./}"
  # shellcheck disable=SC2254  # the pattern is a glob on purpose
  case "$rel" in
    $pat) kit_deny "Blocked: ${rel} matches a secret path (${pattern}) in .claude/kit.yaml. Never read or print it; use the .example template instead." ;;
  esac
done < <(jq -r '.secrets[]? // empty' "$KIT_LOCK")

exit 0
```

Note on matching: `**` in a bash `case` glob already spans `/`, so `secrets/**` matches `secrets/db/pw.txt`, while `.env` does not match `.env.example` because `case` anchors the whole string.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_pre_file_guard.py tests/test_hooks_inert.py -v`
Expected: PASS, 20 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/hooks/pre-file-guard.sh plugins/agentic-kit/kitgen/tests/test_pre_file_guard.py
git commit -m "feat(hooks): pre-file-guard denying profile secret paths"
```

---

## Task 13: `post-edit-format` and `subagent-stop-check`

**Files:**
- Modify: `plugins/agentic-kit/hooks/post-edit-format.sh`
- Modify: `plugins/agentic-kit/hooks/subagent-stop-check.sh`
- Test: `plugins/agentic-kit/kitgen/tests/test_post_and_stop_hooks.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_post_and_stop_hooks.py
import json

from .hooks_conftest import HOOKS, file_payload, run_hook


def make_project(tmp_path, fmt="true", handoff_required=True):
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps({
        "secrets": [],
        "forge": {"kind": "none", "cli": "none", "exclusive": False,
                  "mirror": None, "remote": None, "ci": None},
        "attribution": {"mention_assistant_in_commits": True},
        "toolchain": {"format": fmt},
        "roles": [{"name": "data", "handoff_extra": ["MIGRATION:"]}],
    }))
    return tmp_path


def test_format_hook_runs_the_configured_formatter(tmp_path):
    marker = tmp_path / "ran"
    p = make_project(tmp_path, fmt=f"touch {marker} --")
    r = run_hook("post-edit-format.sh",
                 file_payload("Edit", str(p / "src/a.py"), p), p)
    assert r.returncode == 0
    assert marker.exists()


def test_format_hook_never_blocks_when_the_formatter_fails(tmp_path):
    p = make_project(tmp_path, fmt="false")
    r = run_hook("post-edit-format.sh",
                 file_payload("Edit", str(p / "src/a.py"), p), p)
    assert r.returncode == 0


def test_format_hook_skips_non_source_files(tmp_path):
    marker = tmp_path / "ran"
    p = make_project(tmp_path, fmt=f"touch {marker} --")
    run_hook("post-edit-format.sh",
             file_payload("Write", str(p / "docs/notes.md"), p), p)
    assert not marker.exists()


def test_stop_check_blocks_a_transcript_with_no_handoff(tmp_path):
    p = make_project(tmp_path)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps(
        {"role": "assistant", "content": "Done, looks good."}) + "\n")
    r = run_hook("subagent-stop-check.sh",
                 {"transcript_path": str(transcript), "cwd": str(p)}, p)
    assert r.returncode == 2
    assert "handoff" in r.stderr.lower()


def test_stop_check_accepts_a_transcript_containing_a_handoff(tmp_path):
    p = make_project(tmp_path)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({
        "role": "assistant",
        "content": "TASK M0-S1-ARCH-001 — COMPLETE\nOUTPUTS:\n  - docs/x.md\n"
                   "TESTS: red=0 green=4\n",
    }) + "\n")
    r = run_hook("subagent-stop-check.sh",
                 {"transcript_path": str(transcript), "cwd": str(p)}, p)
    assert r.returncode == 0


def test_stop_check_is_inert_without_a_transcript(tmp_path):
    p = make_project(tmp_path)
    r = run_hook("subagent-stop-check.sh", {"cwd": str(p)}, p)
    assert r.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_post_and_stop_hooks.py -v`
Expected: FAIL — the formatter never runs and the stop check never blocks

- [ ] **Step 3: Write minimal implementation**

```bash
# plugins/agentic-kit/hooks/post-edit-format.sh
#!/usr/bin/env bash
# PostToolUse/Edit,Write. Runs the project formatter on the edited file.
# Never blocks: a formatter failure is a formatting problem, not a policy breach.
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init

path=$(kit_in '.tool_input.file_path')
[ -n "$path" ] || exit 0

case "$path" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs|*.rb|*.java|*.kt|*.css|*.scss) ;;
  *) exit 0 ;;
esac

fmt=$(kit_q '.toolchain.format')
[ -n "$fmt" ] || exit 0

# shellcheck disable=SC2086  # the command is a configured string, split on purpose
timeout 30 $fmt "$path" >/dev/null 2>&1 || true
exit 0
```

```bash
# plugins/agentic-kit/hooks/subagent-stop-check.sh
#!/usr/bin/env bash
# SubagentStop. A task is not finished until it has emitted a handoff note.
set -uo pipefail
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/kitlock.sh"
kit_init

transcript=$(kit_in '.transcript_path')
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

if grep -qE '(^|\\n|")TASK [A-Za-z0-9._-]+ — (COMPLETE|PARTIAL|BLOCKED)' "$transcript"; then
  exit 0
fi

kit_deny "No handoff note in this subagent's output. End every task by running /handoff: TASK <ID> — COMPLETE|PARTIAL|BLOCKED, OUTPUTS, TESTS with the command and its last line, FLOORS, DOWNSTREAM, NOTES."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/ -v`
Expected: PASS — the whole suite green, including the inertness tests for both modified hooks

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/hooks/post-edit-format.sh plugins/agentic-kit/hooks/subagent-stop-check.sh plugins/agentic-kit/kitgen/tests/test_post_and_stop_hooks.py
git commit -m "feat(hooks): post-edit formatter and handoff-note stop check"
```

---

## Task 14: `hooks.json` wiring

**Files:**
- Create: `plugins/agentic-kit/hooks/hooks.json`
- Test: `plugins/agentic-kit/kitgen/tests/test_hooks_json.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_hooks_json.py
import json
import os
import stat
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "hooks"


def load():
    return json.loads((HOOKS / "hooks.json").read_text())["hooks"]


def test_every_declared_event_is_one_we_implement():
    assert set(load()) == {"PreToolUse", "PostToolUse", "SubagentStop"}


def test_every_referenced_script_exists_and_is_executable():
    for entries in load().values():
        for entry in entries:
            for hook in entry["hooks"]:
                cmd = hook["command"]
                assert "${CLAUDE_PLUGIN_ROOT}" in cmd, cmd
                name = cmd.split("/hooks/")[1].strip('"')
                script = HOOKS / name
                assert script.exists(), script
                assert os.stat(script).st_mode & stat.S_IXUSR, script


def test_matchers_cover_bash_and_the_file_tools():
    pre = load()["PreToolUse"]
    matchers = [e["matcher"] for e in pre]
    assert any(m == "Bash" for m in matchers)
    assert any("Edit" in m and "Read" in m and "Write" in m for m in matchers)


def test_every_hook_script_sources_the_inertness_preamble():
    for script in HOOKS.glob("*.sh"):
        body = script.read_text()
        assert "lib/kitlock.sh" in body, script
        assert "kit_init" in body, script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_hooks_json.py -v`
Expected: FAIL — `FileNotFoundError: .../hooks/hooks.json`

- [ ] **Step 3: Write minimal implementation**

```json
{
  "description": "agentic-kit guards. Every hook is inert in a repository without .claude/kit.lock.json.",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/pre-bash-guard.sh\"",
            "timeout": 10
          }
        ]
      },
      {
        "matcher": "Read|Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/pre-file-guard.sh\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/post-edit-format.sh\"",
            "timeout": 40
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/subagent-stop-check.sh\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_hooks_json.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/hooks/hooks.json plugins/agentic-kit/kitgen/tests/test_hooks_json.py
git commit -m "feat(hooks): hooks.json wiring with plugin-root script paths"
```

---

## Task 15: The eight universal process skills

Each reads `.claude/kit.lock.json` and declines when it is absent.

**Files:**
- Create: `plugins/agentic-kit/skills/next-task/SKILL.md`
- Create: `plugins/agentic-kit/skills/gate-check/SKILL.md`
- Create: `plugins/agentic-kit/skills/handoff/SKILL.md`
- Create: `plugins/agentic-kit/skills/new-adr/SKILL.md`
- Create: `plugins/agentic-kit/skills/risk/SKILL.md`
- Create: `plugins/agentic-kit/skills/plan-status/SKILL.md`
- Create: `plugins/agentic-kit/skills/agent-memory/SKILL.md`
- Create: `plugins/agentic-kit/skills/orchestrating/SKILL.md`
- Test: `plugins/agentic-kit/kitgen/tests/test_skills.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_skills.py
import re
from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[2] / "skills"

EXPECTED = {"next-task", "gate-check", "handoff", "new-adr", "risk",
            "plan-status", "agent-memory", "orchestrating"}
# Skills the user invokes deliberately; the model must not fire them on its own.
EXPLICIT_ONLY = {"next-task", "gate-check"}


def frontmatter(path: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.S)
    assert m, f"{path} must open with YAML frontmatter"
    return yaml.safe_load(m.group(1))


def test_exactly_the_expected_skills_are_shipped():
    assert {p.name for p in SKILLS.iterdir() if p.is_dir()} == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_frontmatter_declares_name_and_description(name):
    fm = frontmatter(SKILLS / name / "SKILL.md")
    assert fm["name"] == name
    assert 20 < len(fm["description"]) < 400


@pytest.mark.parametrize("name", sorted(EXPLICIT_ONLY))
def test_dispatch_skills_are_user_invoked_only(name):
    assert frontmatter(SKILLS / name / "SKILL.md")["disable-model-invocation"] is True


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_skill_reads_the_lock_and_declines_without_it(name):
    body = (SKILLS / name / "SKILL.md").read_text()
    assert ".claude/kit.lock.json" in body, name
    assert "decline" in body.lower() or "not a kit project" in body.lower(), name


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_no_skill_hardcodes_a_spine_path_or_a_forge(name):
    body = (SKILLS / name / "SKILL.md").read_text()
    assert "docs/strategy.md" not in body, f"{name}: read spine.strategy from the lock"
    assert "docs/plan/README.md" not in body, f"{name}: read spine.plan from the lock"
    for forge in ("gitlab", "github", "glab", " gh "):
        assert forge not in body.lower(), f"{name}: mentions {forge!r}; stay forge-neutral"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_skills.py -v`
Expected: FAIL — `FileNotFoundError: .../skills`

- [ ] **Step 3: Write minimal implementation**

`skills/next-task/SKILL.md`:

```markdown
---
name: next-task
description: Advance the dispatch loop one step — take the next unblocked task from the plan, dispatch its owning role, validate the handoff, update the plan.
disable-model-invocation: true
---

Read `.claude/kit.lock.json` first. If it is absent, decline: this is not a kit project, and say so
in one line. Take every path below from the lock rather than assuming one.

1. Read `spine.plan`. Confirm the Next task is unblocked — every task it depends on is in Completed.
2. Read its block in `spine.strategy` §11 and the owner's card in `.claude/agents/<owner>.md`.
3. Spawn the owner with the Agent tool. Pass the task block verbatim, the design section references,
   and the instruction to end with `/handoff`. **Pass paths, not pasted documents.** Include the
   atomic-commit rule. If you are dispatching more than one agent in this message, or this agent's
   scope overlaps an in-flight peer, set `isolation: "worktree"`.
4. On return, check the handoff against the task's Acceptance. If the note claims tests without
   pasting the command and its result, run `toolchain.test` yourself and cite your own output.
5. If accepted, edit `spine.plan`: move the task to Completed, advance Next task, unblock downstream.
   If not, record the gap under Active and re-dispatch **once** with the gap named. After a second
   failure, stop and report to the user.
6. If every task feeding a gate is complete, tell the user the gate is ready and **stop**. Do not
   start `/gate-check` without confirmation.
7. Add a row to `spine.risks` if anything surfaced that outlives this task.
```

`skills/gate-check/SKILL.md`:

```markdown
---
name: gate-check
description: Run a formal gate check for a milestone and write the evidence bundle under docs/gates/<id>/.
disable-model-invocation: true
argument-hint: <milestone id, e.g. M1>
---

Read `.claude/kit.lock.json` first; decline in one line if absent — not a kit project. Take the
spine paths, the floors, the test tiers and the veto role's name from the lock.

Gate: $ARGUMENTS

1. Create `docs/gates/$ARGUMENTS/` with `functional.md`, `tests.md`, `floors.md`, `operational.md`
   and `summary.md`.
2. **Functional** — for every task of this milestone in `spine.strategy` §11, cite the handoff note
   and its acceptance evidence. Any miss is a BLOCK, not a note.
3. **Tests** — dispatch the `qa` role: coverage per tier against `test_tiers`, the pipeline result
   read **by job name**, snapshot diffs. A `skipped` job behind a failed one is not a pass; it is a
   claim going stale, and it must be reported as such.
4. **Floors** — dispatch the veto role in review mode for `floors.md` and a verdict, APPROVE or
   VETO. Include the threat-model delta. A VETO is not overridable here.
5. **Operational** — metrics and logs for anything new, runbook entries, rollback path, and backup
   coverage if the data model changed.
6. Apply the milestone's own gate additions from `spine.strategy` §11.
7. `summary.md`: PASS, CONDITIONAL, or BLOCK. Every condition carries an owner and a deadline task
   ID. Signers: Orchestrator, the veto role, and `architect` if a contract changed.
8. **Count the carried conditions.** If a condition has now survived two milestones, say so to the
   user in the summary and in your reply. A condition nobody tallies stops being one.
9. On PASS, advance `spine.plan` and expand the next milestone's tasks in §11.

The bundle is an artefact: counts, codes, dates and hashes. No credential, host, token or personal
string reaches it.
```

`skills/handoff/SKILL.md`:

```markdown
---
name: handoff
description: Emit the structured handoff note that ends every task. Subagents run this last; the Orchestrator validates it.
---

Read `.claude/kit.lock.json`; decline in one line if absent — not a kit project. Find your own role
in `roles[]` and append its `handoff_extra` lines.

Produce exactly:

```
TASK {ID} — COMPLETE | PARTIAL | BLOCKED
OUTPUTS:
  - <path>
CONTRACTS CHANGED: yes (<contracts path> entry) | no
TESTS: red={n} green={n} coverage={tier: %}
FLOORS: unaffected | touched (<which>) — result: <pass|fail>
OBSERVABILITY: <metrics and log fields added> | n/a
DOWNSTREAM: <unblocked task IDs>
NOTES: <deviations, follow-ups, requests to other owners>
```

Then your role's extra lines from `handoff_extra`.

**Evidence over prose.** Paste the test command and its last line. Never write a green you did not
run. If you could not run it, say `TESTS: not run — <why>` and mark the task PARTIAL: an unverified
claim costs more than an honest gap.
```

`skills/new-adr/SKILL.md`:

```markdown
---
name: new-adr
description: Scaffold a numbered ADR and add it to the decisions index.
argument-hint: <kebab-case title>
---

Read `.claude/kit.lock.json`; decline in one line if absent — not a kit project.

1. Find the highest `docs/adr/NNNN-*.md` and take the next number, zero-padded to four.
2. Write `docs/adr/<NNNN>-$ARGUMENTS.md`:

```markdown
# ADR <NNNN> — <Title>

**Status** Proposed · **Date** <today>

## Context
What forces this decision. Include the constraint that makes the obvious answer wrong.

## Decision
What we are doing, in the active voice.

## Consequences
What this costs, what it forecloses, and what has to change if we reverse it.

## Alternatives considered
Each with the reason it lost. An alternative with no stated reason was not considered.
```

3. Append a row to the ADR index in `spine.decisions`.
4. Status stays **Proposed** until the user accepts it. Do not write Accepted on your own.
```

`skills/risk/SKILL.md`:

```markdown
---
name: risk
description: Add or update a row in the project risk register.
argument-hint: <one-line risk statement>
---

Read `.claude/kit.lock.json`; decline in one line if absent — not a kit project.

Open `spine.risks`. Take the next unused `R-NNN` — **never reuse a number**, including for a closed
risk, because task notes and gate bundles cite them.

Add: ID, the risk as a falsifiable statement, likelihood, impact, mitigation, owner, status.

Rules:
- A risk closes on **evidence**, not on time passing. Cite what closed it.
- If the risk has already fired, say how many times and when. A recurrence count is the finding.
- If an existing row covers it, update that row instead of adding a near-duplicate.
```

`skills/plan-status/SKILL.md`:

```markdown
---
name: plan-status
description: Read-only grounding — current milestone, next task, open gates, open risks, and any kit drift.
---

Read `.claude/kit.lock.json`; decline in one line if absent — not a kit project.

Read `spine.plan` and `spine.risks`. Report in at most six lines: current milestone, next task ID
and owner, anything Active or Blocked, open gates, and the count of open risks plus any that have
fired more than once.

If `.claude/kit.yaml` is newer than `.claude/kit.lock.json`, add one line: the profile was
hand-edited and the lock is stale — run `/kit-upgrade`.

Change nothing. This skill only reads.
```

`skills/agent-memory/SKILL.md`:

```markdown
---
name: agent-memory
description: How to keep a role's durable memory — one fact per file with a linked index, so the next session does not rediscover it.
---

Read `.claude/kit.lock.json`; decline in one line if absent — not a kit project.

Your memory is `.claude/agent-memory/<your role>/`. `MEMORY.md` is the index; each fact is its own
file beside it.

**Write a fact when** something cost you real time to discover and would cost the next session the
same: a tool that reported success while doing nothing, an endpoint quirk, a constraint the code
does not state, a test that passes for the wrong reason.

**Do not write** what the repository already records — structure, git history, or anything in
`CLAUDE.md`. A fact that duplicates the tree is noise that dilutes the index.

Format, one file per fact:

```markdown
# <Title — the finding, not the topic>

<The fact, stated so it can be checked. What was observed, what was expected, what the tell is.>

Related: [[other-fact-slug]]
```

Then one line in `MEMORY.md`:

```markdown
- [Title](slug.md) — the hook: what is surprising, in a clause.
```

Titles carry the finding: "a guessed URL is not a measurement" beats "URL notes". Before adding,
scan the index for a fact that already covers it and extend that one instead.
```

`skills/orchestrating/SKILL.md`:

```markdown
---
name: orchestrating
description: Dispatch doctrine for the Orchestrator role — how to brief a subagent, when worktree isolation is mandatory, and how to validate what comes back.
---

Read `.claude/kit.lock.json`; decline in one line if absent — not a kit project.

## Briefing

Pass the task block verbatim, the role card path, and **file paths, never pasted documents** — a
pasted document is a copy that goes stale and costs context twice.

Every brief repeats the atomic-commit rule: commit with `git commit --only <path>`, explicit paths.
Never `git add -A`, `git add .`, or `git commit -a`.

## Worktree isolation is mandatory when

- Two or more agents are dispatched in the same message.
- A dispatched agent's scope overlaps an in-flight peer's tree.
- An agent will edit files a peer may stage.

Set `isolation: "worktree"` on the Agent call. Agents sharing one working tree share one index, and
a shared index is the whole cause of cross-agent staging leaks. Disjoint file lists do **not** make
a shared tree safe.

On return from a worktree agent: verify the handoff and the commit SHA against acceptance,
cherry-pick onto the trunk, remove the worktree, and record both SHAs in the handoff note.

**Never** recover with `git stash`. Restoring a stash has itself moved a peer's working tree into the
wrong commit. If foreign files appear in `git status`, stop and report.

## Validation

A handoff without a pasted command and its last line is not evidence — run `toolchain.test`
yourself. Accept, or record the gap and re-dispatch once with the gap named; after a second failure,
stop and report to the user rather than trying a third time.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_skills.py -v`
Expected: PASS, 27 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/agentic-kit/skills plugins/agentic-kit/kitgen/tests/test_skills.py
git commit -m "feat(skills): eight forge-neutral process skills reading the lock"
```

---

## Task 16: M1 acceptance — end-to-end render, verify, install

**Files:**
- Create: `plugins/agentic-kit/kitgen/tests/test_acceptance_m1.py`
- Create: `README.md`

- [ ] **Step 1: Write the failing test**

```python
# plugins/agentic-kit/kitgen/tests/test_acceptance_m1.py
"""M1 acceptance: every fixture renders, verifies and writes a coherent kit."""
import json
from pathlib import Path

import pytest
import yaml

from kitgen.cli import main
from kitgen.model import KitConfig
from kitgen.render import render
from kitgen.verify import verify

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_renders_verifies_and_writes(name, tmp_path):
    profile = FIXTURE_DIR / name / "profile.yaml"
    cfg = KitConfig.from_dict(yaml.safe_load(profile.read_text()))

    for p in cfg.spine["inherited"]:
        target = tmp_path / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("inherited placeholder")

    assert main(["render", "--profile", str(profile), "--out", str(tmp_path)]) == 0
    assert verify(render(cfg), cfg, project_root=tmp_path) == []

    lock = json.loads((tmp_path / ".claude/kit.lock.json").read_text())
    assert lock["project"]["slug"] == cfg.project.slug

    for r in cfg.roles:
        assert (tmp_path / f".claude/agents/{r.name}.md").exists()
        assert (tmp_path / f".claude/agent-memory/{r.name}/MEMORY.md").exists()

    claude_md = (tmp_path / "CLAUDE.md").read_text()
    for r in cfg.roles:
        assert f"`{r.name}`" in claude_md


@pytest.mark.parametrize("name", FIXTURES)
def test_rendered_kit_is_idempotent(name, tmp_path):
    profile = FIXTURE_DIR / name / "profile.yaml"
    cfg = KitConfig.from_dict(yaml.safe_load(profile.read_text()))
    for p in cfg.spine["inherited"]:
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("inherited placeholder")

    assert main(["render", "--profile", str(profile), "--out", str(tmp_path)]) == 0
    first = {p: (tmp_path / p).read_text() for p in render(cfg)}
    assert main(["render", "--profile", str(profile), "--out", str(tmp_path),
                 "--force"]) == 0
    assert {p: (tmp_path / p).read_text() for p in render(cfg)} == first


def test_marketplace_source_resolves_to_the_plugin_manifest():
    """Task 1 asserted the source string; assert the path it names actually exists,
    and that the two manifests agree on the plugin name."""
    repo = Path(__file__).resolve().parents[4]
    mp = json.loads((repo / ".claude-plugin/marketplace.json").read_text())
    entry = mp["plugins"][0]
    manifest = repo / entry["source"] / ".claude-plugin/plugin.json"
    assert manifest.exists(), manifest
    assert json.loads(manifest.read_text())["name"] == entry["name"]


def test_hooks_are_inert_in_a_rendered_tree_before_the_lock_lands(tmp_path):
    """A half-written install must not start blocking commands."""
    from .hooks_conftest import bash_payload, run_hook
    (tmp_path / "CLAUDE.md").write_text("# partial install")
    r = run_hook("pre-bash-guard.sh", bash_payload("git add -A", tmp_path), tmp_path)
    assert r.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest tests/test_acceptance_m1.py -v`
Expected: FAIL on `test_fixture_renders_verifies_and_writes[greenfield_prd]` if any template still
carries an unrendered reference; otherwise this is the first run that exercises all three fixtures
through the CLI end to end. Fix whatever it surfaces before proceeding.

- [ ] **Step 3: Write the README**

```markdown
# agentic-kit

A drop-in Claude Code kit for the orchestrator development model: role agents with exclusive
file-path ownership, milestone gates, a risk register, handoff notes carrying test evidence, agent
memory, and guard hooks that make the rules executable rather than advisory.

## Install

```bash
claude plugin marketplace add git@<your-forge-host>:<owner>/agentic-kit.git
claude plugin install agentic-kit@agentic-kit
```

Once per machine. The plugin is **inert in any repository without `.claude/kit.lock.json`**, so
installing it machine-wide does not change how you work in projects that do not use it.

## Use

In a project without the kit, run `/kit-install` (no code yet) or `/kit-retrofit` (code exists).
Both interview you, then render the project's kit. See `docs/` for the design.

Day to day: `/next-task`, `/plan-status`, `/handoff`, `/gate-check <milestone>`, `/new-adr <title>`,
`/risk <statement>`. After updating the plugin, `/kit-upgrade`.

## Forge neutrality

Nothing here assumes GitLab or GitHub. `forge.kind` is an interview answer — `gitlab`, `github` or
`none` — and the guard enforces whichever you chose, blocking the other's CLI when
`forge.exclusive` is set.

## Development

```bash
cd plugins/agentic-kit/kitgen
uv run pytest
```

`kitgen.render` is a pure function from a profile to `{path: content}`. It reads nothing from the
project tree and writes nothing, which is what makes the output testable and what would keep a
future MCP wrapper small.
```

- [ ] **Step 4: Run the whole suite**

Run: `cd plugins/agentic-kit/kitgen && uv run pytest -v`
Expected: PASS — every test file green. Record the final count; this is the M1 acceptance evidence.

- [ ] **Step 5: Commit and tag**

```bash
git add plugins/agentic-kit/kitgen/tests/test_acceptance_m1.py README.md
git commit -m "test: M1 acceptance across all three fixtures"
git tag -a m1-kit -m "M1: kit, renderer and guards complete"
```

---

## Task 17: Install the plugin and confirm inertness on a real repository

The one thing no unit test can prove: that a globally installed plugin leaves your other repositories alone.

**Files:** none — this is a verification task.

- [ ] **Step 1: Add the marketplace from the local directory**

```bash
claude plugin marketplace add /home/alex/Documents/coding/agentic-kit
claude plugin install agentic-kit@agentic-kit
```

Expected: both succeed; `claude plugin list` shows `agentic-kit`.

- [ ] **Step 2: Confirm the skills are visible**

Start a session in any directory and check that `/plan-status` is offered.
Expected: the skill is listed.

- [ ] **Step 3: Confirm inertness in a non-kit repository**

In `/home/alex/homelab-runbook` (which has no `.claude/kit.lock.json`), run `/plan-status`.
Expected: it declines in one line — "not a kit project" — and changes nothing.

Then confirm the guard does not fire there:

```bash
git status --short
```

Expected: normal output, no hook denial.

- [ ] **Step 4: Confirm the guard does fire in a kit project**

```bash
cd $(mktemp -d) && git init -q && mkdir -p docs
uv run --project /home/alex/Documents/coding/agentic-kit/plugins/agentic-kit/kitgen \
  kitgen render \
  --profile /home/alex/Documents/coding/agentic-kit/plugins/agentic-kit/kitgen/tests/fixtures/python_monolith/profile.yaml \
  --out .
```

Then in a Claude Code session in that directory, ask it to run `git add -A`.
Expected: the call is blocked with the message naming `git commit --only`.

- [ ] **Step 5: Record the result**

Append the four outcomes to `docs/m1-acceptance.md` and commit.

```bash
git add docs/m1-acceptance.md
git commit -m "docs: M1 acceptance evidence from a real plugin install"
```

---

## M2 — the installers (separate plan)

M2's tasks call `kitgen`'s API, so its steps are written once M1 has produced the real signatures —
writing them now would mean inventing them twice, and the plan's no-placeholder rule would be met
with fiction. Its shape is fixed by the spec:

| Task | Deliverable | Acceptance |
|---|---|---|
| 1 | `kitgen.detect` — languages, package manager, test/format/lint/types, source directories, forge from remotes, CI files, existing docs and `.claude/`, candidate secret paths | golden facts for three real trees: `321_project`, `study-helper-project`, an empty dir with only a PRD |
| 2 | Role-roster proposal from facts — always-on four, conditional `data`/`frontend`, domain roles from source directories, ownership globs that partition | proposes JobOps-like rosters for the real trees; partition check green |
| 3 | `skills/kit-install/SKILL.md` — greenfield: derive the roster from documentation, five-turn interview, floors blocking, render, verify, write, commit | installs into an empty dir holding only a PRD; `/plan-status` and `/next-task` then run |
| 4 | `skills/kit-retrofit/SKILL.md` — brownfield: preservation rule (existing CLAUDE.md verbatim into `## Project-specific notes`), back-fill Completed from progress docs and git history, `spine.inherited` | retrofits `321_project` in a worktree with its GitLab gotchas present verbatim |
| 4b | Widen `test_exactly_the_expected_skills_are_shipped` to eleven skills. Until then a rendered `CLAUDE.md` and the README reference `/kit-upgrade`, which does not exist yet — harmless, because no real project is installed before M2 | the skills test passes with the three installers present |
| 5 | `skills/kit-upgrade/SKILL.md` — re-render against the stored profile, diff, present patches, refuse to touch `## Project-specific notes` | a deliberate template change surfaces as a patch; hand-edits survive |
| 6 | M2 acceptance | `321_project` and `study-helper-project` retrofitted in worktrees; in each, `/plan-status`, `/next-task` and `/gate-check` run against the generated spine; pre-existing CLAUDE.md content verbatim |

**Before M2:** confirm `uv` and `jq` on the laptop (spec R-06). `uv` 0.12.7 and `jq` 1.6 are
confirmed on devbox.
