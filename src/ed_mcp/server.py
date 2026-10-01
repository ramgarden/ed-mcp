"""MCP server entrypoint: exposes Elite Dangerous tools over stdio."""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ed_mcp import config as cfg
from ed_mcp.data import load_anaconda_cargo_build, load_constellations
from ed_mcp.logic import colonisation as col_logic
from ed_mcp.logic import outfitting as out_logic
from ed_mcp.providers import eddn as eddn_p
from ed_mcp.providers import edsm as edsm_p
from ed_mcp.providers import inara as inara_p
from ed_mcp.providers import journal as journal_p
from ed_mcp.providers import spansh as spansh_p

mcp = FastMCP("ed-mcp")


# ---- local journals ----
@mcp.tool()
def get_commander_status(journal_dir: str | None = None) -> dict[str, Any]:
    """Commander name, current system/station, ship, credits from local journals."""
    return journal_p.get_status(journal_dir)


@mcp.tool()
def get_current_location(journal_dir: str | None = None) -> dict[str, Any]:
    """Current system + coords + station from latest Location/FSDJump/Docked event."""
    return journal_p.get_location(journal_dir)


@mcp.tool()
def get_ship_loadout(journal_dir: str | None = None) -> dict[str, Any]:
    """Current ship + modules from latest Loadout event."""
    return journal_p.get_loadout(journal_dir)


@mcp.tool()
def get_journal_history(limit: int = 25, journal_dir: str | None = None) -> dict[str, Any]:
    """Recent relevant journal events, newest first (FSDJump, Docked, Loadout, ...)."""
    return journal_p.get_history(limit=limit, journal_dir=journal_dir)


# ---- EDSM ----
@mcp.tool()
def edsm_sphere_systems(system_name: str | None = None, x: float | None = None,
                        y: float | None = None, z: float | None = None,
                        radius_ly: float = 15.0) -> dict[str, Any]:
    """Systems within radius_ly of a system name or x/y/z coords (EDSM)."""
    try:
        systems = edsm_p.sphere_systems(system_name=system_name, x=x, y=y, z=z,
                                        radius_ly=radius_ly)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "count": len(systems), "systems": systems[:200]}


@mcp.tool()
def edsm_system_info(system_name: str) -> dict[str, Any]:
    """Population/government/stations for one system + claimable assessment (EDSM)."""
    try:
        info = edsm_p.system_info(system_name)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    ok, reasons = col_logic.is_claimable_candidate(info)
    return {"ok": True, "system": info, "claimable_candidate": ok, "reasons": reasons}


# ---- Spansh ----
@mcp.tool()
def spansh_find_nearby_stations(x: float, y: float, z: float,
                                max_results: int = 10) -> dict[str, Any]:
    """Stations nearest to galactic coords, slimmed for shopping lists (Spansh)."""
    try:
        payload = spansh_p.nearest_stations(x, y, z, max_results=max_results)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "stations": out_logic.summarise_station_stock(payload, max_results),
            "raw_count": len(payload.get("results", []))}


