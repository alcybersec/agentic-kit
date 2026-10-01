# plugins/agentic-kit/kitgen/tests/test_render.py
import json
import re

from kitgen.render import render

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


# Grows as templates land: Task 5 adds the agent cards and memory stubs, Task 6
# settings.json, Task 7 the docs spine. Keeping it exact at every step means the
# suite is green at every task boundary instead of red until Task 7.
def expected_paths(cfg):
    paths = {
        "CLAUDE.md",
        ".claude/kit.yaml",
        ".claude/kit.lock.json",
        ".claude/agents/orchestrator.md",
    }
    for r in cfg.roles:
        paths.add(f".claude/agents/{r.name}.md")
        paths.add(f".claude/agent-memory/{r.name}/MEMORY.md")
    return paths


def test_manifest_has_exactly_the_expected_paths(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        assert set(render(cfg)) == expected_paths(cfg), name


def test_render_is_pure_and_deterministic(load_fixture):
    cfg = load_fixture("services_layout")
    assert render(cfg) == render(cfg)


def test_the_lock_is_written_after_the_yaml(load_fixture):
    """§5.1 reads a yaml newer than the lock as hand-edited drift, and the CLI
    writes in manifest insertion order -- so a clean render must emit yaml first."""
    paths = list(render(load_fixture("services_layout")))
    assert paths.index(".claude/kit.yaml") < paths.index(".claude/kit.lock.json")


def test_lock_is_valid_json_matching_the_config(load_fixture):
    cfg = load_fixture("python_monolith")
    lock = json.loads(render(cfg)[".claude/kit.lock.json"])
    assert lock["project"]["slug"] == "ledger"
    assert [r["name"] for r in lock["roles"]] == [r.name for r in cfg.roles]


def test_claude_md_agent_table_lists_every_role(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        body = render(cfg)["CLAUDE.md"]
        for r in cfg.roles:
            assert f"`{r.name}`" in body, (name, r.name)


def test_claude_md_names_only_the_chosen_forge(load_fixture):
    """The chosen CLI appears as the project's tool. The other CLI may appear ONLY
    inside the "do not propose" sentence -- naming it there is deliberate, and Task 6
    asserts the same intent in the deny rules. So test placement, not absence."""
    gl = render(load_fixture("services_layout"))["CLAUDE.md"]
    assert "`glab` for issues" in gl
    assert "GitHub Actions" in gl and "Do not propose" in gl
    assert "`glab` for issues" in gl.split("Do not propose")[0]

    gh = render(load_fixture("python_monolith"))["CLAUDE.md"]
    assert "`gh` for issues" in gh
    assert "GitLab CI" in gh and "`glab`" in gh.split("Do not propose")[1]

    none = render(load_fixture("greenfield_prd"))["CLAUDE.md"]
    assert "Forge:" not in none
    assert "glab" not in none and "`gh`" not in none


def test_templates_actually_ship_in_the_installed_package():
    """`uv run` installs editable, so Path(__file__)/templates always resolves in
    tests even if the wheel omitted the .j2 files. Assert through the package's
    resource API instead, which is what a non-editable consumer install exercises."""
    from importlib.resources import files
    shipped = {p.name for p in (files("kitgen") / "templates").iterdir()}
    assert "CLAUDE.md.j2" in shipped
    assert all(n.endswith(".j2") for n in shipped), shipped


def test_observability_false_omits_the_observability_rule(load_variant):
    """No fixture sets this false, so without a variant the branch never renders."""
    on = render(load_variant("services_layout", observability=True))["CLAUDE.md"]
    off = render(load_variant("services_layout", observability=False))["CLAUDE.md"]
    assert "Observability with the feature" in on
    assert "Observability with the feature" not in off


def test_not_exclusive_with_a_real_forge_omits_the_prohibition(load_variant):
    """exclusive: false only occurs on the kind: none fixture, so a real forge that
    is merely non-exclusive is otherwise untested -- and §6.3 requires it to block
    neither CLI."""
    cfg = load_variant("services_layout",
                       forge={**load_variant("services_layout").to_lock()["forge"],
                              "exclusive": False})
    body = render(cfg)["CLAUDE.md"]
    assert "Forge:" in body and "`glab` for issues" in body
    assert "Do not propose" not in body


def test_every_rendered_markdown_is_well_formed(load_fixture):
    """Generalises the CLAUDE.md checks to the whole manifest: a hard-wrapped table
    row breaks its table, a heading needs a blank line under it, and three newlines
    in a row means a template emitted a stray one."""
    for name in FIXTURES:
        for path, body in render(load_fixture(name)).items():
            if not path.endswith(".md"):
                continue
            assert "\n\n\n" not in body, (name, path, "stray blank line")
            lines = body.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("|"):
                    assert line.rstrip().endswith("|"), (name, path, i, line)
                if line.startswith("#") and i + 1 < len(lines):
                    assert lines[i + 1] == "", (name, path, i, "no blank line under heading")


def test_claude_md_has_every_section(load_fixture):
    """The template was once committed truncated — a third of it missing, including
    the whole dispatch loop — and every string-presence test still passed. Assert the
    document's shape, not just that some phrases occur in it."""
    always = [
        "## Your default role: Orchestrator",
        "## Session-start load order",
        "## How you operate",
        "## Commands",
        "## Task dispatch loop",
        "## What you never do",
        "## Kit",
    ]
    for name in FIXTURES:
        cfg = load_fixture(name)
        body = render(cfg)["CLAUDE.md"]
        for heading in always:
            assert heading in body, (name, heading)
        # the Forge section is conditional on there being a forge
        assert ("## Forge:" in body) == (cfg.forge.kind != "none"), name
        assert body.rstrip().endswith("after updating the plugin."), name


def test_claude_md_is_well_formed_markdown(load_fixture):
    """Two defects the string tests could not see: a table row hard-wrapped onto a
    second line (which breaks the table), and a paragraph placed directly under a
    numbered list (which Markdown absorbs into the last list item)."""
    for name in FIXTURES:
        lines = render(load_fixture(name))["CLAUDE.md"].splitlines()
        for i, line in enumerate(lines):
            if line.startswith("|"):
                assert line.rstrip().endswith("|"), (name, i, line)
        for i, line in enumerate(lines[:-1]):
            if re.match(r"^\d+\. ", line):
                nxt = lines[i + 1]
                assert (nxt == "" or re.match(r"^\d+\. ", nxt)
                        or nxt.startswith("   ")), (name, i, nxt)


def test_no_template_placeholder_survives_rendering(load_fixture):
    for name in FIXTURES:
        for path, body in render(load_fixture(name)).items():
            if path.endswith((".md", ".yaml")):
                assert "{{" not in body and "{%" not in body, (name, path)
