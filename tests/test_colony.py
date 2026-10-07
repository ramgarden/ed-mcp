"""Tests for colony scoreboard, module acquisition flags, station slimming."""
from ed_mcp.logic.colonisation import summarise_depot
from ed_mcp.logic.trade import match_module, slim_station


def _depot():
    return {
        "timestamp": "2026-10-06T19:36:56Z",
        "event": "ColonisationConstructionDepot",
        "ConstructionProgress": 0.033707,
        "ConstructionComplete": False,
        "ConstructionFailed": False,
        "ResourcesRequired": [
            {"Name": "$steel_name;", "Name_Localised": "Steel",
             "RequiredAmount": 6660, "ProvidedAmount": 368, "Payment": 5057},
            {"Name": "$semiconductors_name;", "Name_Localised": "Semiconductors",
             "RequiredAmount": 68, "ProvidedAmount": 68, "Payment": 1526},
            {"Name": "$cmmcomposite_name;", "Name_Localised": "CMM Composite",
             "RequiredAmount": 4508, "ProvidedAmount": 0, "Payment": 6788},
        ],
    }


def test_summarise_depot_totals_and_order():
    board = summarise_depot(_depot())
    assert board["total_required"] == 6660 + 68 + 4508
    assert board["total_provided"] == 368 + 68
    assert board["lines_complete"] == 1
    assert board["complete"] is False
    # least-complete first: CMM (0%) before Steel (5.5%) before Semis (100%)
    names = [r["commodity"] for r in board["resources"]]
    assert names == ["CMM Composite", "Steel", "Semiconductors"]
    steel = next(r for r in board["resources"] if r["commodity"] == "Steel")
    assert steel["remaining"] == 6660 - 368


def test_match_module_acquisition_flags():
    results = [{
        "name": "Oshii Town", "system_name": "R CrA Sector UE-Y b1-2",
        "distance": 19.0, "large_pads": 4, "outfitting_updated_at": "x",
        "modules": [
            {"category": "standard", "class": 6,
             "ed_symbol": "Int_PowerDistributor_Size6_Class5",
             "name": "Power Distributor", "price": 3475690, "rating": "A"},
            {"category": "mercgear", "class": 6,
             "ed_symbol": "Int_PowerDistributor_Size6_Class5",
             "name": "Support Focused Power Distributor",
             "price": 3475690, "rating": "A"},
        ],
    }]
    hits = match_module(results, "power distributor")
    assert len(hits) == 1
    assert hits[0]["match_count"] == 2
    assert hits[0]["has_special_acquisition"] is True
    acqs = {h["acquisition"] for h in hits[0]["matches"]}
    assert acqs == {"credits", "special"}
    # standard_only drops the mercgear entry
    hits_std = match_module(results, "power distributor", standard_only=True)
    assert hits_std[0]["match_count"] == 1
    assert hits_std[0]["has_special_acquisition"] is False


def test_slim_station_flags_colonisation_and_pads():
    rec = {
        "name": "Birdseye Horizons", "system_name": "Kaus Media",
        "type": "Outpost", "distance": 4.9, "distance_to_arrival": 100,
        "large_pads": 0, "has_large_pad": False, "is_planetary": False,
        "has_market": True, "has_outfitting": False, "has_shipyard": False,
        "services": [{"name": "Dock"}, {"name": "System Colonisation"}],
        "system_population": 383943, "updated_at": "t", "market_updated_at": "m",
        "outfitting_updated_at": None,
    }
    slim = slim_station(rec)
    assert slim["system"] == "Kaus Media"  # full name preserved for paste
    assert slim["has_colonisation_contact"] is True
    assert slim["has_large_pad"] is False
    assert slim["services"] == ["Dock", "System Colonisation"]
