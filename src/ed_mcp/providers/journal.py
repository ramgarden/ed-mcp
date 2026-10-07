"""Local Elite Dangerous journal parsing.

Journals are JSON-lines files named ``Journal.<timestamp>.log`` plus helper
files (``Status.json``, ``NavRoute.json``, ``Outfitting.json``, ``Shipyard.json``,
``Market.json``). See https://elite-journal.readthedocs.io/

All helpers degrade gracefully to ``{"found": False, ...}`` when the folder or
files are missing, so the LLM asks the user for a path instead of guessing.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any


def resolve_journal_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    override = os.environ.get("ED_JOURNAL_DIR")
    if override:
        return Path(override).expanduser()
    userprofile = os.environ.get("USERPROFILE", "")
    candidates = []
    if userprofile:
        candidates.append(
            Path(userprofile) / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
        )
    candidates.append(Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous")
    for c in candidates:
        if c.exists():
            return c
    return candidates[0] if candidates else Path(".")


def journal_files(journal_dir: Path) -> list[Path]:
    return sorted(Path(journal_dir).glob("Journal.*.log"))


def _iter_events(journal_dir: Path):
    for jf in journal_files(journal_dir):
        try:
            with open(jf, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


RELEVANT_EVENTS = {
    "LoadGame", "Location", "FSDJump", "Docked", "Undocked", "SupercruiseEntry",
    "SupercruiseExit", "Touchdown", "Liftoff", "Rank", "Progress", "Loadout",
    "Outfitting", "ShipyardBuy", "ShipyardSwap", "ModuleBuy", "ModuleSell",
    "MarketBuy", "MarketSell", "MissionCompleted", "RankUp", "Promotion",
}


def get_status(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Commander name, current system/station, ship, credits summary."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir),
                "hint": "Journal folder not found. Set ED_JOURNAL_DIR or copy journals."}
    commander = location = ship = None
    credits = None
    ranks: dict[str, Any] = {}
    for ev in _iter_events(jdir):
        name = ev.get("event")
        if name == "LoadGame":
            commander = ev.get("Commander")
            ship = ev.get("Ship") or ship
            credits = ev.get("Credits", credits)
        elif name in ("Location", "FSDJump", "Docked"):
            location = ev
            if ev.get("Ship"):
                ship = ev.get("Ship")
        elif name in ("Rank", "Progress"):
            ranks.update({k: v for k, v in ev.items() if k != "event" and k != "timestamp"})
        elif name == "Loadout":
            ship = ev.get("Ship") or ship
    if commander is None and location is None:
        files = journal_files(jdir)
        return {"found": False, "journal_dir": str(jdir),
                "files_seen": len(files),
                "hint": "No journal events parsed. Is this the right folder?"}
    system = location.get("StarSystem") if location else None
    station = location.get("StationName") if location else None
    coords = location.get("StarPos") if location else None
    return {
        "found": True,
        "journal_dir": str(jdir),
        "commander": commander,
        "system": system,
        "station": station,
        "ship": ship,
        "credits": credits,
        "star_pos": coords,
        "ranks": ranks,
        "last_event": location.get("timestamp") if location else None,
    }


def get_location(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Most recent Location/FSDJump/Docked event with coordinates."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    latest: dict[str, Any] | None = None
    for ev in _iter_events(jdir):
        if ev.get("event") in ("Location", "FSDJump", "Docked", "SupercruiseExit"):
            latest = ev
    if not latest:
        return {"found": False, "journal_dir": str(jdir),
                "hint": "No Location/FSDJump/Docked event found."}
    return {
        "found": True,
        "system": latest.get("StarSystem"),
        "system_address": latest.get("SystemAddress"),
        "star_pos": latest.get("StarPos"),
        "station": latest.get("StationName"),
        "station_type": latest.get("StationType"),
        "body": latest.get("Body") or latest.get("BodyName"),
        "event": latest.get("event"),
        "timestamp": latest.get("timestamp"),
    }


def get_loadout(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Latest Loadout event: ship type + modules."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    latest: dict[str, Any] | None = None
    for ev in _iter_events(jdir):
        if ev.get("event") == "Loadout":
            latest = ev
    if not latest:
        return {"found": False, "journal_dir": str(jdir),
                "hint": "No Loadout event yet. Open outfitting in-game to generate one."}
    modules = [
        {"slot": m.get("Slot"), "item": m.get("Item"), "on": m.get("On"),
         "priority": m.get("Priority"), "health": m.get("Health"),
         "value": m.get("Value")}
        for m in latest.get("Modules", [])
    ]
    return {
        "found": True,
        "ship": latest.get("Ship"),
        "ship_name": latest.get("ShipName"),
        "ship_ident": latest.get("ShipIdent"),
        "hull_value": latest.get("HullValue"),
        "modules_value": latest.get("ModulesValue"),
        "rebuy": latest.get("Rebuy"),
        "modules": modules,
        "timestamp": latest.get("timestamp"),
    }


def get_history(limit: int = 25, journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Most recent relevant events, newest first."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    kept: list[dict[str, Any]] = []
    for ev in _iter_events(jdir):
        if ev.get("event") in RELEVANT_EVENTS:
            kept.append(ev)
    kept.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    slim = []
    for ev in kept[: max(1, min(limit, 200))]:
        d = {"event": ev.get("event"), "timestamp": ev.get("timestamp")}
        for k in ("StarSystem", "StationName", "Ship", "Commander", "Credits",
                  "Body", "BodyName", "StationType", "StarPos", "SystemAddress",
                  "Module", "SellItem", "BuyItem", "Count", "Price", "ShipType"):
            if k in ev:
                d[k] = ev[k]
        slim.append(d)
    return {"found": True, "journal_dir": str(jdir), "events": slim, "count": len(slim)}


CARGO_RACK_T_BY_CLASS = {1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64, 7: 128, 8: 256}


def _read_aux(jdir: Path, name: str) -> dict[str, Any]:
    """Read a journal-folder JSON snapshot (Cargo/Market/Outfitting/...)."""
    path = jdir / name
    if not path.exists():
        return {"found": False, "file": name,
                "hint": f"{name} not present. Dock/open the relevant panel in-game to generate it."}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"found": True, "file": name, "data": json.load(fh)}
    except (OSError, json.JSONDecodeError) as exc:
        return {"found": False, "file": name, "error": str(exc)[:200]}


def cargo_capacity_of_modules(modules: list[dict[str, Any]]) -> int:
    """Sum cargo-rack capacity from a Loadout modules list."""
    import re
    total = 0
    for m in modules or []:
        item = str(m.get("Item") or m.get("item") or "").lower()
        if "cargorack" in item.replace(" ", ""):
            mm = re.search(r"size(\d)", item)
            if mm:
                total += CARGO_RACK_T_BY_CLASS.get(int(mm.group(1)), 0)
    return total


def get_cargo_hold(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Current cargo manifest (Cargo.json) + computed rack capacity."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    cargo = _read_aux(jdir, "Cargo.json")
    loadout = get_loadout(jdir)
    capacity = cargo_capacity_of_modules(loadout.get("modules", [])) if loadout.get("found") else 0
    manifest = (cargo.get("data") or {}).get("Inventory", []) if cargo.get("found") else []
    used = sum(int(i.get("Count", 0)) for i in manifest if isinstance(i, dict))
    return {"found": True, "capacity_t": capacity, "used_t": used,
            "free_t": max(0, capacity - used), "inventory": manifest,
            "ship": loadout.get("ship"), "timestamp": (cargo.get("data") or {}).get("timestamp")}


def get_station_market(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Live station market from Market.json (what THIS docked station trades now)."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    doc = _read_aux(jdir, "Market.json")
    if not doc.get("found"):
        return doc
    data = doc["data"]
    items = data.get("Items", []) if isinstance(data, dict) else []
    slim = [{"name": i.get("Name") or i.get("Name_Localised"), "buy": i.get("BuyPrice"),
             "sell": i.get("SellPrice"), "supply": i.get("Stock"),
             "supply_bracket": i.get("StockBracket"), "demand": i.get("Demand"),
             "demand_bracket": i.get("DemandBracket")}
            for i in items if isinstance(i, dict)]
    return {"found": True, "station": data.get("StationName"), "system": data.get("StarSystem"),
            "timestamp": data.get("timestamp"), "count": len(slim), "items": slim}


def get_station_outfitting(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Outfitting stock at current station (Outfitting.json + ModulesInfo.json)."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    return {"found": True,
            "outfitting": _read_aux(jdir, "Outfitting.json"),
            "modules_info": _read_aux(jdir, "ModulesInfo.json")}


def get_station_shipyard(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Shipyard stock at current station (Shipyard.json)."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    return {"found": True, "shipyard": _read_aux(jdir, "Shipyard.json")}


def get_odyssey_state(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """On-foot state: Backpack/ShipLocker files + latest suit/loadout events."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    suit = suit_loadout = None
    for ev in _iter_events(jdir):
        if ev.get("event") in ("SuitLoadout", "SwitchSuitLoadout"):
            suit_loadout = ev
        elif ev.get("event") == "CreateSuitLoadout":
            suit = ev
    return {"found": True,
            "backpack": _read_aux(jdir, "Backpack.json"),
            "ship_locker": _read_aux(jdir, "ShipLocker.json"),
            "last_suit_loadout": suit_loadout, "last_suit_event": suit}


