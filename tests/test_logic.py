"""Logic unit tests (no network)."""
from ed_mcp.data import load_anaconda_cargo_build, load_constellations
from ed_mcp.logic.colonisation import dedupe_by_name, is_claimable_candidate
from ed_mcp.logic.outfitting import shopping_list_for_build, summarise_station_stock


def test_claimable_empty_system():
    ok, reasons = is_claimable_candidate({"information": {"population": 0},
                                          "stations": []})
    assert ok and "zero population" in reasons


def test_claimable_populated_rejected():
    ok, _ = is_claimable_candidate({"information": {"population": 1000,
                                                    "faction": "Pilots"},
                                    "stations": [{"name": "X"}]})
    assert not ok


def test_dedupe():
    systems = [{"name": "Sol"}, {"name": "sol"}, {"name": "Alpha"}]
    assert len(dedupe_by_name(systems)) == 2


def test_teapot_data_has_anchors():
    data = load_constellations()
    assert len(data["teapot"]["stars"]) >= 5


def test_anaconda_build_and_list():
    build = load_anaconda_cargo_build()
    items = shopping_list_for_build(build, owned_items={"hpt_beamlaser_fixed_medium"})
    assert len(items) == len(build["build"])
    assert all("want" in i for i in items)


def test_station_summarise():
    payload = {"results": [{"name": "Daedalus", "system": {"name": "Sol"},
                             "distance": 5.0, "has_outfitting": True}]}
    out = summarise_station_stock(payload)
    assert out[0]["station"] == "Daedalus"
