"""MCP server entrypoint: exposes Elite Dangerous tools over stdio."""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ed_mcp import config as cfg
from ed_mcp.data import load_anaconda_cargo_build, load_constellations
from ed_mcp.logic import colonisation as col_logic
from ed_mcp.logic import outfitting as out_logic
from ed_mcp.logic import trade as trade_logic
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
    if not info or not info.get("name"):
        return {"ok": False, "error": f"System '{system_name}' not found in EDSM."}
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
def inara_search_nearest(system_name: str, search: str = "station",
                         commander: str | None = None) -> dict[str, Any]:
    """Nearest stations/systems via Inara API (needs INARA_API_KEY + app access).

    Falls back to website search URLs when the API app has no access.
    """
    try:
        res = inara_p.search_nearest(system_name, search=search,
                                     commander=commander or "ed-mcp")
        if isinstance(res, dict):
            header = res.get("header", {}) if isinstance(res.get("header"), dict) else {}
            if header.get("eventStatus") not in (None, 200, "200"):
                res["website_fallback"] = inara_p.website_search_urls(system_name)
        return {"ok": True, **res}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def inara_website_search(system_name: str = "", commodity: str = "",
                         station_name: str = "") -> dict[str, Any]:
    """Inara website search links + page check (no API key needed)."""
    try:
        return {"ok": True, **inara_p.website_search(system_name, commodity, station_name)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- EDDN ----
@mcp.tool()
def eddn_live_sample(max_messages: int = 5, timeout_s: float = 15.0,
                     schema: str | None = None) -> dict[str, Any]:
    """Bounded sample of live EDDN relay messages (needs pyzmq + network).

    schema: substring filter on $schemaRef, e.g. "commodity". None = all.
    """
    return eddn_p.sample(max_messages=max_messages, timeout_s=timeout_s,
                         schema=schema, relay=cfg.SETTINGS.eddn_relay)


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


# ---- local journals: cargo/market/fleet/wallet/odyssey ----
@mcp.tool()
def get_cargo_hold(journal_dir: str | None = None) -> dict[str, Any]:
    """Current cargo manifest + rack capacity + free space (Cargo.json + Loadout)."""
    try:
        return {"ok": True, **journal_p.get_cargo_hold(journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_station_market(journal_dir: str | None = None) -> dict[str, Any]:
    """Live market at your docked station (Market.json): prices/supply/demand."""
    try:
        return {"ok": True, **journal_p.get_station_market(journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_station_outfitting(journal_dir: str | None = None) -> dict[str, Any]:
    """Outfitting stock at your station (Outfitting.json + ModulesInfo.json)."""
    try:
        return {"ok": True, **journal_p.get_station_outfitting(journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_station_shipyard(journal_dir: str | None = None) -> dict[str, Any]:
    """Shipyard stock at your station (Shipyard.json)."""
    try:
        return {"ok": True, **journal_p.get_station_shipyard(journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_fleet_overview(journal_dir: str | None = None) -> dict[str, Any]:
    """Every ship in your journals + computed cargo per ship (latest first)."""
    try:
        return {"ok": True, **journal_p.get_fleet_overview(journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_wallet_summary(journal_dir: str | None = None) -> dict[str, Any]:
    """Credits now + lifetime MarketBuy/MarketSell/MissionCompleted sums."""
    try:
        return {"ok": True, **journal_p.get_wallet_summary(journal_dir=journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_odyssey_state(journal_dir: str | None = None) -> dict[str, Any]:
    """On-foot state: Backpack + ShipLocker + latest suit loadout events."""
    try:
        return {"ok": True, **journal_p.get_odyssey_state(journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- Spansh/EDSM: trade, outfitting, shipyard, exploration, distances ----
def _ref_coords(system_name: str | None, x: float | None, y: float | None,
               z: float | None,
               journal_dir: str | None = None) -> tuple[dict[str, Any], dict[str, float] | None]:
    """Resolve reference coords from explicit x/y/z, a system name, or journals."""
    if x is not None and y is not None and z is not None:
        return {}, {"x": x, "y": y, "z": z}
    if system_name:
        info = edsm_p.system_info(system_name)
        coords = info.get("coords") if isinstance(info, dict) else None
        if not coords:
            raise ValueError(f"No EDSM coords for '{system_name}'.")
        return {}, {"x": coords["x"], "y": coords["y"], "z": coords["z"]}
    loc = journal_p.get_location(journal_dir)
    star_pos = loc.get("star_pos") if loc.get("found") else None
    if star_pos and len(star_pos) == 3:
        return {}, {"x": star_pos[0], "y": star_pos[1], "z": star_pos[2]}
    raise ValueError("No reference point: pass system_name or x/y/z, or dock/jump once for journal coords.")


@mcp.tool()
def spansh_search_stations(filters: dict[str, Any] | None = None, page: int = 1,
                           size: int = 20, system_name: str | None = None,
                           x: float | None = None, y: float | None = None,
                           z: float | None = None) -> dict[str, Any]:
    """Full Spansh /stations/search passthrough (pads/services/market filters)."""
    try:
        _, ref = _ref_coords(system_name, x, y, z) if (system_name or x is not None) else ({}, None)
        sorts = ([{"distance": {"direction": "asc",
                                "distance": ref}}] if ref else [])
        payload = spansh_p.search_stations(filters=filters or {}, sorts=sorts,
                                           page=page, size=min(max(size, 1), 100))
        return {"ok": True, **payload}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def find_commodity(commodity: str, mode: str = "buy", system_name: str | None = None,
                   x: float | None = None, y: float | None = None,
                   z: float | None = None, min_qty: int = 1,
                   large_pad_only: bool = False, max_results: int = 10,
                   journal_dir: str | None = None) -> dict[str, Any]:
    """Best stations trading a commodity near you (live Spansh market snapshots).

    mode 'buy' = station has supply; 'sell' = station has demand. Sorted by
    stock size then distance. Stock rotates; verify in-game before flying.
    """
    try:
        if mode not in ("buy", "sell"):
            return {"ok": False, "error": "mode must be 'buy' or 'sell'."}
        _, ref = _ref_coords(system_name, x, y, z, journal_dir)
        payload = spansh_p.search_stations(
            filters={"has_market": {"value": [1]}},
            sorts=[{"distance": {"direction": "asc", "distance": ref}}],
            page=1, size=100)
        hits = trade_logic.match_market(payload.get("results", []), commodity,
                                        mode=mode, min_qty=min_qty,
                                        large_pad_only=large_pad_only)
        return {"ok": True, "commodity": commodity, "mode": mode,
                "ref": ref, "count": len(hits), "stations": hits[:max_results],
                "note": "Spansh market snapshots; verify live prices in-game."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def find_module(module_query: str, system_name: str | None = None,
                x: float | None = None, y: float | None = None,
                z: float | None = None, max_results: int = 10,
                journal_dir: str | None = None) -> dict[str, Any]:
    """Stations selling a module near you (matches name or ed_symbol, live Spansh)."""
    try:
        _, ref = _ref_coords(system_name, x, y, z, journal_dir)
        payload = spansh_p.search_stations(
            filters={}, sorts=[{"distance": {"direction": "asc", "distance": ref}}],
            page=1, size=100)
        hits = trade_logic.match_module(payload.get("results", []), module_query)
        return {"ok": True, "query": module_query, "ref": ref,
                "count": len(hits), "stations": hits[:max_results]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def find_ship(ship_query: str, system_name: str | None = None,
              x: float | None = None, y: float | None = None,
              z: float | None = None, max_results: int = 10,
              journal_dir: str | None = None) -> dict[str, Any]:
    """Stations selling a ship near you (live Spansh shipyard lists)."""
    try:
        _, ref = _ref_coords(system_name, x, y, z, journal_dir)
        payload = spansh_p.search_stations(
            filters={}, sorts=[{"distance": {"direction": "asc", "distance": ref}}],
            page=1, size=100)
        hits = trade_logic.match_ship(payload.get("results", []), ship_query)
        return {"ok": True, "query": ship_query, "ref": ref,
                "count": len(hits), "stations": hits[:max_results]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def spansh_search_bodies(filters: dict[str, Any] | None = None, page: int = 1,
                         size: int = 20, system_name: str | None = None,
                         x: float | None = None, y: float | None = None,
                         z: float | None = None) -> dict[str, Any]:
    """Exploration search over Spansh bodies (e.g. Earth-likes near a reference)."""
    try:
        _, ref = _ref_coords(system_name, x, y, z) if (system_name or x is not None) else ({}, None)
        sorts = ([{"distance": {"direction": "asc",
                                "distance": ref}}] if ref else [])
        payload = spansh_p.search_bodies(filters=filters or {}, sorts=sorts,
                                         page=page, size=min(max(size, 1), 100))
        return {"ok": True,
                "bodies": trade_logic.summarise_bodies(payload.get("results", [])),
                "count": payload.get("count"), "raw": len(payload.get("results", []))}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def system_distance(from_system: str, to_system: str,
                    jump_range_ly: float = 0.0) -> dict[str, Any]:
    """Light-year distance between two systems (live EDSM coords) + jump estimate."""
    try:
        a = edsm_p.system_info(from_system)
        b = edsm_p.system_info(to_system)
        ca, cb = a.get("coords"), b.get("coords")
        if not ca or not cb:
            return {"ok": False, "error": "EDSM has no coords for one of the systems."}
        d = trade_logic.distance_ly(ca, cb)
        out: dict[str, Any] = {"ok": True, "from": from_system, "to": to_system,
                               "distance_ly": round(d, 2), "from_coords": ca,
                               "to_coords": cb}
        if jump_range_ly and jump_range_ly > 0:
            out["jumps"] = trade_logic.jumps_needed(d, jump_range_ly)
            out["jump_range_ly"] = jump_range_ly
        return out
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- exploration survey: searched vs unsearched (Raxxla-grid support) ----
@mcp.tool()
def get_exploration_log(journal_dir: str | None = None, grade: str | None = None,
                        limit: int = 50) -> dict[str, Any]:
    """Per-system survey ledger from YOUR journals (COMPLETE/PARTIAL/VISITED).

    grade: optionally filter to one grade. limit caps rows (default 50).
    """
    from ed_mcp.logic import survey as survey_logic
    try:
        jdir = journal_p.resolve_journal_dir(journal_dir) if journal_dir else journal_p.resolve_journal_dir()
        rows = survey_logic.rollup_journal_scans(list(journal_p._iter_events(jdir)))
        all_rows = sorted(rows.values(), key=lambda r: (r["grade"], -(r["visits"])))
        if grade:
            want = grade.strip().upper()
            all_rows = [r for r in all_rows if r["grade"] == want]
        totals: dict[str, int] = {}
        for r in rows.values():
            totals[r["grade"]] = totals.get(r["grade"], 0) + 1
        return {"ok": True, "systems_tracked": len(rows), "totals": totals,
                "rows": all_rows[:max(1, min(limit, 500))]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def system_scan_status(system_name: str,
                       journal_dir: str | None = None) -> dict[str, Any]:
    """How deeply has ONE system been scanned — community catalog + your log.

    Community: live EDSM bodies catalog count + type break-down + scan value.
    You: matching journal row (visits/FSS/scans/mapped) if ever visited.
    """
    from ed_mcp.logic import survey as survey_logic
    try:
        catalog = edsm_p.system_bodies(system_name)
        bodies = catalog.get("bodies", []) if isinstance(catalog, dict) else []
        breakdown = survey_logic.summarise_bodies_catalog(bodies)
        try:
            value = edsm_p.system_estimated_value(system_name)
        except Exception as exc:  # noqa: BLE001
            value = {"error": str(exc)[:200]}
        mine = None
        jdir = (journal_p.resolve_journal_dir(journal_dir) if journal_dir
                else journal_p.resolve_journal_dir())
        for r in survey_logic.rollup_journal_scans(
                list(journal_p._iter_events(jdir))).values():
            if r["system"] and r["system"].lower() == system_name.lower():
                mine = r
                break
        return {"ok": True, "system": system_name, "community": breakdown,
                "estimated_value": value, "yours": mine or "unvisited in your journals",
                "note": "Catalogued bodies prove others scanned it; absence proves little (unsynced CMDRs exist)."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def find_search_backlog(system_name: str, radius_ly: float = 15.0,
                        max_results: int = 20,
                        journal_dir: str | None = None) -> dict[str, Any]:
    """Systems near a reference YOU have not fully scanned (Raxxla grid backlog).

    Cross-references live EDSM sphere (with bodyCount) against your journal
    ledger: UNVISITED first, then VISITED-but-incomplete. Confirm in-game.
    """
    from ed_mcp.logic import survey as survey_logic
    try:
        sphere = edsm_p.sphere_systems(system_name=system_name, radius_ly=radius_ly)
        jdir = (journal_p.resolve_journal_dir(journal_dir) if journal_dir
                else journal_p.resolve_journal_dir())
        mine = survey_logic.rollup_journal_scans(list(journal_p._iter_events(jdir)))
        by_name = {str(r["system"]).lower(): r for r in mine.values() if r["system"]}
        backlog = []
        for s in sphere:
            if (s.get("name") or "").lower() == system_name.lower():
                continue
            r = by_name.get((s.get("name") or "").lower())
            grade = r["grade"] if r else "UNVISITED"
            if grade == "COMPLETE":
                continue
            info = s.get("information", {}) or {}
            backlog.append({"system": s.get("name"), "distance_ly": s.get("distance"),
                            "your_grade": grade,
                            "edsm_body_count": s.get("bodyCount"),
                            "population": info.get("population"),
                            "visits": r["visits"] if r else 0,
                            "fss_progress": r["fss_progress"] if r else 0.0})
        order = {"UNVISITED": 0, "VISITED": 1, "PARTIAL": 2}
        backlog.sort(key=lambda b: (order.get(b["your_grade"], 3), b["distance_ly"] or 9999))
        return {"ok": True, "reference": system_name, "radius_ly": radius_ly,
                "sphere_count": len(sphere), "backlog_count": len(backlog),
                "backlog": backlog[:max(1, min(max_results, 200))],
                "note": "UNVISITED = absent from your journals, not proof nobody scanned it."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


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


@mcp.prompt()
def trade_run() -> str:
    return ("You are a trade officer. Steps: 1) call get_commander_status and "
            "get_cargo_hold. 2) call find_commodity for the named commodity with "
            "mode='buy' (or 'sell' for offloading), large_pad_only=true if the "
            "player flies a large ship. 3) call system_distance from the player's "
            "system to the top station's system. 4) Present: cargo/free space, "
            "top stations (system/station, distance, supply/demand, price, "
            "market age), jumps at their range, and a verify-in-game caveat. "
            "Never invent stock or prices.")


@mcp.prompt()
def raxxla_survey() -> str:
    return ("You support methodical Raxxla grid searching WITHOUT claiming a "
            "location. Steps: 1) call get_exploration_log for totals. "
            "2) call find_search_backlog around the commander's area for the "
            "unsearched backlog. 3) For top candidates call system_scan_status "
            "for community catalog depth. 4) Present: searched vs unsearched "
            "counts, backlog table (system, distance, your grade, EDSM bodies), "
            "and the caveat that absence from journals/EDSM never proves a "
            "system hides anything. Never invent Raxxla's location.")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
