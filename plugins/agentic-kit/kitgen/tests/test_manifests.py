import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_marketplace_lists_the_plugin():
    mp = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
    assert mp["name"] == "agentic-kit"
    names = [p["name"] for p in mp["plugins"]]
    assert names == ["agentic-kit"]
    assert mp["plugins"][0]["source"] == "./plugins/agentic-kit"


def test_plugin_manifest_is_valid():
    pj = json.loads(
        (REPO / "plugins/agentic-kit/.claude-plugin/plugin.json").read_text()
    )
    assert pj["name"] == "agentic-kit"
    assert pj["description"]
