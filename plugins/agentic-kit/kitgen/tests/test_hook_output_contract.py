# plugins/agentic-kit/kitgen/tests/test_hook_output_contract.py
"""Every deny path must speak the Claude Code hook output contract.

The contract has two halves and the kit got the second one wrong for the whole
build: Claude Code reads a hook's decision object from **stdout**, and when a
hook exits 2 it feeds the hook's **stderr** to the agent as the blocking reason.
`kit_deny` wrote the object to stderr, so the decision was never read -- only
`exit 2` blocked anything -- and every carefully worded remediation message
reached the agent as a raw JSON blob.

No existing test could see it. Around 270 hook tests assert on stderr, but all
of them with substring checks, and `"./secrets/**" in r.stderr` is just as true
of `{"systemMessage":"... ./secrets/** ..."}` as of the sentence. So this file
asserts the shape rather than the content: stderr parses as prose and not as
JSON, and stdout is empty, because anything on stdout would be read as a
decision object.
"""
import json
import subprocess

import pytest

from kitgen.render import render

from .hooks_conftest import HOOKS, bash_payload, file_payload, run_hook

LOCK = {
    "secrets": ["./.env", "./secrets/**"],
    "forge": {"kind": "gitlab", "cli": "glab", "exclusive": True,
              "mirror": None, "remote": "git@h:o/r.git", "ci": ".gitlab-ci.yml"},
    "attribution": {"mention_assistant_in_commits": True},
    "toolchain": {"format": "ruff format"},
    "roles": [{"name": "data", "handoff_extra": ["MIGRATION:"]}],
}


def project(tmp_path):
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps(LOCK))
    return tmp_path


def transcript(p, text):
    t = p / "t.jsonl"
    t.write_text(json.dumps({"role": "assistant", "content": text}) + "\n")
    return t


# Each case drives one hook down one deny path. The payloads are the same ones
# the per-hook test files use, so a change in what blocks is caught there; this
# file only cares how the block is reported.
def _bash(p):
    return run_hook("pre-bash-guard.sh", bash_payload("git add -A", p), p)


def _bash_secret(p):
    return run_hook("pre-bash-guard.sh", bash_payload("cat .env", p), p)


def _file(p):
    return run_hook("pre-file-guard.sh", file_payload("Read", str(p / ".env"), p), p)


def _stop(p):
    return run_hook("subagent-stop-check.sh",
                    {"transcript_path": str(transcript(p, "done")), "cwd": str(p)}, p)


DENIALS = {"pre-bash-guard/sweep": _bash, "pre-bash-guard/secret": _bash_secret,
           "pre-file-guard": _file, "subagent-stop-check": _stop}


def assert_contract(r, label):
    assert r.returncode == 2, (label, r.returncode, r.stdout, r.stderr)
    assert r.stdout == "", (
        f"{label}: stdout must be empty -- Claude Code parses a hook's stdout as "
        f"a decision object, so stray output there is read as one")
    assert r.stderr.strip(), f"{label}: a block must explain itself"
    with pytest.raises(ValueError):
        json.loads(r.stderr)
    for marker in ("hookSpecificOutput", "permissionDecision", "systemMessage",
                   '{"', '"}'):
        assert marker not in r.stderr, (
            f"{label}: the reason reaches the agent verbatim, so it must be prose, "
            f"not a serialised object -- found {marker!r}")


@pytest.mark.parametrize("label", sorted(DENIALS))
def test_plugin_hook_denials_are_prose_on_stderr(tmp_path, label):
    assert_contract(DENIALS[label](project(tmp_path)), label)


@pytest.mark.parametrize("fixture", ["python_monolith", "services_layout"])
def test_ownership_guard_denials_are_prose_on_stderr(tmp_path, fixture, load_fixture):
    """The guard used to carry its own copy of `deny`, rendered into the project. Since
    2026-10-02 it is a plugin hook using `kit_deny` from the shared library — so this
    checks the same contract through the path a real session takes."""
    man = render(load_fixture(fixture))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    script = HOOKS / "ownership-guard.sh"
    (tmp_path / ".claude/kit.lock.json").write_text(man[".claude/kit.lock.json"])

    roles = [r["name"] for r in json.loads(man[".claude/kit.lock.json"])["roles"]]
    # Two roles, so one is editing the other's territory: the guard's own tests
    # own the question of which paths those are, this one just needs a block.
    blocks = [(".claude/agent-memory/%s/MEMORY.md" % roles[1], roles[0]),
              (".claude/agents/%s.md" % roles[0], roles[0])]
    for rel, actor in blocks:
        r = subprocess.run(
            ["bash", str(script)],
            input=json.dumps({"tool_name": "Edit",
                              "tool_input": {"file_path": str(tmp_path / rel)},
                              "cwd": str(tmp_path), "agent_id": "a0",
                              "agent_type": actor}),
            capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)})
        assert_contract(r, f"ownership-guard/{fixture}/{rel}")
