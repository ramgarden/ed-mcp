"""MCP server entrypoint: exposes Elite Dangerous tools over stdio."""
from __future__ import annotations

import json
from pathlib import Path
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
from ed_mcp.research import artifact_store as research_store
from ed_mcp.research import experiment as research_exp
from ed_mcp.research import provenance as research_prov
from ed_mcp.research import region as research_region
from ed_mcp.logic import graph as graph_logic
from ed_mcp.logic import spatial as spatial_logic
from ed_mcp.logic import temporal as temporal_logic

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


@mcp.tool()
def get_ship_purchase_history(ship_query: str | None = None,
                              journal_dir: str | None = None) -> dict[str, Any]:
    """Your actual ship purchase history from journal events (ShipyardBuy/ShipyardSell).

    Returns real purchase prices, stations, systems, timestamps — useful for
    comparing current market prices vs what you actually paid, spotting discounts.
    """
    try:
        return {"ok": True, **journal_p.get_ship_purchase_history(
            journal_dir, ship_query)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_module_purchase_history(module_query: str | None = None,
                                journal_dir: str | None = None) -> dict[str, Any]:
    """Your module purchase history from journal events (ModuleBuy/ModuleSell/ModuleRetrieve).

    Returns real purchase prices, stations, systems, timestamps — useful for
    comparing current outfitting prices vs what you actually paid.
    """
    try:
        return {"ok": True, **journal_p.get_module_purchase_history(
            journal_dir, module_query)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


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


# ---- local journals: exobiology + cargo/market/fleet/wallet/odyssey ----
@mcp.tool()
def find_exobiology_targets(system_name: str | None = None,
                            x: float | None = None, y: float | None = None,
                            z: float | None = None,
                            radius_ly: float = 50.0,
                            max_results: int = 20,
                            journal_dir: str | None = None) -> dict[str, Any]:
    """Best exobiology targets near you: organic-rich systems with estimated turn-in.

    Uses Spansh bodies search for organic-life bodies, ranks systems by
    estimated turn-in credits (body value x biology multiplier). Returns
    per-system body breakdown with distance and estimated value.
    """
    try:
        _, ref = _ref_coords(system_name, x, y, z, journal_dir)
        sorts = [{"distance": {"direction": "asc", "distance": ref}}]
        payload = spansh_p.search_bodies(
            filters={}, sorts=sorts, page=1, size=min(max(radius_ly, 10), 200))
        organic = trade_logic.find_organic_bodies(payload.get("results", []))
        ranked = trade_logic.rank_organic_systems(organic, per_system_limit=max_results)
        return {"ok": True, "ref": ref, "radius_ly": radius_ly,
                "bodies_found": len(organic), **ranked,
                "note": "Spansh body snapshots; verify in-game before flying."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_exobiology_samples(journal_dir: str | None = None,
                           system_name: str | None = None) -> dict[str, Any]:
    """Exobiology sample status: discovery, FSS progress, estimated turn-in credits.

    Reads local journals for FSSAllBodiesFound / ScanOrganic / SAAScanComplete
    events. When FSS complete, uses EDSM estimated system value for turn-in credits.
    community_discovered=True means FSS complete OR EDSM has catalogued bodies (others
    discovered before you).
    """
    try:
        return {"ok": True, **journal_p.get_exobiology_samples(journal_dir, system_name)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


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


@mcp.tool()
def find_stored_ship(query: str | None = None,
                     journal_dir: str | None = None) -> dict[str, Any]:
    """Locate a stored ship: station/system + transfer cost/time.

    Matches name or ship type (case-insensitive); omit query to list all.
    Latest StoredShips sighting per ship wins.
    """
    try:
        got = journal_p.get_stored_ships(journal_dir)
        if not got.get("found"):
            return {"ok": True, **got}
        ships = got.get("ships", [])
        if query:
            want = query.strip().lower()
            ships = [s for s in ships
                     if want in str(s.get("name") or "").lower()
                     or want in str(s.get("ship") or "").lower()]
        return {"ok": True, "query": query, "count": len(ships), "ships": ships}
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
def find_multi_supply(commodities: dict[str, int],
                      system_name: str | None = None,
                      x: float | None = None, y: float | None = None,
                      z: float | None = None, large_pad_only: bool = False,
                      orbital_only: bool = False, pages: int = 4,
                      max_results: int = 10,
                      journal_dir: str | None = None) -> dict[str, Any]:
    """One station covering a whole shopping list (live Spansh markets).

    `commodities` maps name -> minimum supply for one full load, e.g.
    {"Steel": 2000, "Titanium": 2000}. Scans `pages` x 100 nearest stations
    (default 4, max 10); full-cover stations first, then most lines covered,
    then nearest. Stock rotates; verify in-game before flying.
    """
    try:
        _, ref = _ref_coords(system_name, x, y, z, journal_dir)
        sorts = [{"distance": {"direction": "asc", "distance": ref}}]
        seen: dict[Any, dict[str, Any]] = {}
        for page in range(1, min(max(pages, 1), 10) + 1):
            payload = spansh_p.search_stations(
                filters={}, sorts=sorts, page=page, size=100)
            for r in payload.get("results", []) or []:
                seen[r.get("id", (r.get("name"), r.get("system_name")))] = r
        hits = trade_logic.match_multi_supply(
            list(seen.values()), commodities,
            large_pad_only=large_pad_only, orbital_only=orbital_only)
        return {"ok": True, "commodities": commodities, "ref": ref,
                "stations_scanned": len(seen),
                "count": len(hits), "stations": hits[:max_results],
                "note": "Spansh market snapshots; verify live stock in-game."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def find_module(module_query: str, system_name: str | None = None,
                x: float | None = None, y: float | None = None,
                z: float | None = None, max_results: int = 10,
                journal_dir: str | None = None, pages: int = 1,
                standard_only: bool = False) -> dict[str, Any]:
    """Stations selling a module near you (matches name or ed_symbol, live Spansh).

    Scans `pages` x 100 nearest stations (default 1, max 10): Spansh outfitting
    snapshots are sparse, so one page misses stock. Each hit carries
    `acquisition` ("credits" vs "special") — pre-engineered/tech-broker/
    Powerplay stock (e.g. mercgear) is NOT a plain credit purchase.
    `standard_only=True` drops special-acquisition hits.
    """
    try:
        _, ref = _ref_coords(system_name, x, y, z, journal_dir)
        sorts = [{"distance": {"direction": "asc", "distance": ref}}]
        seen: dict[Any, dict[str, Any]] = {}
        for page in range(1, min(max(pages, 1), 10) + 1):
            payload = spansh_p.search_stations(
                filters={}, sorts=sorts, page=page, size=100)
            for r in payload.get("results", []) or []:
                seen[r.get("id", (r.get("name"), r.get("system_name")))] = r
        hits = trade_logic.match_module(list(seen.values()), module_query,
                                        standard_only=standard_only)
        specials = sum(1 for h in hits if h.get("has_special_acquisition"))
        note = None
        if specials:
            note = (f"{specials} station(s) list only special-acquisition stock "
                    "(pre-engineered/tech-broker/Powerplay — verify in-game, "
                    "not a plain credit purchase).")
        stored = []
        try:
            own = journal_p.get_stored_modules(journal_dir)
            if own.get("found"):
                stored = trade_logic.match_stored(own.get("stations", []), module_query)
        except Exception:  # noqa: BLE001
            stored = []
        if stored:
            note = ((note + " " if note else "") +
                    f"You already own {sum(s['match_count'] for s in stored)} matching "
                    "module(s) in storage — transfer instead of buying.")
        return {"ok": True, "query": module_query, "ref": ref,
                "stations_scanned": len(seen),
                "count": len(hits), "stations": hits[:max_results],
                "owned_in_storage": stored,
                "caution": note}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def find_ship(ship_query: str, system_name: str | None = None,
              x: float | None = None, y: float | None = None,
              z: float | None = None, max_results: int = 10,
              pages: int = 4, journal_dir: str | None = None) -> dict[str, Any]:
    """Stations selling a ship near you (live Spansh shipyard lists).

    Scans `pages` x 100 nearest stations (default 4, max 10): Spansh shipyard
    snapshots are sparse, so one page misses stock. Each hit carries a
    `price_note` reminding you to verify the price in-game — ship discounts
    are time-limited and not exposed in Spansh public snapshots.
    """
    try:
        _, ref = _ref_coords(system_name, x, y, z, journal_dir)
        sorts = [{"distance": {"direction": "asc", "distance": ref}}]
        seen: dict[Any, dict[str, Any]] = {}
        for page in range(1, min(max(pages, 1), 10) + 1):
            payload = spansh_p.search_stations(
                filters={}, sorts=sorts, page=page, size=100)
            for r in payload.get("results", []) or []:
                seen[r.get("id", (r.get("name"), r.get("system_name")))] = r
        hits = trade_logic.match_ship(list(seen.values()), ship_query)
        return {"ok": True, "query": ship_query, "ref": ref,
                "stations_scanned": len(seen),
                "count": len(hits), "stations": hits[:max_results],
                "price_note": "Verify ship price in-game — discounts are often time-limited and not reflected in Spansh snapshots."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def station_services(station_name: str, system_name: str | None = None) -> dict[str, Any]:
    """Services/pads/market for a named station (live Spansh).

    Duplicate station names exist across systems: pass `system_name` (full
    name) to disambiguate, otherwise all matches are returned. Flags the
    System Colonisation contact explicitly. Stock snapshots rotate; verify
    in-game before flying.
    """
    try:
        data = spansh_p.quick_search(station_name)
        records = []
        for r in data.get("results", []) or []:
            rec = r.get("record") if isinstance(r, dict) else None
            if isinstance(rec, dict):
                records.append(rec)
        if system_name:
            want = system_name.strip().lower()
            records = [rec for rec in records
                       if str(rec.get("system_name", "")).lower() == want]
        stations = [trade_logic.slim_station(rec) for rec in records]
        return {"ok": True, "query": station_name, "system_filter": system_name,
                "count": len(stations), "stations": stations,
                "note": "Spansh snapshots; verify services in-game before flying."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_colony_progress(journal_dir: str | None = None) -> dict[str, Any]:
    """Colony build scoreboard from your journals (latest depot manifest).

    Per-commodity required/provided/remaining plus totals, overall progress,
    claimed system, your-vs-others tonnage, delivery pace and ETA vs the
    28-day window. Returns found False when no claim/beacon exists yet.
    """
    try:
        return {"ok": True, **journal_p.get_colony_progress(journal_dir)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_stored_modules(journal_dir: str | None = None) -> dict[str, Any]:
    """Modules you own in storage, per station (StoredModules journal events).

    Check here before buying: a stored module only needs a transfer.
    Open outfitting/storage in-game to refresh a station's entry.
    """
    try:
        return {"ok": True, **journal_p.get_stored_modules(journal_dir)}
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


@mcp.tool()
def find_local_opportunities(system_name: str | None = None,
                             radius_ly: float = 40.0,
                             journal_dir: str | None = None) -> dict[str, Any]:
    """What's profitable near you: trade hubs, mission ports, exobio frontier.

    Live EDSM sphere around a system (or your journal location) grouped into
    money-making buckets. Buckets only — follow up with find_commodity or
    station_services before flying.
    """
    try:
        if system_name:
            sphere = edsm_p.sphere_systems(system_name=system_name,
                                           radius_ly=radius_ly)
            ref = system_name
        else:
            loc = journal_p.get_location(journal_dir)
            if not loc.get("found"):
                return {"ok": False,
                        "error": "No journal location; pass system_name."}
            ref = loc.get("system")
            coords = loc.get("star_pos")
            if coords and len(coords) == 3:
                sphere = edsm_p.sphere_systems(x=coords[0], y=coords[1],
                                               z=coords[2], radius_ly=radius_ly)
            else:
                sphere = edsm_p.sphere_systems(system_name=ref,
                                               radius_ly=radius_ly)
        out = trade_logic.classify_systems(sphere)
        return {"ok": True, "reference": ref, "radius_ly": radius_ly,
                "sphere_count": len(sphere), **out,
                "note": "Buckets only; verify markets/missions in-game."}
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


# ---- research foundations (Milestone 1) ----
@mcp.tool()
def create_experiment(
    title: str,
    hypothesis: str,
    method: str,
    parameters: dict[str, Any] | None = None,
    control_design: str | None = None,
) -> dict[str, Any]:
    """Define a bounded scientific experiment with provenance tracking.

    Creates an experiment definition that can be tracked with runs,
    results, and controls. Parameters and control design should be
    minimal and deterministic.
    """
    try:
        exp = research_exp.Experiment.create(
            title=title,
            hypothesis=hypothesis,
            method=method,
            parameters=parameters or {},
            control_design=control_design,
        )
        # Initialize store if not present; use default DB path
        db_path = cfg.SETTINGS.journal_dir / "research_artifacts.db" if cfg.SETTINGS.journal_dir else Path(
            "research_artifacts.db"
        )
        if not db_path.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            research_store.ArtifactStore(db_path)  # creates schema
        else:
            research_store.ArtifactStore(db_path)
        store = research_store.ArtifactStore(db_path)
        store.save_experiment(exp)
        return {
            "ok": True,
            "experiment_id": exp.experiment_id,
            "title": exp.title,
            "hypothesis": exp.hypothesis,
            "method": exp.method,
            "method_version": exp.method_version,
            "parameters": exp.parameters,
            "control_design": exp.control_design,
            "status": exp.status,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def run_experiment(
    experiment_id: str,
    bounded_inputs: dict[str, Any] | None = None,
    random_seed: int | None = None,
) -> dict[str, Any]:
    """Create a new run of a bounded scientific experiment.

    Records the run start time, software version, model/provider metadata
    if applicable, and optional random seed. The agent should invoke
    approved MCP tools to populate results, then call complete_experiment.
    """
    try:
        exp_store = research_store.ArtifactStore(
            Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir
            else Path(cfg.SETTINGS.journal_dir / "research_artifacts.db")
        )
        run = research_exp.ExperimentRun.create(
            experiment_id=experiment_id,
            random_seed=random_seed,
            software_version="ed-mcp/0.1.0",
        )
        exp_store.save_run(run)
        run_dict = run.to_dict()
        run_dict["experiment_id"] = experiment_id
        return {"ok": True, "run": run_dict}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def complete_experiment(
    run_id: str,
    result_summary: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Mark an experiment run as complete with results or error.

    Records completion time, result summary, and any error message.
    The agent should have gathered results from approved MCP tools
    before calling this.
    """
    try:
        exp_store = research_store.ArtifactStore(
            Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir
            else Path(cfg.SETTINGS.journal_dir / "research_artifacts.db")
        )
        run_store = research_store.ArtifactStore(
            Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir
            else Path(cfg.SETTINGS.journal_dir / "research_artifacts.db")
        )
        existing = exp_store.get_run(run_id)
        if existing is None:
            return {"ok": False, "error": f"Run {run_id} not found"}
        completed = existing.complete(
            result_summary=result_summary,
            error_message=error_message,
        )
        exp_store.save_run(completed)
        return {
            "ok": True,
            "run_id": completed.run_id,
            "experiment_id": completed.experiment_id,
            "status": completed.status,
            "start_time_utc": completed.start_time_utc,
            "end_time_utc": completed.end_time_utc,
            "result_summary": completed.result_summary,
            "error_message": completed.error_message,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def save_observation(
    source: str,
    system_name: str | None = None,
    source_record_id: str | None = None,
    coordinates: tuple[float, float, float] | None = None,
    coordinate_reference: str | None = None,
    data_type: str | None = None,
    source_schema_version: str | None = None,
    raw_payload: dict[str, Any] | None = None,
    query_parameters: dict[str, Any] | None = None,
    pagination_cursor: str | None = None,
    completeness_notes: str | None = None,
) -> dict[str, Any]:
    """Save a provenance-tracked source observation to the research store.

    All missing data is explicitly marked rather than silently converted.
    Returns the observation ID and provenance summary.
    """
    try:
        db_path = Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir else Path(
            cfg.SETTINGS.journal_dir / "research_artifacts.db"
        )
        store = research_store.ArtifactStore(db_path)
        prov = research_prov.Provenance.create(
            source=source,
            source_record_id=source_record_id,
            system_name=system_name,
            coordinates=coordinates,
            coordinate_reference=coordinate_reference,
            data_type=data_type,
            source_schema_version=source_schema_version,
            raw_payload=raw_payload,
            query_parameters=query_parameters,
            pagination_cursor=pagination_cursor,
            completeness_notes=completeness_notes,
        )
        obs = research_prov.Observation(
            provenance=prov,
            value=raw_payload,
            is_missing=coordinates is None,
            missing_reason=coordinate_reference if coordinates is None else None,
        )
        obs_id = store.save_observation(obs)
        return {
            "ok": True,
            "observation_id": obs_id,
            "source": prov.source,
            "system_name": prov.system_name,
            "is_missing": obs.is_missing,
            "missing_reason": obs.missing_reason,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_experiment_result(
    run_id: str,
) -> dict[str, Any]:
    """Retrieve a completed experiment run's results with full provenance.

    Returns the stored run with result summary, provenance observations,
    and metadata.
    """
    try:
        db_path = Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir else Path(
            cfg.SETTINGS.journal_dir / "research_artifacts.db"
        )
        store = research_store.ArtifactStore(db_path)
        run = store.get_run(run_id)
        if run is None:
            return {"ok": False, "error": f"Run {run_id} not found"}
        return {
            "ok": True,
            "run_id": run.run_id,
            "experiment_id": run.experiment_id,
            "start_time_utc": run.start_time_utc,
            "end_time_utc": run.end_time_utc,
            "status": run.status,
            "software_version": run.software_version,
            "model_provider": run.model_provider,
            "model_identifier": run.model_identifier,
            "random_seed": run.random_seed,
            "result_summary": run.result_summary,
            "error_message": run.error_message,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def list_experiment_runs(
    experiment_id: str | None = None,
) -> dict[str, Any]:
    """List all runs for an experiment (or all experiments).

    Returns run summaries ordered by start time descending.
    """
    try:
        db_path = Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir else Path(
            cfg.SETTINGS.journal_dir / "research_artifacts.db"
        )
        store = research_store.ArtifactStore(db_path)
        runs = store.list_runs(experiment_id=experiment_id)
        return {
            "ok": True,
            "runs": [r.to_dict() for r in runs],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def list_observations(
    source: str | None = None,
    system_name: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List provenance-tracked observations with filtering.

    Filters by source and/or system name. Never silently converts missing
    values; all observations retain their missing/observed status.
    """
    try:
        db_path = Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir else Path(
            cfg.SETTINGS.journal_dir / "research_artifacts.db"
        )
        store = research_store.ArtifactStore(db_path)
        obs_list = store.list_observations(source=source, system_name=system_name, limit=limit)
        return {
            "ok": True,
            "observations": [
                {
                    "observation_id": i,
                    "source": o.provenance.source,
                    "system_name": o.provenance.system_name,
                    "is_missing": o.is_missing,
                    "missing_reason": o.missing_reason,
                    "retrieval_timestamp_utc": o.provenance.retrieval_timestamp_utc,
                    "observation_type": o.provenance.observation_type,
                    "value_summary": (
                        str(list(o.value or {}).keys())[:20] if o.value is not None else None
                    ),
                }
                for i, o in enumerate(obs_list)
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def query_bounded_region(
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
) -> dict[str, Any]:
    """Query a bounded EDSM sphere region with full provenance tracking.

    Caps results at 200 systems to keep responses bounded. Systems missing
    coordinates are explicitly marked rather than silently dropped. Returns
    region metadata, system list with provenance, and any errors.
    """
    try:
        db_path = Path("research_artifacts.db") if not cfg.SETTINGS.journal_dir else Path(
            cfg.SETTINGS.journal_dir / "research_artifacts.db"
        )
        store = research_store.ArtifactStore(db_path)
        result = research_region.query_region(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
            store=store,
        )
        return {
            "ok": result.ok,
            "center_system": result.center_system,
            "center_coords": result.center_coords,
            "radius_ly": result.radius_ly,
            "systems": [
                {
                    "name": s["name"],
                    "coords": s.get("coords"),
                    "distance": s.get("distance"),
                    "bodyCount": s.get("bodyCount"),
                    "information": s.get("information"),
                    "_provenance": s.get("_provenance"),
                    "is_missing": s.get("is_missing", False),
                    "missing_reason": s.get("missing_reason"),
                }
                for s in result.systems
            ],
            "count": result.count,
            "errors": result.errors,
            "provenance": [p.to_dict() for p in result.provenance],
            "query_parameters": result.query_parameters,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- graph analysis (Milestone 2) ----
@mcp.tool()
def build_system_graph(
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
    max_edge_distance: float = 30.0,
    graph_definition: str = "jump_range_proximity",
) -> dict[str, Any]:
    """Build a jump-range proximity graph for a bounded EDSM sphere.

    Queries EDSM for systems within radius_ly, then constructs edges
    between all pairs within max_edge_distance. Returns graph snapshot
    with nodes, edges, and metadata. Missing coordinates are preserved
    as isolated nodes with explicit missing flags.
    """
    try:
        systems = edsm_p.sphere_systems(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
        )
        snap = graph_logic.GraphSnapshot.build(
            systems=systems,
            max_edge_distance=max_edge_distance,
            graph_definition=graph_definition,
            source_snapshot_id=None,
        )
        return {"ok": True, "graph": snap.to_dict()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def analyze_graph_metrics(
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
    max_edge_distance: float = 30.0,
    graph_definition: str = "jump_range_proximity",
) -> dict[str, Any]:
    """Build a graph and compute structural metrics in one call.

    Returns: connected components, degree distribution, bridges,
    articulation points, betweenness centrality, and motif counts.
    """
    try:
        systems = edsm_p.sphere_systems(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
        )
        snap = graph_logic.GraphSnapshot.build(
            systems=systems,
            max_edge_distance=max_edge_distance,
            graph_definition=graph_definition,
        )
        return {
            "ok": True,
            "graph_definition": graph_definition,
            "max_edge_distance": max_edge_distance,
            "connected_components": graph_logic.connected_components(snap),
            "degree_distribution": graph_logic.degree_distribution(snap),
            "bridges_articulation": graph_logic.bridges_and_articulation_points(snap),
            "betweenness_centrality": graph_logic.betweenness_centrality(snap),
            "motif_counts": graph_logic.motif_counts(snap),
            "graph_metadata": {
                "node_count": snap.node_count,
                "edge_count": snap.edge_count,
                "missing_coordinates": snap.missing_coordinates,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def graph_sensitivity_analysis(
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
    radii: list[float] | None = None,
    graph_definition: str = "jump_range_proximity",
) -> dict[str, Any]:
    """Run graph construction across multiple jump-range radii.

    Returns per-radius metrics for parameter sensitivity testing.
    """
    try:
        systems = edsm_p.sphere_systems(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
        )
        radii_list = radii or [15.0, 20.0, 30.0, 40.0, 50.0]
        results = graph_logic.sensitivity_analysis(
            systems=systems,
            radii=radii_list,
            graph_definition=graph_definition,
        )
        return {"ok": True, "radius_ly": radius_ly, "sensitivity": results}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- spatial analysis (Milestone 3) ----
@mcp.tool()
def find_spatial_clusters(
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
    eps_ly: float = 50.0,
    min_samples: int = 3,
) -> dict[str, Any]:
    """Find DBSCAN spatial clusters in a bounded EDSM sphere.

    Queries EDSM for systems within radius_ly, extracts coordinates,
    then runs DBSCAN with eps_ly and min_samples. Returns clusters,
    noise points, and per-point assignments. Systems without
    coordinates are excluded from clustering but noted.
    """
    try:
        systems = edsm_p.sphere_systems(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
        )
        # Extract points with valid coordinates
        points = []
        missing_coords = 0
        for s in systems:
            coords = s.get("coords")
            if coords:
                try:
                    coord_tuple = (
                        float(coords.get("x", coords[0]) if isinstance(coords, dict) else coords[0]),
                        float(coords.get("y", coords[1]) if isinstance(coords, dict) else coords[1]),
                        float(coords.get("z", coords[2]) if isinstance(coords, dict) else coords[2]),
                    )
                    points.append(
                        spatial_logic.SpatialPoint(
                            system_name=s.get("name", ""),
                            coordinates=coord_tuple,
                        )
                    )
                except (TypeError, ValueError, IndexError):
                    missing_coords += 1
            else:
                missing_coords += 1

        result = spatial_logic.dbscan(points=points, eps_ly=eps_ly, min_samples=min_samples)
        result["missing_coordinates"] = missing_coords
        result["total_systems"] = len(systems)
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def analyze_spatial_geometry(
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
) -> dict[str, Any]:
    """Analyze geometric structure of systems in a bounded EDSM sphere.

    Computes linearity, planarity, spread, centroid, compactness,
    and nearest-neighbor statistics to identify linear arrangements,
    planar structures, or spherical clusters.
    """
    try:
        systems = edsm_p.sphere_systems(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
        )
        points = []
        missing_coords = 0
        for s in systems:
            coords = s.get("coords")
            if coords:
                try:
                    coord_tuple = (
                        float(coords.get("x", coords[0]) if isinstance(coords, dict) else coords[0]),
                        float(coords.get("y", coords[1]) if isinstance(coords, dict) else coords[1]),
                        float(coords.get("z", coords[2]) if isinstance(coords, dict) else coords[2]),
                    )
                    points.append(
                        spatial_logic.SpatialPoint(
                            system_name=s.get("name", ""),
                            coordinates=coord_tuple,
                        )
                    )
                except (TypeError, ValueError, IndexError):
                    missing_coords += 1
            else:
                missing_coords += 1

        geometry = spatial_logic.analyze_geometry(points)
        nn_stats = spatial_logic.nearest_neighbor_stats(points)
        return {
            "ok": True,
            "geometry": {
                "dominant_axis": geometry.dominant_axis,
                "linearity": geometry.linearity,
                "planarity": geometry.planarity,
                "spread": geometry.spread,
                "centroid": geometry.centroid,
                "compactness": geometry.compactness,
            },
            "nearest_neighbor": nn_stats,
            "point_count": len(points),
            "missing_coordinates": missing_coords,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def spatial_sensitivity_analysis(
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
    eps_values: list[float] | None = None,
    min_samples_values: list[int] | None = None,
) -> dict[str, Any]:
    """Run DBSCAN across parameter combinations for sensitivity testing.

    Returns per-parameter-set cluster counts, noise counts, and cluster
    details to assess robustness of spatial patterns.
    """
    try:
        systems = edsm_p.sphere_systems(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
        )
        points = []
        for s in systems:
            coords = s.get("coords")
            if coords:
                try:
                    coord_tuple = (
                        float(coords.get("x", coords[0]) if isinstance(coords, dict) else coords[0]),
                        float(coords.get("y", coords[1]) if isinstance(coords, dict) else coords[1]),
                        float(coords.get("z", coords[2]) if isinstance(coords, dict) else coords[2]),
                    )
                    points.append(
                        spatial_logic.SpatialPoint(
                            system_name=s.get("name", ""),
                            coordinates=coord_tuple,
                        )
                    )
                except (TypeError, ValueError, IndexError):
                    pass
        results = spatial_logic.spatial_sensitivity_analysis(
            points=points,
            eps_values=eps_values,
            min_samples_values=min_samples_values,
        )
        return {"ok": True, "sensitivity": results, "point_count": len(points)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---- temporal analysis (Milestone 4) ----
@mcp.tool()
def aggregate_temporal_events(
    events: list[dict[str, Any]],
    interval_minutes: int = 60,
    system_name: str | None = None,
    event_types: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate timestamped EDDN/journal events into a time series.

    Returns intervals with event-type counts. Systems without timestamps
    are skipped (not silently converted to zero).
    """
    try:
        result = temporal_logic.aggregate_time_series(
            events=events,
            interval_minutes=interval_minutes,
            system_name=system_name,
            event_types=event_types,
        )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def detect_temporal_outliers(
    series: dict[str, dict[str, int]],
    interval: str,
    method: str = "IQR",
    z_threshold: float = 3.0,
) -> dict[str, Any]:
    """Robust outlier detection on event counts for a given interval.

    Methods: 'IQR' (interquartile range) or 'zscore' (standard deviations).
    Returns per-event-type outlier flags and statistics.
    """
    try:
        result = temporal_logic.robust_outlier_detection(
            series=series,
            interval=interval,
            method=method,
            z_threshold=z_threshold,
        )
        return {"ok": True, "interval": interval, "outliers": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def detect_change_points(
    series: dict[str, dict[str, int]],
    interval: str,
    window_size: int = 5,
    sensitivity: float = 1.5,
) -> dict[str, Any]:
    """Detect change points using sliding window mean comparison.

    Compares early vs late window means; flags changes exceeding
    sensitivity * MAD. Works on per-event-type time series.
    """
    try:
        result = temporal_logic.change_point_detection(
            series=series,
            interval=interval,
            window_size=window_size,
            sensitivity=sensitivity,
        )
        return {"ok": True, "interval": interval, "change_points": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def normalize_temporal_activity(
    series: dict[str, dict[str, int]],
    accessibility_data: dict[str, dict[str, Any]] | None = None,
    method: str = "traffic_normalized",
) -> dict[str, Any]:
    """Normalize activity counts by accessibility/traffic indicators.

    Methods: 'traffic_normalized', 'population_normalized', 'raw'.
    Returns normalized series with caveats for missing data.
    """
    try:
        result = temporal_logic.normalize_activity_by_accessibility(
            series=series,
            accessibility_data=accessibility_data,
            method=method,
        )
        return {"ok": True, "normalized_series": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def check_temporal_persistence(
    series1: dict[str, dict[str, int]],
    series2: dict[str, dict[str, int]],
    interval: str,
    min_overlap: float = 0.5,
) -> dict[str, Any]:
    """Check persistence of anomalous patterns across two time windows.

    Returns per-event-type persistence flags with relative proportion change.
    """
    try:
        result = temporal_logic.persistence_check(
            series1=series1,
            series2=series2,
            interval=interval,
            min_overlap=min_overlap,
        )
        return {"ok": True, "interval": interval, "persistence": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
