from pathlib import Path

import pytest
import yaml

from kitgen.model import KitConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> KitConfig:
        raw = yaml.safe_load((FIXTURE_DIR / name / "profile.yaml").read_text())
        return KitConfig.from_dict(raw)
    return _load


@pytest.fixture
def load_variant():
    """Load a fixture profile with top-level keys overridden, re-validating it.

    Used for the two branches no fixture reaches (§Task 3 coverage gap). Goes back
    through KitConfig.from_dict rather than dataclasses.replace, so a variant is a
    genuinely valid profile and not one that skipped validation.
    """
    def _load(name: str, **overrides) -> KitConfig:
        raw = yaml.safe_load((FIXTURE_DIR / name / "profile.yaml").read_text())
        raw.update(overrides)
        return KitConfig.from_dict(raw)
    return _load
