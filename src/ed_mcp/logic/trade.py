"""Trader/explorer logic over Spansh payloads + EDSM coords.

All functions are pure (no network) so they stay unit-testable; the MCP
tools in server.py fetch live payloads and call these to shortlist.
"""
from __future__ import annotations

import math
from typing import Any


def distance_ly(a: dict[str, Any] | list | tuple,
                b: dict[str, Any] | list | tuple) -> float:
    """Euclidean distance between two {x,y,z} coord sets."""
    def xyz(v: Any) -> tuple[float, float, float]:
        if isinstance(v, dict):
            return float(v["x"]), float(v["y"]), float(v["z"])
        return float(v[0]), float(v[1]), float(v[2])
    (x1, y1, z1), (x2, y2, z2) = xyz(a), xyz(b)
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)


def jumps_needed(distance_ly: float, jump_range_ly: float) -> int:
    """Ceiling jump count for a laden/unladen range (min 1 if > 0)."""
    if distance_ly <= 0:
        return 0
    return max(1, math.ceil(distance_ly / max(jump_range_ly, 0.1)))


def match_market(results: list[dict[str, Any]], commodity: str,
                 mode: str = "buy", min_qty: int = 1,
                 large_pad_only: bool = False) -> list[dict[str, Any]]:
    """Shortlist stations trading a commodity from a /stations/search payload.

    mode 'buy' = station has supply (we buy); 'sell' = station has demand.
    Never invents stock: only rows present in each station's market list.
    """
    want = commodity.strip().lower()
    out: list[dict[str, Any]] = []
    for r in results:
        if large_pad_only and not r.get("has_large_pad"):
            continue
        for c in (r.get("market") or []):
            if not isinstance(c, dict):
                continue
            if want not in str(c.get("commodity", "")).lower():
                continue
            qty = int(c.get("supply") or 0) if mode == "buy" else int(c.get("demand") or 0)
            if qty < min_qty:
                continue
            out.append({
                "station": r.get("name"), "system": r.get("system_name"),
                "distance_ly": r.get("distance"),
                "distance_to_arrival_ls": r.get("distance_to_arrival"),
                "large_pads": r.get("large_pads"),
                "type": r.get("type"),
                "market_updated_at": r.get("market_updated_at"),
                "commodity": c.get("commodity"),
                "supply": c.get("supply"), "demand": c.get("demand"),
                "sell_price": c.get("sell_price"), "buy_price": c.get("buy_price"),
            })
    if mode == "buy":
        out.sort(key=lambda h: (-(h["supply"] or 0), h["distance_ly"] or 9999))
    else:
        out.sort(key=lambda h: (-(h["demand"] or 0), h["distance_ly"] or 9999))
    return out


#: How a module is acquired, from Spansh's outfitting `category` field.
#: Anything but "standard" (e.g. "mercgear" pre-engineered stock) is NOT a
#: plain credit purchase — it can need tech-broker materials, Powerplay
#: merits/rank, or other unlocks. Always verify in-game before flying out.
ACQUISITION_NOTES = {
    "standard": "credits (normal outfitting purchase)",
    "mercgear": "SPECIAL: pre-engineered mercenary gear — needs tech-broker materials / unlocks, not just credits",
    "techbroker": "SPECIAL: technology broker — needs materials unlock, not just credits",
    "powerplay": "SPECIAL: Powerplay — needs merits and rank, not just credits",
}


def acquisition_of(module: dict[str, Any]) -> tuple[str, str]:
    """(acquisition, note) for one Spansh outfitting entry."""
    cat = str(module.get("category") or "standard").lower()
    if cat == "standard":
        return "credits", ACQUISITION_NOTES["standard"]
    return "special", ACQUISITION_NOTES.get(cat, f"SPECIAL: non-standard stock ({cat}) — verify in-game before flying out")


