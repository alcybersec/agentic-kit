import pytest
from kitgen.model import DEFAULT_TOOLS, KitConfig, ConfigError

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


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_toolchain_value_is_rejected(value):
    bad = {**MINIMAL, "toolchain": {**MINIMAL["toolchain"], "format": value}}
    with pytest.raises(ConfigError, match="toolchain.format"):
        KitConfig.from_dict(bad)


@pytest.mark.parametrize("fmt", [
    "black .",            # the shipped python_monolith fixture, until 2026-10-01
    "black ./",
    "ruff format .",
    "prettier --write .",
    "cargo fmt --all",
    "prettier --write src/",
    "black src/*.py",
    "ruff format app/main.py",
])
def test_format_command_carrying_its_own_target_is_rejected(fmt):
    """`post-edit-format.sh` appends the edited file, so a command that already
    names a target reformats that target too -- on every single edit, from a
    PostToolUse hook that no ownership matcher covers."""
    bad = {**MINIMAL, "toolchain": {**MINIMAL["toolchain"], "format": fmt}}
    with pytest.raises(ConfigError, match="toolchain.format must name no target"):
        KitConfig.from_dict(bad)


@pytest.mark.parametrize("fmt", [
    "ruff format",
    "black",
    "prettier --write",
    "gofmt -w",
    "gofmt -w -r",                            # -r takes a rewrite rule, not a target
    "npx prettier --write",
    "./scripts/fmt.sh",                       # one token: the executable itself
    "prettier --config ./p.json --write",     # a path, but a flag's value
    "poetry run black",
])
def test_format_command_without_a_target_is_accepted(fmt):
    """The check is lexical and must not reject a legitimate prefix: a
    single-token command is the executable, and a mid-command path is usually a
    flag's value rather than a target."""
    good = {**MINIMAL, "toolchain": {**MINIMAL["toolchain"], "format": fmt}}
    assert KitConfig.from_dict(good).toolchain["format"] == fmt


def test_default_tools_include_skill():
    """The handoff protocol depends on it: every role card ends with 'run /handoff',
    and a subagent without the Skill tool cannot invoke a slash skill at all."""
    from kitgen.model import DEFAULT_TOOLS
    assert "Skill" in DEFAULT_TOOLS


@pytest.mark.parametrize("outline", [[], None, "M0"])
def test_empty_or_malformed_milestone_outline_is_rejected(outline):
    import copy
    d = copy.deepcopy(MINIMAL)
    d["milestones"]["outline"] = outline
    with pytest.raises(ConfigError, match="outline"):
        KitConfig.from_dict(d)


@pytest.mark.parametrize("field,value", [("remote", "git@h:o/r.git"),
                                         ("ci", ".github/workflows"),
                                         ("mirror", "github")])
def test_forge_none_with_a_remote_ci_or_mirror_is_rejected(field, value):
    import copy
    d = copy.deepcopy(MINIMAL)
    d["forge"] = {"kind": "none", "remote": None, "cli": "none", "ci": None,
                  "exclusive": False}
    d["forge"][field] = value
    with pytest.raises(ConfigError, match=f"forge.{field}"):
        KitConfig.from_dict(d)


# --- fix 2.2: the overlap truth table ----------------------------------------
#
# Exclusive path ownership is the kit's central invariant and `_overlaps` is the
# only thing enforcing it, yet eight mutants of it survived the audit: the
# function was exercised only through profiles that happened to be valid, so most
# of its logic was never pinned.
#
# The audit also reported that "two roles can currently declare the identical glob
# and validate". That is NOT true — `src/a/**` twice yields equal prefixes and is
# rejected — and the first row below is here to keep it false.

OVERLAP = [
    # (a, b, overlaps, why)
    ("src/a/**", "src/a/**", True, "identical globs"),
    ("docs/x.md", "docs/x.md", True, "identical literals, no wildcard at all"),
    ("src/a/**", "src/a/b/**", True, "b is inside a"),
    ("src/a/b/**", "src/a/**", True, "a is inside b — the check is symmetric"),
    ("src/a/**", "src/a", True, "a directory and its own tree"),
    ("src/a/", "src/a/**", True, "a trailing slash is not a different directory"),
    ("docs/x.md", "docs/**", True, "a file inside a claimed tree"),
    ("src/a/**", "src/b/**", False, "disjoint siblings"),
    ("src/a/**", "src/ab/**", False,
     "a prefix that is a string prefix but not a PATH prefix"),
    ("src/a*/x/**", "src/ab/x/**", True,
     "a mid-segment wildcard truncates to `src`, so this is conservative on purpose"),
    ("**/*.py", "app/**", True, "a wild first segment has no prefix: overlaps all"),
    ("*.py", "*.ts", True,
     "extension-partitioned ownership of one tree is rejected by design (§5.2)"),
]


