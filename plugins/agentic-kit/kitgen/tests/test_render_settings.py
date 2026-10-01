import json

import pytest

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


def test_the_kit_protects_its_own_config(load_fixture):
    deny = settings(load_fixture("services_layout"))["permissions"]["deny"]
    for path in ("./.claude/settings.json", "./.claude/kit.lock.json"):
        assert f"Edit({path})" in deny


UNCONSULTED = ("Write(", "NotebookEdit(", "Glob(", "MultiEdit(")


def test_no_rule_uses_a_prefix_claude_code_never_consults(load_fixture):
    """Per the permissions docs, a path rule for Write/NotebookEdit/Glob/MultiEdit is
    "accepted but never consulted, and warns at startup". Read covers Edit and Write;
    Edit is what covers NotebookEdit. Emitting any of these is strictly worse than
    omitting it, and it would warn in every project that installs the kit."""
    for name in FIXTURES:
        perms = settings(load_fixture(name))["permissions"]
        for rule in perms["allow"] + perms["deny"]:
            assert not rule.startswith(UNCONSULTED), (name, rule)


def test_the_other_forge_cli_is_denied_when_exclusive(load_fixture):
    gl = settings(load_fixture("services_layout"))["permissions"]["deny"]
    assert "Bash(gh:*)" in gl
    gh = settings(load_fixture("python_monolith"))["permissions"]["deny"]
    assert "Bash(glab:*)" in gh


def test_no_forge_denies_neither_cli(load_fixture):
    deny = settings(load_fixture("greenfield_prd"))["permissions"]["deny"]
    assert "Bash(gh:*)" not in deny and "Bash(glab:*)" not in deny


def test_a_real_but_non_exclusive_forge_denies_neither_cli(load_variant):
    """greenfield_prd is both kind: none AND exclusive: false, so on its own it
    cannot distinguish 'no forge' from 'not exclusive'. §6.3 requires a real forge
    with exclusive: false to block neither CLI, and its own CLI to stay allowed."""
    cfg = load_variant("services_layout",
                       forge={**load_variant("services_layout").to_lock()["forge"],
                              "exclusive": False})
    perms = json.loads(render(cfg)[".claude/settings.json"])["permissions"]
    assert "Bash(gh:*)" not in perms["deny"]
    assert "Bash(glab:*)" not in perms["deny"]
    assert "Bash(glab:*)" in perms["allow"]


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


@pytest.mark.parametrize("entry", [
    "Bash(rm -rf:*)", "Bash(git push --force:*)", "Bash(git push -f:*)",
    "Bash(git reset --hard:*)", "Bash(docker compose down -v:*)",
    "Bash(rm -fr:*)", "Bash(docker compose down --volumes:*)",
    "Bash(docker-compose down -v:*)",
])
def test_destructive_commands_are_denied_individually(entry, load_fixture):
    assert entry in settings(load_fixture("services_layout"))["permissions"]["deny"]


@pytest.mark.parametrize("entry", [
    "Bash(git add -A:*)", "Bash(git add .:*)", "Bash(git commit -a:*)",
    "Bash(git stash:*)", "Bash(git commit -am:*)", "Bash(git commit --all:*)",
    "Bash(git add --all:*)", "Bash(git add -u:*)",
])
def test_staging_sweeps_are_denied(entry, load_fixture):
    """These four are why a shared git index absorbs one agent's work into
    another's commit. They are the kit's reason for existing, so assert each."""
    assert entry in settings(load_fixture("services_layout"))["permissions"]["deny"]


@pytest.mark.parametrize("entry", [
    "Bash(git checkout -- .:*)", "Bash(git checkout .:*)",
    "Bash(git restore .:*)", "Bash(git clean:*)",
])
def test_working_tree_wipes_are_denied(entry, load_fixture):
    """These destroy a *peer's* uncommitted work on a shared checkout, not just
    your own -- 'undo my changes' is the most plausible reflex there is."""
    assert entry in settings(load_fixture("services_layout"))["permissions"]["deny"]


def test_worktree_allow_is_narrowed_to_add_and_list(load_fixture):
    allow = settings(load_fixture("services_layout"))["permissions"]["allow"]
    assert "Bash(git worktree add:*)" in allow
    assert "Bash(git worktree list:*)" in allow
    assert "Bash(git worktree:*)" not in allow


def test_every_toolchain_command_is_allowed(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        allow = settings(cfg)["permissions"]["allow"]
        for key in ("test", "format", "lint", "types", "pm"):
            assert f"Bash({cfg.toolchain[key]}:*)" in allow, (name, key)


def test_no_empty_permission_rule_is_emitted(load_fixture):
    """Cheap insurance only; it cannot currently fail, because validate() rejects
    empty toolchain values so no loadable profile renders '(:*)'. The real guard is
    test_empty_toolchain_value_is_rejected in test_model.py."""
    for name in FIXTURES:
        perms = settings(load_fixture(name))["permissions"]
        for rule in perms["allow"] + perms["deny"]:
            assert rule.strip(), name
            assert "()" not in rule and "(:*)" not in rule, (name, rule)


@pytest.mark.parametrize("overrides", [
    {"forge": {"kind": "github", "remote": "g", "cli": "gh", "ci": "c",
               "exclusive": False}},
    {"forge": {"kind": "none", "remote": None, "cli": "none", "ci": None,
               "exclusive": True}},
    {"secrets": []},
])
def test_every_conditional_combination_still_emits_valid_json(load_variant, overrides):
    cfg = load_variant("services_layout", **overrides)
    parsed = json.loads(render(cfg)[".claude/settings.json"])
    assert parsed["permissions"]["allow"] and parsed["permissions"]["deny"]
