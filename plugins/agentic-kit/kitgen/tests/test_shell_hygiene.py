# plugins/agentic-kit/kitgen/tests/test_shell_hygiene.py
"""Patterns that are wrong in every shipped script, checked once for all of them.

`printf ... | grep -q` under `set -o pipefail` is a race: `grep -q` exits on the
first match, a writer that has not finished dies of SIGPIPE, and `pipefail` turns
that into a failed pipeline. It cost this kit a gate that blocked finished tasks
~1.5% of the time and an attribution check that let a line through at about the
same rate — in opposite directions, from one idiom. A behavioural test catches it
only where someone thought to write one, so this is grep.
"""
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
SCRIPTS = sorted([*(PLUGIN / "hooks").rglob("*.sh"), *(PLUGIN / "bin").rglob("*.sh")])
# Every shipped script, the ownership guard included: it moved out of a Jinja template
# into hooks/ on 2026-10-02, so the glob covers it and there is no template to special-case.
ALL_SHELL = SCRIPTS

assert SCRIPTS, "no shell scripts found — the glob is wrong, not the tree"


@pytest.mark.parametrize("path", ALL_SHELL, ids=lambda p: p.name)
def test_no_short_circuiting_consumer_on_the_right_of_a_pipe(path):
    """`grep -q`, `head -n` and `grep -m` all close the pipe early. Use a
    herestring (`<<<`) or give the consumer the file directly."""
    body = path.read_text()
    if "pipefail" not in body:
        pytest.skip("no pipefail, so a SIGPIPE does not become a failed pipeline")
    for n, line in enumerate(body.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        # `bash <script>` belongs here too: a guard that refuses exits without
        # draining stdin, so the writer takes a SIGPIPE and the pipeline reports 141
        # instead of the guard's own exit code.
        if re.search(r"\|\s*(\w+=\S+\s+)*(grep\s+(-\w*q|-m\s*\d)|head\b|bash\b)", line):
            pytest.fail(f"{path.name}:{n}: short-circuiting consumer after a pipe "
                        f"under pipefail — use a herestring: {line.strip()}")


@pytest.mark.parametrize("path", ALL_SHELL, ids=lambda p: p.name)
def test_every_shipped_script_parses(path):
    import subprocess
    r = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("path", ALL_SHELL, ids=lambda p: p.name)
def test_the_raw_payload_is_never_exported(path):
    """An exported variable is copied into every child's environment, and Linux caps
    a single environment string at 131072 bytes. Exporting the hook payload made
    every `jq` fail with E2BIG past that size, so the hook read nothing and allowed
    everything. Whatever holds stdin stays a plain shell variable."""
    body = path.read_text()
    holders = set(re.findall(r"^\s*(\w+)=\$\(cat\b", body, re.M))
    for var in holders:
        assert not re.search(rf"^\s*export\b[^\n]*\b{var}\b", body, re.M), (
            f"{path.name}: {var} holds the raw payload and must not be exported")


HOT_PATH = [p for p in SCRIPTS if p.parent.name == "hooks"]


@pytest.mark.parametrize("path", HOT_PATH, ids=lambda p: p.name)
def test_a_hook_asks_jq_at_most_twice(path):
    """A performance property, invisible in behaviour and easy to lose.

    These run on the hot path of every tool call and a jq process costs ~20 ms here.
    Each hook has at most two things to ask — one pass over the payload, one over the
    lock — and asking per-question instead cost 308 ms per edit in the ownership guard
    and 193 ms per Bash call in the bash guard. `kit_q`/`kit_in` are one process per
    call, so they are banned here too; `kit_read_nul` with a single `jq -j` replaces them.

    kit_init's own two calls are in the library and are not counted: they are the
    correctness gate every hook shares.
    """
    body = path.read_text()
    code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    n = code.count("jq -")
    assert n <= 2, f"{path.name}: {n} jq invocations; one pass for the payload, one for the lock"
    for helper in ("kit_q ", "kit_in "):
        assert helper not in code, (
            f"{path.name}: {helper.strip()} is one jq process per call — read what you "
            f"need in a single kit_read_nul pass instead")


@pytest.mark.parametrize("path", HOT_PATH, ids=lambda p: p.name)
def test_a_hook_reads_nul_delimited_fields_not_lines(path):
    """`kit_read_nul` exists because the values are not newline-free: `$cmd` is a whole
    command line and a `git commit -m` message spans lines. The first single-pass version
    read line by line, truncated the command at the first newline, and silently stopped
    enforcing the attribution rule."""
    code = path.read_text()
    if "kit_read_nul" not in code:
        pytest.skip("no single-pass read in this hook")
    assert "jq -j" in code, "kit_read_nul needs `jq -j` emitting NUL after each field"
    assert '"\\u0000"' in code or '"\u0000"' in code, "fields must be NUL-delimited"


@pytest.mark.parametrize("path", ALL_SHELL, ids=lambda p: p.name)
def test_stderr_is_silenced_before_an_output_redirect_not_after(path):
    """`cmd > "$f" 2>/dev/null` does NOT silence the failure of `> "$f"`.

    Bash applies redirections left to right, so when `$f` is unwritable the failure is
    reported while stderr is still the real one and bash prints "No such file or
    directory" to it. In kit-usage-probe.sh that stderr was the status line the probe
    rides on: any unwritable snapshot path put a line of shell error text into it.
    `2>/dev/null` first leaves the failed redirect nowhere to complain, and the `if`
    still sees the non-zero status.

    Found on 2026-10-04 by a test for an unrelated bug, which is the only reason anyone
    looked: the leak needs an unwritable target, and the happy path never has one.
    """
    body = path.read_text()
    for n, line in enumerate(body.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if re.search(r'>>?\s*"?\$\{?\w[^"\s]*"?\s+2>\s*/dev/null', line):
            pytest.fail(f"{path.name}:{n}: stderr is silenced AFTER the output redirect, "
                        f"so a failing redirect still prints. Put `2>/dev/null` first: "
                        f"{line.strip()}")


def test_shellcheck_is_clean_across_every_shipped_script():
    """One run over all of them, because shellcheck's cross-file view is the point:
    `-x` follows the `source lib/kitlock.sh` so a helper's variables are not reported
    as undefined in each caller.

    It found a dead `strategy` read in session-start.sh that no behavioural test could
    see — the value was parsed out of the lock and never used. Dead fields are worse
    than untidy here: `kit_read_nul` assigns positionally, so one in the middle of the
    list is a loaded gun for the next person who adds a field.

    Skipped where shellcheck is not installed, which means a machine without it gets no
    coverage from this test at all. The CI image has it.
    """
    import shutil
    import subprocess

    exe = shutil.which("shellcheck")
    if exe is None:
        pytest.skip("shellcheck not installed")
    r = subprocess.run([exe, "-x", "-S", "warning", *map(str, ALL_SHELL)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout or r.stderr
