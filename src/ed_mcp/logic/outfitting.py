"""Outfitting / shopping-list logic for the Anaconda max-cargo example."""
from __future__ import annotations

from typing import Any


def shopping_list_for_build(build: dict[str, Any],
                            owned_items: set[str] | None = None) -> list[dict[str, Any]]:
    """Mark which build items the commander already owns (from Loadout)."""
    owned = {i.lower() for i in (owned_items or set())}
    items: list[dict[str, Any]] = []
    for entry in build.get("build", []):
        want = entry.get("want", "")
        # crude match: does any owned module string appear in the wanted text?
        have = any(o and o in want.lower() for o in owned)
        items.append({"slot": entry.get("slot"), "want": want, "already_owned": have})
    return items


def summarise_station_stock(stations_payload: dict[str, Any],
                            max_results: int = 10) -> list[dict[str, Any]]:
    """Slim a Spansh stations response to what the shopping list needs."""
    results = stations_payload.get("results") or stations_payload.get("stations") or []
    out: list[dict[str, Any]] = []
    for s in results[:max_results]:
        out.append({
            "station": s.get("name"),
            "system": (s.get("system") or {}).get("name") if isinstance(s.get("system"), dict) else s.get("system_name"),
            "distance": s.get("distance"),
            "has_outfitting": s.get("has_outfitting"),
            "has_shipyard": s.get("has_shipyard"),
            "max_pad": s.get("max_landing_pad_size"),
            "updated": s.get("updated_at") or s.get("update_time"),
        })
    return out