def match_module(results: list[dict[str, Any]], query: str,
                 standard_only: bool = False) -> list[dict[str, Any]]:
    """Stations whose modules list contains the query (name or ed_symbol).

    Each hit carries `acquisition` ("credits" or "special") plus a note, so
    pre-engineered/tech-broker/Powerplay stock is never mistaken for a normal
    credit purchase. `standard_only=True` drops special-acquisition hits.
    """
    want = query.strip().lower()
    out: list[dict[str, Any]] = []
    for r in results:
        hits = []
        for m in (r.get("modules") or []):
            if not isinstance(m, dict):
                continue
            if not (want in str(m.get("name", "")).lower()
                    or want in str(m.get("ed_symbol", "")).lower()):
                continue
            acq, note = acquisition_of(m)
            if standard_only and acq != "credits":
                continue
            hits.append({**m, "acquisition": acq, "acquisition_note": note})
        if hits:
            specials = sum(1 for h in hits if h["acquisition"] == "special")
            out.append({"station": r.get("name"), "system": r.get("system_name"),
                        "distance_ly": r.get("distance"),
                        "large_pads": r.get("large_pads"),
                        "outfitting_updated_at": r.get("outfitting_updated_at"),
                        "matches": hits[:10], "match_count": len(hits),
                        "has_special_acquisition": specials > 0})
    return sorted(out, key=lambda h: h["distance_ly"] or 9999)


def match_ship(results: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Stations whose shipyard lists the named ship."""
    want = query.strip().lower()
    out: list[dict[str, Any]] = []
    for r in results:
        hits = [s for s in (r.get("ships") or [])
                if isinstance(s, dict) and
                (want in str(s.get("name", "")).lower()
                 or want in str(s.get("symbol", "")).lower())]
        if hits:
            out.append({"station": r.get("name"), "system": r.get("system_name"),
                        "distance_ly": r.get("distance"),
                        "shipyard_updated_at": r.get("shipyard_updated_at"),
                        "matches": hits[:10]})
    return sorted(out, key=lambda h: h["distance_ly"] or 9999)


def summarise_bodies(results: list[dict[str, Any]],
                     max_results: int = 20) -> list[dict[str, Any]]:
    """Slim a /bodies/search payload to explorer-relevant fields."""
    out: list[dict[str, Any]] = []
    for b in results[:max_results]:
        out.append({
            "body": b.get("name"), "system": b.get("system_name"),
            "distance_ly": b.get("distance"),
            "distance_to_arrival_ls": b.get("distance_to_arrival"),
            "type": b.get("sub_type") or b.get("type"),
            "earth_masses": b.get("earth_masses"),
            "estimated_value": b.get("estimated_value") or b.get("estimated_map_value"),
            "is_landable": b.get("is_landable"),
            "terraforming": b.get("terraforming_state") or b.get("terraform_state"),
        })
    return out


def slim_station(record: dict[str, Any]) -> dict[str, Any]:
    """Slim one Spansh station record to services/pads/market essentials (pure).

    Always surfaces the full system name for galaxy-map paste and flags the
    System Colonisation contact explicitly. `services_raw` keeps full names.
    """
    services = [s.get("name") for s in (record.get("services") or [])
                if isinstance(s, dict) and s.get("name")]
    return {
        "station": record.get("name"), "system": record.get("system_name"),
        "type": record.get("type"), "distance_ly": record.get("distance"),
        "distance_to_arrival_ls": record.get("distance_to_arrival"),
        "large_pads": record.get("large_pads"),
        "has_large_pad": record.get("has_large_pad"),
        "is_planetary": record.get("is_planetary"),
        "has_market": record.get("has_market"),
        "has_outfitting": record.get("has_outfitting"),
        "has_shipyard": record.get("has_shipyard"),
        "has_colonisation_contact": "System Colonisation" in services,
        "services": services,
        "system_population": record.get("system_population"),
        "updated_at": record.get("updated_at"),
        "market_updated_at": record.get("market_updated_at"),
        "outfitting_updated_at": record.get("outfitting_updated_at"),
    }
