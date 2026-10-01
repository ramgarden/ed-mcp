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
