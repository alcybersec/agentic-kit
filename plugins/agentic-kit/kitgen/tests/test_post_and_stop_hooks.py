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


# --- harness payload: stop_hook_active, agent_transcript_path, last_assistant_message ---

def stop_payload(p, tmp_name="x", **fields):
    return run_hook("subagent-stop-check.sh", {"cwd": str(p), **fields}, p)


def write_t(p, name, text):
    f = p / name
    f.write_text(json.dumps(asst(text)) + "\n")
    return str(f)


def test_stop_hook_active_exits_zero_with_no_note_anywhere(tmp_path):
    p = make_project(tmp_path)
    t = write_t(p, "a.jsonl", "nothing here")
    r = stop_payload(p, stop_hook_active=True, agent_transcript_path=t,
                     last_assistant_message="nothing here")
    assert r.returncode == 0 and r.stderr == ""
    # and it is the flag doing it, not the absence of evidence
    assert stop_payload(p, stop_hook_active=False, last_assistant_message="x").returncode == 2


def test_agent_transcript_with_note_passes(tmp_path):
    p = make_project(tmp_path)
    t = write_t(p, "a.jsonl", NOTE)
    assert stop_payload(p, agent_transcript_path=t).returncode == 0


def test_subagent_transcript_without_note_blocks_even_if_parent_has_one(tmp_path):
    """The false negative: the orchestrator's transcript mentions a note, the subagent's does not."""
    p = make_project(tmp_path)
    sub = write_t(p, "sub.jsonl", "all done, trust me")
    parent = write_t(p, "parent.jsonl", NOTE)
    r = stop_payload(p, agent_transcript_path=sub, transcript_path=parent)
    assert r.returncode == 2


def test_parent_transcript_is_only_a_fallback(tmp_path):
    p = make_project(tmp_path)
    assert stop_payload(p, transcript_path=write_t(p, "p.jsonl", NOTE)).returncode == 0
    assert stop_payload(p, transcript_path=write_t(p, "q.jsonl", "no")).returncode == 2
    # agent path set but unreadable -> falls back to the parent's
    assert stop_payload(p, agent_transcript_path=str(p / "gone"),
                        transcript_path=write_t(p, "r.jsonl", NOTE)).returncode == 0


def test_either_source_satisfies_the_check(tmp_path):
    p = make_project(tmp_path)
    with_note = write_t(p, "n.jsonl", NOTE)
    no_note = write_t(p, "e.jsonl", "no")
    # note earlier, closing remark last: passes (was a false positive when the message was primary)
    assert stop_payload(p, last_assistant_message="Done.",
                        agent_transcript_path=with_note).returncode == 0
    # note in the last message, none in the transcript
    assert stop_payload(p, last_assistant_message="wrap up\n\n" + NOTE,
                        agent_transcript_path=no_note).returncode == 0
    # no note in either source
    assert stop_payload(p, last_assistant_message="Done.",
                        agent_transcript_path=no_note).returncode == 2
    # message only, no note
    assert stop_payload(p, last_assistant_message="Done.").returncode == 2
    # empty message falls through to the transcript
    assert stop_payload(p, last_assistant_message="",
                        agent_transcript_path=with_note).returncode == 0
    assert stop_payload(p, last_assistant_message="",
                        agent_transcript_path=no_note).returncode == 2


def test_false_negative_still_blocks_with_a_closing_message(tmp_path):
    """Parent has a note, subagent does not: still 2 whatever the last message says."""
    p = make_project(tmp_path)
    sub = write_t(p, "sub.jsonl", "all done")
    parent = write_t(p, "parent.jsonl", NOTE)
    assert stop_payload(p, last_assistant_message="Done.",
                        agent_transcript_path=sub, transcript_path=parent).returncode == 2


def test_documented_limit_a_quoted_note_on_its_own_line_passes(tmp_path):
    """Undecidable from text alone; accepted. Pinned so closing it is a decision."""
    p = make_project(tmp_path)
    msg = "The format looks like this:\nTASK M0-1 — COMPLETE\nOUTPUTS: ..."
    assert stop_payload(p, last_assistant_message=msg).returncode == 0


@pytest.mark.parametrize("fields", [
    {"stop_hook_active": True},
    {"last_assistant_message": "no note"},
    {"agent_transcript_path": "/nope", "transcript_path": "/nope"},
])
def test_stop_check_is_inert_with_no_lock_whatever_fields_are_present(tmp_path, fields):
    r = run_hook("subagent-stop-check.sh", {"cwd": str(tmp_path), **fields}, tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_format_hook_passes_the_edited_file_as_the_only_argument(tmp_path):
    """The hook appends the edited file to `toolchain.format`.

    A command carrying its own target would therefore format that target as well
    -- `black . <file>` rewrites the whole tree from a PostToolUse hook that no
    ownership matcher covers. `model.py` rejects such a command; this pins the
    other half of the contract: the hook adds exactly one argument, and the
    formatter sees nothing else.
    """
    argv = tmp_path / "argv"
    stub = tmp_path / "stub.sh"
    stub.write_text(f'for a in "$@"; do echo "$a"; done > "{argv}"\n')
    p = make_project(tmp_path, fmt=f"sh {stub}")
    r = run_hook("post-edit-format.sh",
                 file_payload("Edit", str(p / "src/a.py"), p), p)
    assert r.returncode == 0
    assert argv.read_text().split() == [str(p / "src/a.py")]