@mcp.tool()
def spansh_query_systems(filters: dict[str, Any] | None = None,
                         page: int = 1) -> dict[str, Any]:
    """Flexible Spansh systems search, e.g. {"population": {"value": [0,0]}}."""
    try:
        return {"ok": True, **spansh_p.search_systems(filters=filters or {}, page=page)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- Inara ----
@mcp.tool()
def inara_search_nearest(system_name: str, search: str = "station") -> dict[str, Any]:
    """Nearest stations/systems via Inara API (needs INARA_API_KEY)."""
    try:
        return {"ok": True, **inara_p.search_nearest(system_name, search=search)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- EDDN ----
@mcp.tool()
def eddn_live_sample(max_messages: int = 5, timeout_s: float = 15.0) -> dict[str, Any]:
    """Bounded sample of live EDDN relay messages (needs pyzmq + network)."""
    return eddn_p.sample(max_messages=max_messages, timeout_s=timeout_s,
                         relay=cfg.SETTINGS.eddn_relay)


# ---- composite: colonisation (Teapot example) ----
@mcp.tool()
def find_colonisation_candidates(centre: str = "teapot", radius_ly: float = 15.0,
                                 max_candidates: int = 20) -> dict[str, Any]:
    """Zero-pop, claimable systems near a constellation/centre.

    centre: 'teapot' (Sagittarius asterism) or an EDSM system name or 'x,y,z'.
    Workflow: resolve Teapot anchor stars -> EDSM sphere search per anchor ->
    batch detail lookup -> filter zero-pop/uncontrolled/stationless -> dedupe.
    """
    constellations = load_constellations()
    anchors: list[dict[str, Any]] = []
    if centre.lower() == "teapot":
        anchors = constellations["teapot"]["stars"]
    elif "," in centre:
        try:
            x0, y0, z0 = (float(v) for v in centre.split(","))
            anchors = [{"name": centre, "x": x0, "y": y0, "z": z0}]
        except ValueError:
            return {"ok": False, "error": "centre must be 'teapot', a system name, or 'x,y,z'."}
    else:
        anchors = [{"name": centre, "edsm": centre}]

    gathered: list[dict[str, Any]] = []
    errors: list[str] = []
    for a in anchors:
        try:
            if "edsm" in a:
                sphere = edsm_p.sphere_systems(system_name=a["edsm"], radius_ly=radius_ly)
            else:
                sphere = edsm_p.sphere_systems(x=a["x"], y=a["y"], z=a["z"],
                                               radius_ly=radius_ly)
            for s in sphere:
                s["_anchor"] = a.get("name")
            gathered.extend(sphere)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{a.get('name')}: {exc}")
    gathered = col_logic.dedupe_by_name(gathered)

    # Batch detail for claimable filtering (cap to keep the call fast)
    names = [s.get("name") for s in gathered[:100] if s.get("name")]
    try:
        details = edsm_p.systems_info(names) if names else []
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "candidates": [], "searched": len(gathered),
                "warning": f"detail lookup failed ({exc}); returning unfiltered sphere.",
                "systems": gathered[:100], "errors": errors}
    by_name = {d.get("name", "").lower(): d for d in details if isinstance(d, dict)}
    candidates: list[dict[str, Any]] = []
    for s in gathered:
        d = by_name.get((s.get("name") or "").lower(), s)
        ok, reasons = col_logic.is_claimable_candidate(d)
        if ok:
            candidates.append({"name": s.get("name"), "coords": s.get("coords"),
                               "distance": s.get("distance"), "anchor": s.get("_anchor"),
                               "reasons": reasons, "info": d})
        if len(candidates) >= max_candidates:
            break
    return {"ok": True, "centre": centre, "radius_ly": radius_ly,
            "searched": len(gathered), "candidates": candidates, "errors": errors,
            "note": "Confirm in-game (colonisation UI) before travelling; rules change."}


# ---- composite: Anaconda max-cargo shopping list ----
@mcp.tool()
def build_cargo_shopping_list(journal_dir: str | None = None,
                              search_radius_ly: float = 50.0,
                              max_stations: int = 10) -> dict[str, Any]:
    """Anaconda max-cargo module list + where to buy near your current location.

    Uses journals for current system/coords + owned modules, Spansh for nearby
    stations with outfitting, EDSM sphere as fallback. Prices/stock rotate;
    verify at the station.
    """
    build = load_anaconda_cargo_build()
    loc = journal_p.get_location(journal_dir)
    loadout = journal_p.get_loadout(journal_dir)
    owned: set[str] = set()
    if loadout.get("found"):
        for m in loadout.get("modules", []):
            if m.get("item"):
                owned.add(str(m["item"]).lower())
    items = out_logic.shopping_list_for_build(build, owned)

    coords = (loc.get("star_pos") or []) if loc.get("found") else []
    stations: list[dict[str, Any]] = []
    station_source = "none"
    if len(coords) == 3:
        try:
            payload = spansh_p.nearest_stations(coords[0], coords[1], coords[2],
                                               max_results=max_stations)
            stations = out_logic.summarise_station_stock(payload, max_stations)
            station_source = "spansh"
        except Exception as exc:  # noqa: BLE001
            station_source = f"spansh failed: {exc}"
    result: dict[str, Any] = {
        "ok": True,
        "ship": build["ship"],
        "goal": build["goal"],
        "expected_capacity_t": build.get("expected_capacity_t"),
        "current_location": loc,
        "shopping_list": items,
        "stations": stations,
        "station_source": station_source,
        "notes": build.get("notes", []),
    }
    if not loc.get("found"):
        result["warning"] = ("Current location unknown (no journals). "
                             "Provide journal_dir or system coords.")
    return result


# ---- prompts: worked examples ----
@mcp.prompt()
def colonisation_survey() -> str:
    return ("You are surveying colonisation candidates. Steps: 1) call "
            "get_commander_status to note the commander's position. 2) call "
            "find_colonisation_candidates with centre='teapot', radius_ly=15. "
            "3) For the top 5, call edsm_system_info to confirm zero population, "
            "no faction, no stations, no permit. 4) Present a table: system, "
            "anchor star, distance, coords, why claimable, what to verify in-game. "
            "Never invent systems; only report tool output.")


@mcp.prompt()
def anaconda_cargo_refit() -> str:
    return ("You are an outfitting officer. Steps: 1) call get_current_location "
            "and get_ship_loadout. 2) call build_cargo_shopping_list. 3) For the "
            "top stations call spansh_find_nearby_stations with the commander's "
            "coords. 4) Present: current system/ship, module shopping list "
            "(slot, wanted module, owned?), nearby stations (system/station, "
            "distance, outfitting?), and cost caveat (verify live prices). "
            "Never invent stock or prices.")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