@pytest.mark.parametrize("a,b,expected,why", OVERLAP,
                         ids=[f"{c[0]}|{c[1]}" for c in OVERLAP])
def test_overlap_truth_table(a, b, expected, why):
    from kitgen.model import _overlaps
    assert _overlaps(a, b) is expected, why
    # Symmetry is load-bearing: validate() compares each pair once, in roster
    # order, so an asymmetric answer would make the verdict depend on which role
    # happens to be listed first.
    assert _overlaps(b, a) is expected, f"not symmetric: {why}"


PREFIX = [
    ("src/a/**", "src/a"),
    ("src/a/", "src/a"),
    ("src/a", "src/a"),
    ("docs/x.md", "docs/x.md"),
    ("src/a*/x/**", "src"),      # back to the last separator, never a part-segment
    ("src/*/x", "src"),
    ("**/*.py", ""),
    ("*.py", ""),
    ("src/a[0-9]/**", "src"),    # [ is a metacharacter
    ("src/a{b,c}/**", "src"),    # so is {
    ("src/a?/**", "src"),        # and ?
]


@pytest.mark.parametrize("pattern,prefix", PREFIX)
def test_glob_prefix_truth_table(pattern, prefix):
    from kitgen.model import _glob_prefix
    assert _glob_prefix(pattern) == prefix


@pytest.mark.parametrize("a,b,expected,why", OVERLAP,
                         ids=[f"{c[0]}|{c[1]}" for c in OVERLAP])
def test_a_profile_follows_the_overlap_table(a, b, expected, why):
    """The table drives validate() as well, so the two cannot drift apart."""
    if a.endswith("/") or b.endswith("/"):
        pytest.skip("a trailing slash is rejected by the normalisation check first, "
                    "which runs before overlap — the unit test above still pins "
                    "that _overlaps itself handles it")
    bad = {**MINIMAL, "roles": [
        {**MINIMAL["roles"][0], "owns": [a]},
        {**MINIMAL["roles"][1], "owns": [b]},
    ]}
    if expected:
        with pytest.raises(ConfigError, match="ownership overlap"):
            KitConfig.from_dict(bad)
    else:
        assert [r.owns for r in KitConfig.from_dict(bad).roles] == [[a], [b]]


# --- fix 2.3: the profile-key matrix -----------------------------------------
#
# Twenty-two mutants survived in from_dict / _check_shapes, because every test
# fed it a profile that was either valid or broken in one hand-picked way. The
# CLI maps any failure here to exit 2 ("bad profile"), so what matters is that
# NOTHING gets through, and that the message names the key — a profile is edited
# by a human and "KeyError" is not a diagnosis.

REQUIRED_TOP = ["kit_version", "rendered_on", "project", "forge", "attribution",
                "spine", "load_order", "milestones", "roles", "floors",
                "test_tiers", "toolchain", "secrets", "observability"]


@pytest.mark.parametrize("key", REQUIRED_TOP)
def test_every_top_level_key_is_required(key):
    bad = {k: v for k, v in MINIMAL.items() if k != key}
    with pytest.raises((ConfigError, KeyError, TypeError)) as e:
        KitConfig.from_dict(bad)
    assert key in str(e.value), (key, str(e.value))


MAPPING_SECTIONS = ["attribution", "spine", "milestones", "test_tiers", "toolchain"]
LIST_SECTIONS = ["load_order", "roles", "floors", "secrets"]


@pytest.mark.parametrize("section", MAPPING_SECTIONS)
@pytest.mark.parametrize("wrong", ["a string", 3, ["a", "list"], None])
def test_a_mapping_section_given_a_non_mapping_is_rejected(section, wrong):
    bad = {**MINIMAL, section: wrong}
    with pytest.raises(ConfigError, match=f"{section} must be a mapping"):
        KitConfig.from_dict(bad)


@pytest.mark.parametrize("section", LIST_SECTIONS)
@pytest.mark.parametrize("wrong", ["a string", 3, {"a": "map"}, None])
def test_a_list_section_given_a_non_list_is_rejected(section, wrong):
    bad = {**MINIMAL, section: wrong}
    with pytest.raises(ConfigError, match=f"{section} must be a list"):
        KitConfig.from_dict(bad)


