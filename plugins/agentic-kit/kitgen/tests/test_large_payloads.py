# plugins/agentic-kit/kitgen/tests/test_large_payloads.py
"""A hook must still work when the payload is large.

`kit_init` used to `export KIT_INPUT`, putting the whole raw payload into every
child process's environment. Linux caps a single environment string at
MAX_ARG_STRLEN — 32 pages, 131072 bytes — and past that `execve` fails with
E2BIG, so every `jq` the helpers run died. The hook then read an empty command and
exited 0: a payload over ~128 KB silently disarmed the entire guard layer.

Both reachable in ordinary use. A Bash command carrying a heredoc — a migration, a
generated config, a long SQL script — passes 128 KB without being remarkable, and a
verbose subagent's `last_assistant_message` passes it easily, which made the
handoff gate pass for exactly the agents that said the most.

Every case here is sized just over the limit, and each is ~1 KB under it as a
control, so a failure says "the limit" rather than "something about big strings".
"""
import json

import pytest

from .hooks_conftest import bash_payload, file_payload, run_hook

LIMIT = 131072


def lock(tmp_path, **over):
    data = {
        "secrets": ["./.env"],
        "forge": {"kind": "gitlab", "cli": "glab", "exclusive": True,
                  "mirror": None, "remote": "git@h:o/r.git", "ci": ".gitlab-ci.yml"},
        "attribution": {"mention_assistant_in_commits": False},
        "toolchain": {"format": "true"},
        "roles": [{"name": "data", "handoff_extra": ["MIGRATION:"]}],
    }
    data.update(over)
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps(data))
    return tmp_path


def pad(n):
    return "\n# " + "x" * n


@pytest.mark.parametrize("size,label", [(LIMIT - 1024, "just under MAX_ARG_STRLEN"),
                                        (LIMIT + 1024, "just over"),
                                        (LIMIT * 3, "well over")])
def test_a_staging_sweep_is_blocked_whatever_the_command_length(tmp_path, size, label):
    p = lock(tmp_path)
    r = run_hook("pre-bash-guard.sh", bash_payload("git add -A" + pad(size), p), p)
    assert r.returncode == 2, (label, r.returncode, r.stdout, r.stderr[:200])


@pytest.mark.parametrize("size,label", [(LIMIT - 1024, "just under"),
                                        (LIMIT + 1024, "just over")])
def test_a_secret_read_is_blocked_whatever_the_command_length(tmp_path, size, label):
    p = lock(tmp_path)
    r = run_hook("pre-bash-guard.sh",
                 bash_payload("base64 ./.env" + pad(size), p), p)
    assert r.returncode == 2, (label, r.returncode, r.stderr[:200])


@pytest.mark.parametrize("size,label", [(LIMIT - 1024, "just under"),
                                        (LIMIT + 1024, "just over")])
def test_an_attribution_line_is_blocked_whatever_the_message_length(tmp_path, size, label):
    p = lock(tmp_path)
    msg = "Co-Authored-By: Claude <noreply@anthropic.com>" + pad(size)
    r = run_hook("pre-bash-guard.sh",
                 bash_payload(f"git commit --only src/a.py -m '{msg}'", p), p)
    assert r.returncode == 2, (label, r.returncode, r.stderr[:200])


@pytest.mark.parametrize("size,label", [(LIMIT - 1024, "just under"),
                                        (LIMIT + 1024, "just over")])
def test_a_secret_file_path_is_blocked_with_a_large_payload(tmp_path, size, label):
    """The file guard's own payload is small, but a hook receives the whole JSON
    object and other fields can be large."""
    p = lock(tmp_path)
    payload = file_payload("Read", str(p / ".env"), p)
    payload["transcript_path"] = "/x" + "y" * size
    r = run_hook("pre-file-guard.sh", payload, p)
    assert r.returncode == 2, (label, r.returncode, r.stderr[:200])


@pytest.mark.parametrize("size,label", [(LIMIT - 1024, "just under"),
                                        (LIMIT + 1024, "just over"),
                                        (LIMIT * 3, "well over")])
def test_a_missing_handoff_note_is_caught_in_a_long_final_message(tmp_path, size, label):
    """The one that mattered most: a verbose subagent with no note. The gate used to
    pass it, because the gate itself could no longer run `jq`."""
    p = lock(tmp_path)
    msg = "I have finished the work." + pad(size)
    r = run_hook("subagent-stop-check.sh",
                 {"cwd": str(p), "last_assistant_message": msg}, p)
    assert r.returncode == 2, (label, r.returncode, r.stderr[:200])


@pytest.mark.parametrize("size,label", [(LIMIT + 1024, "just over"),
                                        (LIMIT * 3, "well over")])
def test_a_present_handoff_note_is_accepted_in_a_long_final_message(tmp_path, size, label):
    """And the other direction, so the fix is not "block everything big"."""
    p = lock(tmp_path)
    msg = ("TASK M0-S1-DATA-007 — COMPLETE\nOUTPUTS:\n  - a.py\nTESTS: red=0 green=3\n"
           + pad(size))
    r = run_hook("subagent-stop-check.sh",
                 {"cwd": str(p), "last_assistant_message": msg}, p)
    assert r.returncode == 0, (label, r.returncode, r.stderr[:200])
