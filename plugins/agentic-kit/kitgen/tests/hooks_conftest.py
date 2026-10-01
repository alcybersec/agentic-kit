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
