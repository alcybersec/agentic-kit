import json

import pytest

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def settings(cfg):
    return json.loads(render(cfg)[".claude/settings.json"])


def test_settings_is_valid_json(load_fixture):
    for name in FIXTURES:
        assert settings(load_fixture(name))["permissions"]


def test_every_secret_path_is_denied_for_read_edit_and_write(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        deny = settings(cfg)["permissions"]["deny"]
        for s in cfg.secrets:
            for verb in ("Read", "Edit", "Write"):
                assert f"{verb}({s})" in deny, (name, verb, s)


def test_the_kit_protects_its_own_config_from_both_verbs(load_fixture):
    deny = settings(load_fixture("services_layout"))["permissions"]["deny"]
    for path in ("./.claude/settings.json", "./.claude/kit.lock.json"):
        assert f"Edit({path})" in deny
        assert f"Write({path})" in deny


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
])
def test_destructive_commands_are_denied_individually(entry, load_fixture):
    assert entry in settings(load_fixture("services_layout"))["permissions"]["deny"]


@pytest.mark.parametrize("entry", [
    "Bash(git add -A:*)", "Bash(git add .:*)", "Bash(git commit -a:*)",
    "Bash(git stash:*)",
])
def test_staging_sweeps_are_denied(entry, load_fixture):
    """These four are why a shared git index absorbs one agent's work into
    another's commit. They are the kit's reason for existing, so assert each."""
    assert entry in settings(load_fixture("services_layout"))["permissions"]["deny"]


def test_every_toolchain_command_is_allowed(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        allow = settings(cfg)["permissions"]["allow"]
        for key in ("test", "format", "lint", "types", "pm"):
            assert f"Bash({cfg.toolchain[key]}:*)" in allow, (name, key)


def test_no_empty_permission_rule_is_emitted(load_fixture):
    """Regression for the Bash(:*) defect: an empty toolchain value used to render
    a rule with no prefix at all."""
    for name in FIXTURES:
        perms = settings(load_fixture(name))["permissions"]
        for rule in perms["allow"] + perms["deny"]:
            assert rule.strip(), name
            assert "()" not in rule and "(:*)" not in rule, (name, rule)
