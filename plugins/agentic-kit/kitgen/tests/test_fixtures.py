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
