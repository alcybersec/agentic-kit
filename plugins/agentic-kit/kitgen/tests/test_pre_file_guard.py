# plugins/agentic-kit/kitgen/tests/test_pre_file_guard.py
import json
import os

import pytest

from .hooks_conftest import file_payload, run_hook

HOOK = "pre-file-guard.sh"


def make_project(tmp_path, secrets):
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps({
        "secrets": secrets,
        "forge": {"kind": "none", "cli": "none", "exclusive": False,
                  "mirror": None, "remote": None, "ci": None},
        "attribution": {"mention_assistant_in_commits": True},
        "toolchain": {"format": "ruff format"},
    }))
    return tmp_path


def blocked(p, tool, path):
    return run_hook(HOOK, file_payload(tool, path, p), p).returncode == 2


@pytest.mark.parametrize("tool", ["Read", "Edit", "Write", "NotebookEdit"])
def test_a_secret_file_is_blocked_for_every_tool(tmp_path, tool):
    p = make_project(tmp_path, ["./.env", "./secrets/**"])
    r = run_hook(HOOK, file_payload(tool, str(p / ".env"), p), p)
    assert r.returncode == 2
    assert ".env" in r.stderr


def test_a_glob_secret_matches_nested_paths(tmp_path):
    p = make_project(tmp_path, ["./secrets/**"])
    r = run_hook(HOOK, file_payload("Read", str(p / "secrets/db/pw.txt"), p), p)
    assert r.returncode == 2


def test_an_ordinary_file_is_allowed(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    r = run_hook(HOOK, file_payload("Edit", str(p / "src/app.py"), p), p)
    assert r.returncode == 0


def test_a_relative_path_is_matched_too(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    assert blocked(p, "Read", ".env")
    assert blocked(p, "Read", "./.env")


def test_a_lookalike_name_is_not_blocked(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    for safe in [".env.example", ".env.local", "env", "a.env", "sub/.env",
                 "docs/env.md", "src/environment.py", "README.md"]:
        r = run_hook(HOOK, file_payload("Read", str(p / safe), p), p)
        assert r.returncode == 0, safe


def test_glob_boundaries(tmp_path):
    p = make_project(tmp_path, ["./secrets/**"])
    for safe in ["secrets", "secretsfile", "secrets.md", "src/secrets/x"]:
        assert not blocked(p, "Read", str(p / safe)), safe
    assert blocked(p, "Read", str(p / "secrets/a"))


def test_dot_dot_segments_are_normalised(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    assert blocked(p, "Read", str(p / "src/../.env"))
    assert blocked(p, "Read", "src/../.env")
    assert not blocked(p, "Read", str(p / "src/../.env.example"))


def test_a_path_that_escapes_and_returns_is_still_inside(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    assert blocked(p, "Read", f"{p}/../{p.name}/.env")


def test_a_path_outside_the_project_is_not_policed(tmp_path):
    p = make_project(tmp_path / "proj", ["./.env", "./secrets/**"])
    assert not blocked(p, "Read", str(tmp_path / ".env"))
    assert not blocked(p, "Read", "/etc/hostname")
    assert not blocked(p, "Read", str(p / "../.env"))
    # a sibling sharing the root's name as a prefix is outside too
    assert not blocked(p, "Read", str(p) + "-other/.env")


def test_a_symlink_to_a_secret_is_caught_by_its_target(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    (p / ".env").write_text("TOKEN=x")
    os.symlink(p / ".env", p / "innocent.txt")
    assert blocked(p, "Read", str(p / "innocent.txt"))


def test_a_symlink_named_like_a_secret_is_caught_by_its_name(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    (p / "real.txt").write_text("x")
    os.symlink(p / "real.txt", p / ".env")
    assert blocked(p, "Read", str(p / ".env"))


def test_a_relative_path_resolves_against_cwd_not_root(tmp_path):
    p = make_project(tmp_path, ["./.env", "./secrets/**"])
    (p / "secrets").mkdir()
    payload = file_payload("Read", "pw.txt", p / "secrets")
    assert run_hook(HOOK, payload, p).returncode == 2
    payload = file_payload("Read", ".env", p / "sub")
    assert run_hook(HOOK, payload, p).returncode == 0  # sub/.env, not ./.env


def test_spaces_and_newlines_in_paths(tmp_path):
    p = make_project(tmp_path, ["./my secrets/**", "./.env"])
    assert blocked(p, "Read", str(p / "my secrets/a b.txt"))
    assert not blocked(p, "Read", str(p / "my secrets"))
    assert not blocked(p, "Read", str(p / "x\n.env"))
    assert not blocked(p, "Read", str(p / "a\nb/ok.txt"))


def test_the_message_names_the_pattern_and_the_alternative(tmp_path):
    p = make_project(tmp_path, ["./secrets/**"])
    r = run_hook(HOOK, file_payload("Read", str(p / "secrets/x"), p), p)
    msg = r.stderr
    assert "./secrets/**" in msg and "secrets/x" in msg
    assert ".example" in msg


def test_no_file_path_in_the_payload_is_allowed(tmp_path):
    p = make_project(tmp_path, ["./.env"])
    r = run_hook(HOOK, {"tool_name": "Read", "tool_input": {}, "cwd": str(p)}, p)
    assert r.returncode == 0


def test_an_empty_or_missing_secrets_list_blocks_nothing(tmp_path):
    p = make_project(tmp_path, [])
    assert not blocked(p, "Read", str(p / ".env"))
    (p / ".claude/kit.lock.json").write_text("{}")
    assert not blocked(p, "Read", str(p / ".env"))