@pytest.mark.parametrize("wrong", ["a string", 3, ["nested"], None])
def test_a_role_that_is_not_a_mapping_is_rejected(wrong):
    bad = {**MINIMAL, "roles": [wrong]}
    with pytest.raises(ConfigError, match="each role must be a mapping"):
        KitConfig.from_dict(bad)


@pytest.mark.parametrize("key", ["name", "description", "owns"])
def test_a_role_missing_a_required_key_is_rejected(key):
    roles = [{**MINIMAL["roles"][0]}, MINIMAL["roles"][1]]
    del roles[0][key]
    with pytest.raises((ConfigError, KeyError, TypeError)) as e:
        KitConfig.from_dict({**MINIMAL, "roles": roles})
    assert key in str(e.value), (key, str(e.value))


@pytest.mark.parametrize("key,default", [("handoff_extra", []),
                                         ("tools", DEFAULT_TOOLS),
                                         ("veto", False)])
def test_an_optional_role_key_falls_back_to_its_default(key, default):
    """These three are optional on purpose, so their absence must not raise — and
    the default has to be the documented one, since `tools` missing `Skill` would
    make /handoff uninvokable and `veto` defaulting to True would hand a second
    role a block."""
    roles = [{**MINIMAL["roles"][0]}, MINIMAL["roles"][1]]
    roles[0].pop(key, None)   # MINIMAL does not set `tools` at all
    cfg = KitConfig.from_dict({**MINIMAL, "roles": roles})
    assert getattr(cfg.roles[0], key) == default


def test_an_unknown_role_key_names_the_role_and_the_key():
    """A typo in a role key is the likeliest profile error there is, and silently
    ignoring it would drop the setting the user thought they had made."""
    roles = [{**MINIMAL["roles"][0], "ownz": ["src/**"]}, MINIMAL["roles"][1]]
    with pytest.raises(ConfigError, match=r"role 'architect' has unknown keys: \['ownz'\]"):
        KitConfig.from_dict({**MINIMAL, "roles": roles})


def test_an_unnamed_role_with_an_unknown_key_still_reports_usefully():
    roles = [{"owns": ["src/**"], "zzz": 1}, MINIMAL["roles"][1]]
    with pytest.raises(ConfigError, match=r"role '<unnamed>' has unknown keys"):
        KitConfig.from_dict({**MINIMAL, "roles": roles})


REQUIRED_SUB = [
    ("spine", "plan"), ("spine", "strategy"), ("spine", "design"),
    ("spine", "decisions"), ("spine", "risks"), ("spine", "contracts"),
    ("spine", "inherited"),
    ("toolchain", "pm"), ("toolchain", "test"), ("toolchain", "format"),
    ("toolchain", "lint"), ("toolchain", "types"),
    ("milestones", "prefix"), ("milestones", "id_format"), ("milestones", "outline"),
    ("attribution", "mention_assistant_in_commits"),
]


@pytest.mark.parametrize("section,key", REQUIRED_SUB,
                         ids=[f"{s}.{k}" for s, k in REQUIRED_SUB])
def test_every_required_subkey_is_required(section, key):
    bad = {**MINIMAL, section: {k: v for k, v in MINIMAL[section].items()
                                if k != key}}
    with pytest.raises((ConfigError, KeyError, TypeError)) as e:
        KitConfig.from_dict(bad)
    assert key in str(e.value), (section, key, str(e.value))


def test_veto_role_raises_rather_than_returning_none():
    """`validate()` already rejects a roster without exactly one veto role, so this
    is the defensive half: `veto_role` is a public property the templates call, and
    a KitConfig built directly — bypassing from_dict — must not hand them None and
    turn the omission into an UndefinedError three layers away."""
    import dataclasses
    cfg = KitConfig.from_dict(MINIMAL)
    novetoes = dataclasses.replace(
        cfg, roles=[dataclasses.replace(r, veto=False) for r in cfg.roles])
    with pytest.raises(ConfigError, match="no role carries veto: true"):
        _ = novetoes.veto_role


def test_more_than_one_veto_role_is_rejected_by_name():
    roles = [{**MINIMAL["roles"][0], "veto": True}, MINIMAL["roles"][1]]
    with pytest.raises(ConfigError, match=r"exactly one role must carry veto: true, "
                                          r"found \['architect', 'safety'\]"):
        KitConfig.from_dict({**MINIMAL, "roles": roles})


