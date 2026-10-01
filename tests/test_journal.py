"""Journal provider tests with synthetic journal files."""
import json
from pathlib import Path

from ed_mcp.providers import journal as j


def _write_journal(tmp_path: Path):
    events = [
        {"timestamp": "2026-01-01T00:00:00Z", "event": "LoadGame",
         "Commander": "TestCmdr", "Ship": "Anaconda", "Credits": 123456},
        {"timestamp": "2026-01-01T01:00:00Z", "event": "Location",
         "StarSystem": "Sol", "SystemAddress": 10477373803,
         "StarPos": [0.0, 0.0, 0.0], "StationName": "Daedalus",
         "StationType": "Orbis"},
        {"timestamp": "2026-01-01T02:00:00Z", "event": "Loadout",
         "Ship": "Anaconda", "ShipName": "Hauly", "Modules": [
             {"Slot": "Slot01", "Item": "hpt_beamlaser_fixed_medium", "On": True}]},
    ]
    p = tmp_path / "Journal.2026-01-01.log"
    with open(p, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
    return tmp_path


def test_status_location_loadout(tmp_path):
    d = _write_journal(tmp_path)
    st = j.get_status(d)
    assert st["found"] and st["commander"] == "TestCmdr" and st["system"] == "Sol"
    loc = j.get_location(d)
    assert loc["found"] and loc["system"] == "Sol" and loc["star_pos"] == [0.0, 0.0, 0.0]
    lo = j.get_loadout(d)
    assert lo["found"] and lo["ship"] == "Anaconda" and len(lo["modules"]) == 1
    hist = j.get_history(limit=5, journal_dir=d)
    assert hist["found"] and hist["count"] >= 3


def test_missing_dir(tmp_path):
    missing = tmp_path / "nope"
    assert j.get_status(missing)["found"] is False
    assert j.get_location(missing)["found"] is False
