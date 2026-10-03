# plugins/agentic-kit/kitgen/tests/test_hooks_json.py
import json
import os
import stat
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "hooks"


def load():
    return json.loads((HOOKS / "hooks.json").read_text())["hooks"]


def test_every_declared_event_is_one_we_implement():
    assert set(load()) == {"PreToolUse", "PostToolUse", "SubagentStop",
                           "SessionStart"}


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

def test_plugin_declares_a_version():
    """`claude plugin validate` warns without one, and /plugin update -- the whole
    update model in design spec §4.1 -- has nothing to compare against."""
    pj = json.loads((HOOKS.parent / ".claude-plugin/plugin.json").read_text())
    assert pj["version"], pj
    assert pj["version"].count(".") == 2, pj["version"]


def test_no_unknown_hook_event_is_declared():
    """`claude plugin validate` only WARNS on an unknown event ("entry ignored at
    runtime"), so a typo there yields a hook that silently never fires. Pin the set."""
    known = {"PreToolUse", "PostToolUse", "SubagentStop", "SessionStart",
             "UserPromptSubmit", "Stop", "Notification", "PreCompact"}
    assert set(load()) <= known, set(load()) - known


def test_the_file_guard_matcher_covers_every_file_writing_tool():
    """The ownership guard's own matcher lists MultiEdit; the plugin's file guard did
    not, so a secret path would have been readable through it. Harmless if the host
    has no such tool, and the whole guard otherwise if it does."""
    entries = load()["PreToolUse"]
    matchers = [e["matcher"] for e in entries if "matcher" in e]
    file_matcher = next(m for m in matchers if "Read" in m)
    for tool in ("Read", "Edit", "Write", "NotebookEdit", "MultiEdit"):
        assert tool in file_matcher.split("|"), (tool, file_matcher)


def test_session_start_is_registered_without_a_matcher():
    """SessionStart fires once per session, so it takes no matcher — and the kit needs it
    to: §5.1's drift signal was defined and read by nothing until this hook existed."""
    entries = load()["SessionStart"]
    assert len(entries) == 1
    assert "matcher" not in entries[0], "SessionStart has no tool to match on"
    assert "session-start.sh" in entries[0]["hooks"][0]["command"]