def get_fleet_overview(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Every ship seen in Loadout events + computed cargo per ship (latest first)."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    latest: dict[tuple, dict[str, Any]] = {}
    for ev in _iter_events(jdir):
        if ev.get("event") == "Loadout":
            key = (ev.get("Ship"), ev.get("ShipName"), ev.get("ShipIdent"))
            latest[key] = ev
    ships = []
    for (ship, name, ident), ev in sorted(latest.items(),
                                          key=lambda kv: kv[1].get("timestamp", ""),
                                          reverse=True):
        ships.append({"ship": ship, "name": name, "ident": ident,
                      "cargo_t": cargo_capacity_of_modules(
                          [{"Item": m.get("Item")} for m in ev.get("Modules", [])]),
                      "timestamp": ev.get("timestamp")})
    return {"found": True, "count": len(ships), "ships": ships}


def get_wallet_summary(limit: int = 5000,
                       journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Credits now + sums of recent trade/mission/carrier flows."""
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    status = get_status(jdir)
    spent_buy = earned_sell = missions = 0
    n_buy = n_sell = n_missions = 0
    for i, ev in enumerate(_iter_events(jdir)):
        if i > limit * 20:
            break
        name = ev.get("event")
        if name == "MarketBuy":
            spent_buy += int(ev.get("TotalCost", 0) or 0)
            n_buy += 1
        elif name == "MarketSell":
            earned_sell += int(ev.get("TotalSale", 0) or 0)
            n_sell += 1
        elif name == "MissionCompleted":
            for k in ("Reward", "Donation"):
                if isinstance(ev.get(k), int):
                    missions += ev[k]
            n_missions += 1
    return {"found": True, "credits": status.get("credits"),
            "commander": status.get("commander"),
            "market_buy_total": spent_buy, "market_buy_events": n_buy,
            "market_sell_total": earned_sell, "market_sell_events": n_sell,
            "mission_rewards_total": missions, "mission_events": n_missions}


def get_colony_depot(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Latest ColonisationConstructionDepot event (colony build manifest).

    Returns the raw manifest rows (Name/RequiredAmount/ProvidedAmount/Payment)
    plus progress flags. Use logic.colonisation.summarise_depot for the
    scoreboard; returns found False when no claim/beacon exists yet.
    """
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    latest: dict[str, Any] | None = None
    for ev in _iter_events(jdir):
        if ev.get("event") == "ColonisationConstructionDepot":
            latest = ev
    if not latest:
        return {"found": False, "journal_dir": str(jdir),
                "hint": "No ColonisationConstructionDepot event yet. "
                        "Register a claim, deploy the beacon, and dock at the colony ship."}
    return {"found": True, "journal_dir": str(jdir), "depot": latest}


def get_stored_modules(journal_dir: Path | str | None = None) -> dict[str, Any]:
    """Modules in storage across all visited stations (StoredModules events).

    Keeps the latest event per station (MarketID). Identity lives in the
    `Name` $symbol field (Name_Localised is often generic like "FSD"), so
    both are returned. Open outfitting/storage in-game to refresh a station.
    """
    jdir = Path(journal_dir) if journal_dir else resolve_journal_dir()
    if not jdir.exists():
        return {"found": False, "journal_dir": str(jdir)}
    latest: dict[Any, dict[str, Any]] = {}
    for ev in _iter_events(jdir):
        if ev.get("event") == "StoredModules":
            key = ev.get("MarketID") or (ev.get("StationName"), ev.get("StarSystem"))
            latest[key] = ev
    stations: list[dict[str, Any]] = []
    total = 0
    for ev in latest.values():
        items = []
        for it in ev.get("Items", []) or []:
            if not isinstance(it, dict):
                continue
            total += 1
            items.append({
                "symbol": it.get("Name"),
                "name": it.get("Name_Localised") or it.get("Name"),
                "hot": bool(it.get("Hot", False)),
                "transfer_cost": it.get("TransferCost"),
                "transfer_time_s": it.get("TransferTime"),
            })
        if items:
            stations.append({
                "station": ev.get("StationName"),
                "system": ev.get("StarSystem"),
                "timestamp": ev.get("timestamp"),
                "items": items,
            })
    stations.sort(key=lambda s: s["station"] or "")
    return {"found": True, "journal_dir": str(jdir),
            "stations_with_storage": len(stations), "modules_stored": total,
            "stations": stations}
