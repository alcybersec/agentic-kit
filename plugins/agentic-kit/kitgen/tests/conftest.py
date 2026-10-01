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
