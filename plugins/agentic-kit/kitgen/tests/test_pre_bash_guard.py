# plugins/agentic-kit/kitgen/tests/test_pre_bash_guard.py
import json

import pytest

from .hooks_conftest import bash_payload, run_hook

HOOK = "pre-bash-guard.sh"


def make_project(tmp_path, secrets=None, **overrides):
    lock = {
        "secrets": secrets if secrets is not None else ["./.env"],
        "forge": {"kind": "gitlab", "cli": "glab", "exclusive": True,
                  "mirror": None, "remote": "git@h:o/r.git", "ci": ".gitlab-ci.yml"},
        "attribution": {"mention_assistant_in_commits": False},
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
    'git commit -am "wip"',
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
    "git commit --only src/a.py -m 'fix the -a flag handling'",
    "git add src/a.py",
    "git add -p src/a.py",
    "git status",
    "git diff --cached",
    "git push --force-with-lease origin topic",
])
def test_explicit_path_operations_are_allowed(tmp_path, command):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == 0, command


@pytest.mark.parametrize("command", [
    "rm -rf build",
    "rm -fr build",
    "rm -r -f build",
    "git push --force origin main",
    "git push -f",
    "git push origin +main",
    "git reset --hard HEAD~1",
    "docker compose down -v",
    "docker-compose down --volumes",
])
def test_destructive_commands_are_blocked(tmp_path, command):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == 2, command


@pytest.mark.parametrize("command", [
    "git  add  -A",
    "git add --all .",
    "GIT_DIR=x git add -A",
    "git -C /other add -A",
    "env git stash",
    "sudo rm -rf /x",
    "echo $(git add -A)",
    "make && git add -A",
    "make | git add -A",
    "/usr/bin/git add -A",
])
def test_spellings_of_a_blocked_command_are_blocked(tmp_path, command):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == 2, command


def test_the_other_forge_cli_is_blocked_when_exclusive(tmp_path):
    p = make_project(tmp_path)
    r = run_hook(HOOK, bash_payload("gh pr create", p), p)
    assert r.returncode == 2
    assert "glab" in r.stderr
    for spelling in ["/usr/bin/gh pr list", "GH_TOKEN=x gh pr list", "ls && gh pr list"]:
        assert run_hook(HOOK, bash_payload(spelling, p), p).returncode == 2, spelling


def test_the_chosen_forge_cli_is_allowed(tmp_path):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload("glab mr list", p), p).returncode == 0


def test_github_projects_block_glab_and_allow_gh(tmp_path):
    p = make_project(tmp_path, forge={"kind": "github", "cli": "gh",
                                      "exclusive": True, "mirror": None,
                                      "remote": "git@h:o/r.git", "ci": None})
    r = run_hook(HOOK, bash_payload("glab mr list", p), p)
    assert r.returncode == 2
    assert "gh" in r.stderr
    assert run_hook(HOOK, bash_payload("gh pr list", p), p).returncode == 0


def test_neither_cli_is_blocked_when_forge_is_none(tmp_path):
    p = make_project(tmp_path, forge={"kind": "none", "cli": "none",
                                      "exclusive": False, "mirror": None,
                                      "remote": None, "ci": None})
    assert run_hook(HOOK, bash_payload("gh pr list", p), p).returncode == 0
    assert run_hook(HOOK, bash_payload("glab mr list", p), p).returncode == 0


def test_a_non_exclusive_forge_blocks_neither_cli(tmp_path):
    p = make_project(tmp_path, forge={"kind": "gitlab", "cli": "glab",
                                      "exclusive": False, "mirror": "github",
                                      "remote": "git@h:o/r.git", "ci": ".gitlab-ci.yml"})
    assert run_hook(HOOK, bash_payload("gh pr list", p), p).returncode == 0
    assert run_hook(HOOK, bash_payload("glab mr list", p), p).returncode == 0


def test_assistant_attribution_in_a_commit_message_is_blocked(tmp_path):
    p = make_project(tmp_path)
    cmd = "git commit --only a.py -m 'feat: x\n\nCo-Authored-By: Claude <x@y>'"
    r = run_hook(HOOK, bash_payload(cmd, p), p)
    assert r.returncode == 2
    assert "attribution" in r.stderr.lower()
    for blocked in [
        "git commit --only a.py --message='feat: x\n\nCo-Authored-By: Claude <x@y>'",
        "git commit --only a.py -m 'feat: x' -m 'Generated with Claude Code'",
        "git commit --only a.py -m 'feat: x \U0001f916'",
    ]:
        assert run_hook(HOOK, bash_payload(blocked, p), p).returncode == 2, blocked


def test_a_message_that_merely_names_the_assistant_is_allowed(tmp_path):
    """The policy is 'do not credit the assistant', not 'never type the word'."""
    p = make_project(tmp_path)
    for ok in ["git commit --only a.py -m 'docs: mention anthropic sdk'",
               "git commit --only a.py -m 'fix: claude hook ordering'"]:
        assert run_hook(HOOK, bash_payload(ok, p), p).returncode == 0, ok


