from kitgen.model import KitConfig

FIXTURES = ["greenfield_prd", "python_monolith", "services_layout"]


def test_every_fixture_is_a_valid_profile(load_fixture):
    for name in FIXTURES:
        cfg = load_fixture(name)
        assert isinstance(cfg, KitConfig)
        assert cfg.veto_role


def test_fixtures_cover_all_three_forge_kinds(load_fixture):
    kinds = {load_fixture(n).forge.kind for n in FIXTURES}
    assert kinds == {"gitlab", "github", "none"}


def test_no_fixture_gives_one_role_the_whole_test_tree(load_fixture):
    """§8.4: a broad `tests/**` blocks every other role from writing a test, while
    the kit mandates test-first for logic. `services_layout` shipped exactly that
    anti-pattern — so the one roster a user is most likely to copy from locked four
    service roles out of their own tests, and left the veto role's floor tier with
    nowhere conventional to live.

    These are reference rosters. An anti-pattern here propagates by being copied."""
    for name in ("greenfield_prd", "python_monolith", "services_layout"):
        cfg = load_fixture(name)
        for role in cfg.roles:
            for glob in role.owns:
                assert glob not in ("tests", "tests/**", "tests/*"), (
                    f"{name}: role {role.name!r} owns {glob!r}, which blocks every "
                    f"other role from writing any test")


def test_the_shipped_example_profile_is_valid_and_renders():
    """An example that has gone stale is worse than none: it is the first thing anyone
    copies. This loads it through the real validator and renders it, so a schema change
    that invalidates it breaks the build rather than someone's afternoon."""
    import yaml
    from pathlib import Path
    from kitgen.model import KitConfig
    from kitgen.render import render
    from kitgen.verify import advise, verify
    example = Path(__file__).resolve().parents[2] / "examples/kit.yaml"
    cfg = KitConfig.from_dict(yaml.safe_load(example.read_text()))
    man = render(cfg)
    assert verify(man, cfg) == []
    assert advise(man, cfg) == [], "the example must not model something it warns about"
    # It exists to be read, so the comments that carry the reasoning must survive.
    text = example.read_text()
    for lesson in ("must take ONE file", "crosses nobody's boundary", "is refused",
                   "exactly one role carries the veto", 'MUST start with "./"'):
        assert lesson in text, lesson


def test_the_example_profile_matches_the_plugin_version():
    """`kit_version` in the example is what a reader will copy, and /kit-doctor notes a
    profile pinned behind the plugin — so a stale example manufactures that note."""
    import json, yaml
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    example = yaml.safe_load((root / "examples/kit.yaml").read_text())
    plugin = json.loads((root / ".claude-plugin/plugin.json").read_text())
    assert example["kit_version"] == plugin["version"]
