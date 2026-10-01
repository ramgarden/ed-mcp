"""Static reference data bundled with ed-mcp."""
from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).parent


def load_constellations() -> dict:
    with open(_HERE / "constellations.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_anaconda_cargo_build() -> dict:
    with open(_HERE / "anaconda_max_cargo.json", encoding="utf-8") as fh:
        return json.load(fh)
