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
