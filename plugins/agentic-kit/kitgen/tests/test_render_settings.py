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