def test_an_overlap_caused_by_a_wild_first_segment_names_the_cause():
    """A glob with no literal prefix overlaps everything, so the partner named
    alongside it is usually innocent and the author reaches for the wrong one."""
    bad = {**MINIMAL, "roles": [
        {**MINIMAL["roles"][0], "owns": ["**/*.py"]},
        {**MINIMAL["roles"][1], "owns": ["tests/safety/**"]},
    ]}
    with pytest.raises(ConfigError) as e:
        KitConfig.from_dict(bad)
    msg = str(e.value)
    assert "'**/*.py' begins with a wildcard segment" in msg
    assert "The other pattern here may be fine" in msg


def test_an_ordinary_overlap_does_not_get_the_wildcard_explanation():
    bad = {**MINIMAL, "roles": [
        {**MINIMAL["roles"][0], "owns": ["src/a/**"]},
        {**MINIMAL["roles"][1], "owns": ["src/a/b/**"]},
    ]}
    with pytest.raises(ConfigError) as e:
        KitConfig.from_dict(bad)
    assert "wildcard segment" not in str(e.value)
    assert "ownership overlap: architect:src/a/** and safety:src/a/b/**" in str(e.value)


# --- critical paths -----------------------------------------------------------

def test_critical_defaults_to_empty_and_is_optional():
    """Most projects need none, so absence must be valid rather than `critical: []`
    boilerplate in every profile — the same treatment as a role's `handoff_extra`."""
    assert KitConfig.from_dict(MINIMAL).critical == []


def test_critical_reaches_the_lock():
    cfg = KitConfig.from_dict({**MINIMAL, "critical": ["src/kill_switch.py"]})
    assert cfg.to_lock()["critical"] == ["src/kill_switch.py"]


@pytest.mark.parametrize("pattern,why", [
    ("/abs/kill.py", "absolute"),
    ("./src/kill.py", "a leading './' is a '.' segment"),
    ("src/../kill.py", "'..' segment"),
    ("src//kill.py", "empty segment"),
    ("src\\kill.py", "backslash"),
])
def test_a_non_normalised_critical_path_is_rejected(pattern, why):
    """Same rule as `owns`, because the guard matches them with the same code."""
    with pytest.raises(ConfigError, match="critical path .* is not normalised"):
        KitConfig.from_dict({**MINIMAL, "critical": [pattern]})


@pytest.mark.parametrize("pattern", ["", "   ", 7, None])
def test_an_empty_or_non_string_critical_entry_is_rejected(pattern):
    with pytest.raises(ConfigError, match="critical entries must be non-empty strings"):
        KitConfig.from_dict({**MINIMAL, "critical": [pattern]})


@pytest.mark.parametrize("wrong", ["a string", 3, {"a": "map"}])
def test_critical_given_a_non_list_is_rejected(wrong):
    with pytest.raises(ConfigError, match="critical must be a list"):
        KitConfig.from_dict({**MINIMAL, "critical": wrong})


def test_a_critical_path_may_sit_inside_another_roles_tree():
    """The reason it exists: this is an ownership overlap that must NOT be rejected,
    because `critical` is not ownership — it is a refusal that outranks it."""
    cfg = KitConfig.from_dict({**MINIMAL, "critical": ["docs/adr/0001-frozen.md"]})
    assert "docs/adr/**" in cfg.roles[0].owns
    assert cfg.critical == ["docs/adr/0001-frozen.md"]


# --- per-role model (2026-10-02) ----------------------------------------------

def test_model_defaults_to_inherit():
    """`inherit` is the safe default: whatever the session runs, every role runs. A kit
    that silently picked a model would spend the user's money on an assumption."""
    cfg = KitConfig.from_dict(MINIMAL)
    assert [r.model for r in cfg.roles] == ["inherit", "inherit"]
    assert cfg.to_lock()["roles"][0]["model"] == "inherit"


@pytest.mark.parametrize("value", ["inherit", "opus", "sonnet", "haiku", "fable",
                                   "claude-opus-5-5", "claude-sonnet-5"])
def test_an_accepted_model_value(value):
    roles = [{**MINIMAL["roles"][0], "model": value}, MINIMAL["roles"][1]]
    assert KitConfig.from_dict({**MINIMAL, "roles": roles}).roles[0].model == value


@pytest.mark.parametrize("value", ["Opus", "sonnet-4", "gpt-4", "best", "inherits",
                                   "", "   "])
def test_an_unresolvable_model_value_is_rejected(value):
    """Claude Code does not report an unusable `model` until the subagent is dispatched —
    mid-task, with the role card written and the work assigned. Catch it at the profile."""
    roles = [{**MINIMAL["roles"][0], "model": value}, MINIMAL["roles"][1]]
    with pytest.raises(ConfigError, match="model"):
        KitConfig.from_dict({**MINIMAL, "roles": roles})


