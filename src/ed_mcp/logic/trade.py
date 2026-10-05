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


def match_module(results: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Stations whose modules list contains the query (name or ed_symbol)."""
    want = query.strip().lower()
    out: list[dict[str, Any]] = []
    for r in results:
        hits = [m for m in (r.get("modules") or [])
                if isinstance(m, dict) and
                (want in str(m.get("name", "")).lower()
                 or want in str(m.get("ed_symbol", "")).lower())]
        if hits:
            out.append({"station": r.get("name"), "system": r.get("system_name"),
                        "distance_ly": r.get("distance"),
                        "large_pads": r.get("large_pads"),
                        "outfitting_updated_at": r.get("outfitting_updated_at"),
                        "matches": hits[:10], "match_count": len(hits)})
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
