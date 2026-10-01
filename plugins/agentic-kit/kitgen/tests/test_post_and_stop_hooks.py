import json

import pytest

from .hooks_conftest import file_payload, run_hook


def make_project(tmp_path, fmt="true", handoff_required=True):
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/kit.lock.json").write_text(json.dumps({
        "secrets": [],
        "forge": {"kind": "none", "cli": "none", "exclusive": False,
                  "mirror": None, "remote": None, "ci": None},
        "attribution": {"mention_assistant_in_commits": True},
        "toolchain": {"format": fmt},
        "roles": [{"name": "data", "handoff_extra": ["MIGRATION:"]}],
    }))
    return tmp_path


def stop(p, lines):
    t = p / "t.jsonl"
    t.write_text("".join(
        (l if isinstance(l, str) else json.dumps(l)) + "\n" for l in lines))
    return run_hook("subagent-stop-check.sh",
                    {"transcript_path": str(t), "cwd": str(p)}, p)


def asst(text):
    return {"role": "assistant", "content": text}


NOTE = "TASK M0-S1-ARCH-001 — COMPLETE\nOUTPUTS:\n  - docs/x.md\nTESTS: red=0 green=4\n"


def test_format_hook_runs_the_configured_formatter(tmp_path):
    marker = tmp_path / "ran"
    p = make_project(tmp_path, fmt=f"touch {marker} --")
    r = run_hook("post-edit-format.sh",
                 file_payload("Edit", str(p / "src/a.py"), p), p)
    assert r.returncode == 0
    assert marker.exists()


def test_format_hook_never_blocks_when_the_formatter_fails(tmp_path):
    p = make_project(tmp_path, fmt="false")
    r = run_hook("post-edit-format.sh",
                 file_payload("Edit", str(p / "src/a.py"), p), p)
    assert r.returncode == 0


@pytest.mark.parametrize("fmt", [
    "false",
    "/nonexistent/formatter",
    "",
    "sh -c 'echo boom >&2; exit 3' --",
    "*",
])
def test_format_hook_exits_zero_and_silent_whatever_the_formatter_does(tmp_path, fmt):
    p = make_project(tmp_path, fmt=fmt)
    r = run_hook("post-edit-format.sh",
                 file_payload("Edit", str(p / "src/a.py"), p), p)
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""


def test_format_hook_skips_non_source_files(tmp_path):
    marker = tmp_path / "ran"
    p = make_project(tmp_path, fmt=f"touch {marker} --")
    run_hook("post-edit-format.sh",
             file_payload("Write", str(p / "docs/notes.md"), p), p)
    assert not marker.exists()


def test_stop_check_blocks_a_transcript_with_no_handoff(tmp_path):
    p = make_project(tmp_path)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps(
        {"role": "assistant", "content": "Done, looks good."}) + "\n")
    r = run_hook("subagent-stop-check.sh",
                 {"transcript_path": str(transcript), "cwd": str(p)}, p)
    assert r.returncode == 2
    assert "handoff" in r.stderr.lower()


def test_stop_check_accepts_a_transcript_containing_a_handoff(tmp_path):
    p = make_project(tmp_path)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({
        "role": "assistant",
        "content": "TASK M0-S1-ARCH-001 — COMPLETE\nOUTPUTS:\n  - docs/x.md\n"
                   "TESTS: red=0 green=4\n",
    }) + "\n")
    r = run_hook("subagent-stop-check.sh",
                 {"transcript_path": str(transcript), "cwd": str(p)}, p)
    assert r.returncode == 0


def test_stop_check_is_inert_without_a_transcript(tmp_path):
    p = make_project(tmp_path)
    r = run_hook("subagent-stop-check.sh", {"cwd": str(p)}, p)
    assert r.returncode == 0


@pytest.mark.parametrize("status", ["COMPLETE", "PARTIAL", "BLOCKED"])
def test_stop_check_accepts_every_status(tmp_path, status):
    p = make_project(tmp_path)
    assert stop(p, [asst(NOTE.replace("COMPLETE", status))]).returncode == 0


def test_stop_check_rejects_an_unknown_status(tmp_path):
    p = make_project(tmp_path)
    assert stop(p, [asst(NOTE.replace("COMPLETE", "DONE"))]).returncode == 2


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_stop_check_accepts_hyphen_en_dash_and_em_dash(tmp_path, dash):
    p = make_project(tmp_path)
    assert stop(p, [asst(NOTE.replace("—", dash))]).returncode == 0


def test_stop_check_accepts_blocks_content_and_ignores_tool_input(tmp_path):
    p = make_project(tmp_path)
    ok = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "wrapping up\n\n" + NOTE}]}}
    assert stop(p, [ok]).returncode == 0
    # A note typed into a file via a tool call is not an emitted note.
    wrote = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Write",
         "input": {"file_path": "n.md", "content": NOTE}}]}}
    assert stop(p, [wrote]).returncode == 2


def test_stop_check_ignores_the_dispatch_prompt(tmp_path):
    p = make_project(tmp_path)
    prompt = {"role": "user", "content": NOTE}
    assert stop(p, [prompt, asst("done")]).returncode == 2


def test_stop_check_rejects_the_format_explained_not_emitted(tmp_path):
    p = make_project(tmp_path)
    r = stop(p, [asst("The format is `TASK <ID> — COMPLETE` then OUTPUTS.")])
    assert r.returncode == 2
    r = stop(p, [asst("I will end with: TASK M0-1 — COMPLETE when done.")])
    assert r.returncode == 2


def test_stop_check_accepts_a_note_inside_a_code_fence(tmp_path):
    p = make_project(tmp_path)
    assert stop(p, [asst("```\n" + NOTE + "```")]).returncode == 0


def test_stop_check_handles_a_non_jsonl_transcript(tmp_path):
    p = make_project(tmp_path)
    assert stop(p, ["not json at all", "TASK A-1 — BLOCKED"]).returncode == 0
    assert stop(p, ["not json at all"]).returncode == 2


def test_stop_check_empty_or_missing_transcript_is_inert_or_blocks(tmp_path):
    p = make_project(tmp_path)
    assert stop(p, []).returncode == 2
    r = run_hook("subagent-stop-check.sh",
                 {"transcript_path": str(p / "nope.jsonl"), "cwd": str(p)}, p)
    assert r.returncode == 0


def test_stop_check_deny_message_says_what_to_emit(tmp_path):
    p = make_project(tmp_path)
    msg = json.loads(stop(p, [asst("done")]).stderr)["systemMessage"]
    for word in ("/handoff", "TASK", "COMPLETE", "OUTPUTS", "TESTS"):
        assert word in msg