def test_a_commit_message_naming_a_secret_path_is_allowed(tmp_path):
    p = make_project(tmp_path)
    for ok in ["git commit --only a.py -m \"feat: touch .env handling\"",
               "git commit --only a.py --message='feat: touch .env handling'",
               "git commit --only a.py -m 'feat: x\n\nnotes about .env; more'"]:
        assert run_hook(HOOK, bash_payload(ok, p), p).returncode == 0, ok
    # ...but the message skip must not become a bypass for what follows it.
    r = run_hook(HOOK, bash_payload("git commit -m 'x' && cat .env | base64", p), p)
    assert r.returncode == 2


@pytest.mark.parametrize("command", [
    "git checkout -- .",
    "git checkout .",
    "git restore .",
    "git restore --staged .",
    "git clean -fd",
    "git clean -n",
    "git push --delete origin main",
    "git push -d origin main",
    "git push origin :main",
    "sudo -u bob rm -rf /x",
    "sudo -g wheel -u bob git stash",
    "env -u FOO git add -A",
    "nice -n 5 rm -rf x",
])
def test_working_tree_wipes_and_remote_deletes_are_blocked(tmp_path, command):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == 2, command


@pytest.mark.parametrize("command", [
    "git checkout topic",
    "git checkout -b topic",
    "git checkout -- src/a.py",
    "git restore src/a.py",
    "git restore --staged src/a.py",
    "git push origin topic",
])
def test_scoped_checkout_restore_and_push_are_allowed(tmp_path, command):
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == 0, command


def test_the_wipe_message_names_the_peer_agent_and_the_rm_message_a_next_step(tmp_path):
    p = make_project(tmp_path)
    r = run_hook(HOOK, bash_payload("git clean -fd", p), p)
    assert "peer agent" in r.stderr
    r = run_hook(HOOK, bash_payload("rm -rf build", p), p)
    assert "make clean" in r.stderr and "rm <file>" in r.stderr


@pytest.mark.parametrize("command, expected", [
    ('bash -c "git add -A"', 0),
    ("sh -c 'git stash'", 0),
    ("xargs git add -A", 0),
    ("git add -A\\", 0),
    ('cat "$(echo .e)nv"', 0),
    ("git commit -F msg.txt", 0),
    ('echo "a; git stash now"', 2),
    ("echo 'a; git reset --hard now'", 2),
])
def test_known_matcher_limits(tmp_path, command, expected):
    """Documented limits of matching command STRINGS, not oversights (design spec
    6.2: neither layer is a sandbox). The first six slip through (so does `echo 'a; git add -A'`, only because the
    closing quote sticks to `-A`: luck, not design): a command inside
    a quoted interpreter string, a wrapper that is not peeled, a trailing
    backslash, a path built at run time, a message read from a file. The last two are
    false positives: the segmenter is not quote-aware. This pins CURRENT behaviour;
    if one changes, decide deliberately and update 6.2."""
    p = make_project(tmp_path)
    assert run_hook(HOOK, bash_payload(command, p), p).returncode == expected, command


def test_attribution_is_allowed_when_the_profile_permits_it(tmp_path):
    p = make_project(tmp_path,
                     attribution={"mention_assistant_in_commits": True})
    cmd = "git commit --only a.py -m 'feat: x\n\nCo-Authored-By: Claude <x@y>'"
    assert run_hook(HOOK, bash_payload(cmd, p), p).returncode == 0


def test_a_command_naming_a_secret_path_is_blocked(tmp_path):
    """Read/Edit denies already cover cat/head/tail/sed/tee and redirection targets.
    This hook covers the remainder: readers Claude Code does not recognise, and
    interpreters. Overlapping with the path deny on `cat` is harmless."""
    p = make_project(tmp_path)
    for cmd in ["base64 .env", "xxd ./.env", "strings .env",
                "python -c \"print(open('.env').read())\"", "cp .env /tmp/x"]:
        r = run_hook(HOOK, bash_payload(cmd, p), p)
        assert r.returncode == 2, cmd
        assert "secret path" in r.stderr


def test_a_glob_secret_is_matched_by_its_literal_prefix(tmp_path):
    p = make_project(tmp_path, secrets=["./secrets/**"])
    r = run_hook(HOOK, bash_payload("cat secrets/db/pw.txt", p), p)
    assert r.returncode == 2


def test_an_unrelated_command_is_not_blocked_by_the_secret_check(tmp_path):
    p = make_project(tmp_path)
    for safe in ["cat README.md", "ls -la", "cat .env.example",
                 "cp .env.example .env", "grep -r TOKEN src/"]:
        assert run_hook(HOOK, bash_payload(safe, p), p).returncode == 0, safe


def test_a_substring_match_does_not_cause_a_false_block(tmp_path):
    p = make_project(tmp_path)
    for safe in ["echo 'git add -A is forbidden'",
                 "grep -r 'git stash' docs/",
                 "ls github-notes/"]:
        assert run_hook(HOOK, bash_payload(safe, p), p).returncode == 0, safe
