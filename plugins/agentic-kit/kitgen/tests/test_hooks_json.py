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