def test_the_veto_role_may_not_run_on_the_cheap_model():
    """The one combination the kit refuses. The veto role produces every gate's Floors
    dimension and its VETO cannot be overridden, and a floor it fails to test reads
    exactly like a floor that holds — the failure is silent, which is why this is an
    error rather than advice."""
    roles = [MINIMAL["roles"][0], {**MINIMAL["roles"][1], "model": "haiku"}]
    with pytest.raises(ConfigError, match="may not run on 'haiku'"):
        KitConfig.from_dict({**MINIMAL, "roles": roles})


@pytest.mark.parametrize("value", ["inherit", "opus", "sonnet", "claude-opus-5-5"])
def test_the_veto_role_accepts_anything_not_explicitly_cheap(value):
    """`CHEAP_MODELS` is a set of one on purpose. Ranking the whole lineup would be wrong
    within two releases, and an alias the kit does not recognise is trusted rather than
    guessed at."""
    roles = [MINIMAL["roles"][0], {**MINIMAL["roles"][1], "model": value}]
    assert KitConfig.from_dict({**MINIMAL, "roles": roles}).veto_role.model == value


def test_a_non_veto_role_may_run_on_the_cheap_model():
    """The refusal is narrow: one role, for a stated reason. Everything else is the
    user's call, and a mechanical wiring role is exactly where the saving lives."""
    roles = [{**MINIMAL["roles"][0], "model": "haiku"}, MINIMAL["roles"][1]]
    assert KitConfig.from_dict({**MINIMAL, "roles": roles}).roles[0].model == "haiku"


# --- memory scope, and the tools default (2026-10-03) ------------------------

def test_memory_defaults_to_project():
    """`project` is `.claude/agent-memory/<role>/` — the same directory the kit renders
    MEMORY.md into, and the one the ownership guard already partitions per role."""
    assert [r.memory for r in KitConfig.from_dict(MINIMAL).roles] == ["project"] * 2


@pytest.mark.parametrize("scope", ["project", "local"])
def test_an_accepted_memory_scope(scope):
    roles = [{**MINIMAL["roles"][0], "memory": scope}, MINIMAL["roles"][1]]
    assert KitConfig.from_dict({**MINIMAL, "roles": roles}).roles[0].memory == scope


def test_memory_user_is_refused():
    """One directory shared across every project on the machine: a fact learned about one
    codebase would be presented as true of another, and the ownership guard only governs
    paths inside this project."""
    roles = [{**MINIMAL["roles"][0], "memory": "user"}, MINIMAL["roles"][1]]
    with pytest.raises(ConfigError, match="may not use memory: 'user'"):
        KitConfig.from_dict({**MINIMAL, "roles": roles})


@pytest.mark.parametrize("scope", ["Project", "shared", "", "none"])
def test_an_unresolvable_memory_scope_is_rejected(scope):
    roles = [{**MINIMAL["roles"][0], "memory": scope}, MINIMAL["roles"][1]]
    with pytest.raises(ConfigError, match="memory"):
        KitConfig.from_dict({**MINIMAL, "roles": roles})


def test_default_tools_cover_the_tools_the_guards_police():
    """`NotebookEdit` was absent while both the file guard and the ownership guard matched
    it, so the kit policed a tool its own roles could not use. On a notebook-heavy project
    a role could not have edited a notebook at all."""
    from kitgen.model import DEFAULT_TOOLS
    import json as _json
    from pathlib import Path as _P
    matchers = _json.loads(
        (_P(__file__).resolve().parents[2] / "hooks/hooks.json").read_text()
    )["hooks"]["PreToolUse"]
    policed = set()
    for entry in matchers:
        policed |= {t for t in entry.get("matcher", "").split("|") if t != "Read"}
    # Guard broadly, grant narrowly. `MultiEdit` is matched defensively — harmless if the
    # host has no such tool, the whole guard if it does — but it is deliberately NOT
    # granted, because listing a tool that may not exist in a role card's frontmatter is
    # a claim about the host that the kit cannot check. Every tool the kit DOES grant and
    # police must appear in both.
    granted = set(DEFAULT_TOOLS)
    assert policed - granted == {"MultiEdit"}, sorted(policed - granted)
    assert {"Edit", "Write", "NotebookEdit"} <= policed & granted


def test_default_tools_let_a_role_track_multi_step_work():
    from kitgen.model import DEFAULT_TOOLS
    assert "TodoWrite" in DEFAULT_TOOLS
    assert "Agent" not in DEFAULT_TOOLS, (
        "a role must not dispatch: spawn depth is 1 and only the Orchestrator dispatches")
