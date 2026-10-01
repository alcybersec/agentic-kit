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


def test_mirror_equal_to_kind_is_rejected():
    bad = {**MINIMAL, "forge": {**MINIMAL["forge"], "mirror": "gitlab"}}
    with pytest.raises(ConfigError, match="mirror"):
        KitConfig.from_dict(bad)


def test_unknown_forge_kind_is_rejected():
    bad = {**MINIMAL, "forge": {**MINIMAL["forge"], "kind": "bitbucket"}}
    with pytest.raises(ConfigError, match="unknown forge kind"):
        KitConfig.from_dict(bad)


def test_missing_spine_key_is_rejected():
    bad = {**MINIMAL, "spine": {k: v for k, v in MINIMAL["spine"].items()
                                if k != "strategy"}}
    with pytest.raises(ConfigError, match="strategy"):
        KitConfig.from_dict(bad)


def test_non_boolean_observability_is_rejected():
    with pytest.raises(ConfigError, match="observability"):
        KitConfig.from_dict({**MINIMAL, "observability": "false"})


def test_glob_prefix_truncates_to_a_whole_segment():
    from kitgen.model import _overlaps
    assert _overlaps("src/a*/x/**", "src/ab/**")
    assert _overlaps("src/[ab]/**", "src/a/**")
    assert _overlaps("services/{api,worker}/**", "services/api/**")
    assert not _overlaps("src/foo/**", "src/foobar/**")
    assert not _overlaps("services/api/**", "services/ui/**")
    assert _overlaps("**/*.py", "totally/unrelated/**")


def test_unknown_role_key_is_rejected():
    bad = {**MINIMAL, "roles": [
        {**MINIMAL["roles"][0], "handoff_extras": ["MIGRATION:"]},
        MINIMAL["roles"][1],
    ]}
    with pytest.raises(ConfigError, match="unknown keys"):
        KitConfig.from_dict(bad)


def test_scalar_where_a_mapping_belongs_is_a_config_error():
    with pytest.raises(ConfigError, match="spine must be a mapping"):
        KitConfig.from_dict({**MINIMAL, "spine": "docs/strategy.md"})


def test_scalar_where_a_list_belongs_is_a_config_error():
    with pytest.raises(ConfigError, match="floors must be a list"):
        KitConfig.from_dict({**MINIMAL, "floors": "one floor"})


@pytest.mark.parametrize("glob", [
    "./src/**", "src//core/**", "src/../lib/**",
    "/src/**", ".", "..", "src/./core/**", "src\\core/**",
])
def test_non_normalised_owns_glob_is_rejected(glob):
    bad = {**MINIMAL, "roles": [
        {**MINIMAL["roles"][0], "owns": [glob]},
        MINIMAL["roles"][1],
    ]}
    with pytest.raises(ConfigError, match="not normalised"):
        KitConfig.from_dict(bad)


@pytest.mark.parametrize("glob", [
    "src/**", "docs/adr/**", "compose.yaml", ".gitlab-ci.yml",
    ".github/workflows/**", "src/ledger/api/**", "packages/protocol/**",
    "tests/**", "migrations/**",
])
def test_normalised_owns_globs_are_accepted(glob):
    """Every glob form the three Task 3 fixtures use must survive the check.
    A leading dot in a segment name is not a '.' segment."""
    ok = {**MINIMAL, "roles": [
        {**MINIMAL["roles"][0], "owns": [glob]},
        {**MINIMAL["roles"][1], "owns": ["zzz_unrelated/**"]},
    ]}
    assert KitConfig.from_dict(ok).roles[0].owns == [glob]


def test_nested_profile_structures_are_not_aliased():
    profile = {**MINIMAL, "spine": {**MINIMAL["spine"], "inherited": ["docs/PRD.md"]}}
    cfg = KitConfig.from_dict(profile)
    assert cfg.spine["inherited"] is not profile["spine"]["inherited"]
    assert cfg.milestones["outline"] is not profile["milestones"]["outline"]
