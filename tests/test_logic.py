"""Logic unit tests (no network)."""
from ed_mcp.data import load_anaconda_cargo_build, load_constellations
from ed_mcp.logic.colonisation import dedupe_by_name, is_claimable_candidate
from ed_mcp.logic.outfitting import shopping_list_for_build, summarise_station_stock
from ed_mcp.logic.trade import (distance_ly, jumps_needed, match_market,
                                match_module, match_ship, summarise_bodies)
from ed_mcp.providers.journal import cargo_capacity_of_modules


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


def test_station_summarise_new_shape():
    payload = {"results": [{"name": "Shkaplerov Beacon", "system_name": "XF-O a6-6",
                             "distance": 11.2, "has_large_pad": True, "large_pads": 5,
                             "distance_to_arrival": 430.0,
                             "market_updated_at": "2026-10-02"}]}
    out = summarise_station_stock(payload)
    assert out[0]["system"] == "XF-O a6-6"
    assert out[0]["max_pad"] == "Lx5"


def test_cargo_capacity_sum():
    mods = [{"Item": "Int_CargoRack_Size6_Class1"}, {"Item": "Int_CargoRack_Size3_Class1"},
            {"Item": "Int_ShieldGenerator_Size6_Class2"}]
    assert cargo_capacity_of_modules(mods) == 72


def test_distance_and_jumps():
    assert distance_ly({"x": 0, "y": 0, "z": 0}, {"x": 3, "y": 4, "z": 0}) == 5.0
    assert jumps_needed(46.5, 23.25) == 2
    assert jumps_needed(0, 30) == 0


def test_match_market_buy_sell():
    results = [{"name": "A", "system_name": "S1", "distance": 5.0,
                "has_large_pad": True, "large_pads": 2, "type": "Orbis",
                "distance_to_arrival": 100.0, "market_updated_at": "t",
                "market": [{"commodity": "Aluminium", "supply": 100,
                             "demand": 0, "sell_price": 2000, "buy_price": 2100}]},
               {"name": "B", "system_name": "S2", "distance": 2.0,
                "has_large_pad": False, "market": [
                    {"commodity": "Aluminium", "supply": 50,
                     "demand": 0, "sell_price": 1900, "buy_price": 2000}]}]
    buys = match_market(results, "aluminium", mode="buy")
    assert buys[0]["station"] == "A"  # bigger supply first
    assert match_market(results, "aluminium", mode="buy",
                        large_pad_only=True) == [buys[0]]
    assert match_market(results, "aluminium", mode="sell") == []
    assert match_market(results, "gold", mode="buy") == []


def test_match_module_and_ship():
    results = [{"name": "A", "system_name": "S1", "distance": 3.0,
                "modules": [{"name": "Fuel Scoop", "ed_symbol": "Int_FuelScoop_Size6_Class5"}],
                "ships": [{"name": "Anaconda", "symbol": "Anaconda", "price": 1}]}]
    assert match_module(results, "fuelscoop")[0]["station"] == "A"
    assert match_module(results, "guardian")[0:0] == []
    assert match_ship(results, "anaconda")[0]["matches"][0]["name"] == "Anaconda"


def test_summarise_bodies():
    payload = [{"name": "Earth", "system_name": "Sol", "distance": 0.0,
                "sub_type": "Earth-like world", "earth_masses": 1.0,
                "estimated_value": 600000, "is_landable": False}]
    out = summarise_bodies(payload)
    assert out[0]["type"] == "Earth-like world"


def test_survey_rollup_grades():
    from ed_mcp.logic.survey import rollup_journal_scans, summarise_bodies_catalog
    evs = [
        {"event": "FSDJump", "StarSystem": "A", "SystemAddress": 1,
         "timestamp": "2026-01-01T00:00:00Z"},
        {"event": "FSSAllBodiesFound", "SystemName": "A", "SystemAddress": 1},
        {"event": "FSDJump", "StarSystem": "B", "SystemAddress": 2,
         "timestamp": "2026-01-02T00:00:00Z"},
        {"event": "FSSDiscoveryScan", "SystemName": "B", "SystemAddress": 2,
         "Progress": 0.5, "BodyCount": 10},
        {"event": "Scan", "StarSystem": "B", "SystemAddress": 2,
         "WasDiscovered": False},
        {"event": "FSDJump", "StarSystem": "C", "SystemAddress": 3,
         "timestamp": "2026-01-03T00:00:00Z"},
    ]
    rows = rollup_journal_scans(evs)
    assert rows["1"]["grade"] == "COMPLETE"
    assert rows["2"]["grade"] == "PARTIAL"
    assert rows["2"]["first_discoveries"] == 1
    assert rows["3"]["grade"] == "VISITED"
    cat = summarise_bodies_catalog([{"subType": "Earth-like world", "isLandable": True},
                                    {"type": "Star"}])
    assert cat["catalogued"] == 2 and cat["landable"] == 1