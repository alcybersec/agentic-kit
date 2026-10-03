"""The blast-radius test: with no kit.lock.json every hook must be a no-op."""
import json
import subprocess

import pytest

from .hooks_conftest import HOOKS, bash_payload, file_payload, run_hook

# Every shipped hook, not a hand-kept subset: the ownership guard and the session-start
# hook were added later and the blast-radius rule applies to them identically.
ALL_HOOKS = ["pre-bash-guard.sh", "pre-file-guard.sh", "post-edit-format.sh",
             "subagent-stop-check.sh", "ownership-guard.sh", "session-start.sh"]


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


# --- Beyond the plan's three cases: everything else that could make a hook
# --- misbehave in a repository that has nothing to do with the kit.

def _raw(hook, stdin, *, env, cwd=None):
    return subprocess.run(["/usr/bin/bash", str(HOOKS / hook)], input=stdin,
                          capture_output=True, text=True, env=env, cwd=cwd)


def _env(project_dir=None, plugin_root=True, path="/usr/bin:/bin"):
    env = {"PATH": path}
    if plugin_root:
        env["CLAUDE_PLUGIN_ROOT"] = str(HOOKS.parent)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return env


def _assert_silent_ok(r, hook):
    assert r.returncode == 0, (hook, r.stdout, r.stderr)
    assert r.stdout == "" and r.stderr == "", (hook, r.stdout, r.stderr)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_when_jq_is_not_installed(hook, bare_project, tmp_path):
    empty = tmp_path / "emptybin"
    empty.mkdir()
    r = _raw(hook, json.dumps(bash_payload("git add -A", bare_project)),
             env=_env(bare_project, path=str(empty)))
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("content", ["", "[]", '"x"', "null", "false", "42"])
@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_when_the_lock_is_not_a_json_object(hook, content, bare_project):
    (bare_project / ".claude").mkdir()
    (bare_project / ".claude/kit.lock.json").write_text(content)
    r = _raw(hook, json.dumps(bash_payload("git add -A", bare_project)),
             env=_env(bare_project))
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_when_the_lock_is_a_directory(hook, bare_project):
    (bare_project / ".claude/kit.lock.json").mkdir(parents=True)
    r = _raw(hook, json.dumps(bash_payload("x", bare_project)), env=_env(bare_project))
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_when_project_dir_does_not_exist(hook, tmp_path):
    r = _raw(hook, json.dumps(bash_payload("x", tmp_path)),
             env=_env(tmp_path / "nope"))
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_when_no_project_dir_and_no_cwd(hook, bare_project):
    r = _raw(hook, json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"}}),
             env=_env(None), cwd=bare_project)
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_when_the_payload_has_no_tool_input(hook, bare_project):
    r = _raw(hook, json.dumps({"tool_name": "Bash", "cwd": str(bare_project)}),
             env=_env(bare_project))
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("stdin", ["", "   \n", "not json", "[]", '"x"', "null", "7"])
@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_on_malformed_stdin(hook, stdin, bare_project):
    r = _raw(hook, stdin, env=_env(bare_project))
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_when_plugin_root_is_unset(hook, bare_project):
    """`set -u` must not trip on an unset CLAUDE_PLUGIN_ROOT before the lock check."""
    r = _raw(hook, json.dumps(bash_payload("x", bare_project)),
             env=_env(bare_project, plugin_root=False))
    _assert_silent_ok(r, hook)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_inert_with_project_dir_unset_and_cwd_in_payload(hook, bare_project):
    r = _raw(hook, json.dumps(bash_payload("x", bare_project)), env=_env(None))
    _assert_silent_ok(r, hook)


# --- The preamble is real and shared.

@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_every_hook_sources_the_shared_preamble_and_calls_kit_init(hook):
    text = (HOOKS / hook).read_text()
    assert "lib/kitlock.sh" in text, hook
    assert "\nkit_init\n" in text, hook


@pytest.mark.parametrize("via", ["env", "cwd"])
def test_kit_init_finds_a_valid_lock(via, bare_project):
    """The positive path: a valid lock must survive kit_init and be exported."""
    (bare_project / ".claude").mkdir()
    (bare_project / ".claude/kit.lock.json").write_text('{"a": {"b": "c"}}')
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"},
                          "cwd": str(bare_project)})
    env = _env(bare_project if via == "env" else None)
    r = subprocess.run(
        ["/usr/bin/bash", "-c",
         f'source "{HOOKS}/lib/kitlock.sh"; kit_init; echo "$KIT_LOCK"; kit_q .a.b; kit_in .tool_name'],
        input=payload, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[:3] == [f"{bare_project}/.claude/kit.lock.json", "c", "Bash"]
