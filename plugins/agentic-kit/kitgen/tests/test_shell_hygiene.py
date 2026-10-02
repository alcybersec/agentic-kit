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
