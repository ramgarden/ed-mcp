"""Survey logic: how deeply has a system been scanned — you vs the community.

Grade per system (local journals):
  COMPLETE — FSSAllBodiesFound seen
  PARTIAL  — FSS progress > 0 or body scans, never completed
  VISITED  — jumps only, no scan evidence
  UNVISITED — in a reference sphere but absent from your journals

Community side (live EDSM bodies catalog): count + break-down of catalogued
bodies. A system can be EDSM-catalogued yet locally unvisited — that is the
normal Raxxla-grid-search backlog row. Nothing here locates Raxxla; it only
tracks where looking has (and has not) happened.
"""
from __future__ import annotations

from typing import Any


def rollup_journal_scans(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fold raw journal events into per-system survey rows (pure, testable).

    Keyed by SystemAddress when present, else StarSystem/SystemName.
    """
    rows: dict[str, dict[str, Any]] = {}

    def row(key: str, name: str | None) -> dict[str, Any]:
        r = rows.get(key)
        if r is None:
            r = {"key": key, "system": name, "visits": 0,
                 "fss_progress": 0.0, "fss_complete": False,
                 "body_count": None, "scans": 0, "first_discoveries": 0,
                 "dss_mapped": 0, "bio_logged": 0, "last_visit": None}
            rows[key] = r
        if name and not r["system"]:
            r["system"] = name
        return r

    for ev in events:
        name = ev.get("event")
        addr = ev.get("SystemAddress")
        sys = (ev.get("StarSystem") or ev.get("SystemName") or ev.get("System"))
        key = str(addr) if addr is not None else (f"name:{sys}" if sys else "")
        if not key:
            continue
        if name in ("FSDJump", "Location", "Docked", "SupercruiseExit"):
            r = row(key, sys)
            r["visits"] += 1
            if ev.get("timestamp") and (not r["last_visit"] or ev["timestamp"] > r["last_visit"]):
                r["last_visit"] = ev["timestamp"]
        elif name == "FSSDiscoveryScan":
            r = row(key, ev.get("SystemName") or sys)
            try:
                r["fss_progress"] = max(float(r["fss_progress"]),
                                        float(ev.get("Progress", 0) or 0))
            except (TypeError, ValueError):
                pass
            if ev.get("BodyCount") is not None and r["body_count"] is None:
                try:
                    r["body_count"] = int(ev["BodyCount"])
                except (TypeError, ValueError):
                    pass
        elif name == "FSSAllBodiesFound":
            r = row(key, ev.get("SystemName") or sys)
            r["fss_complete"] = True
            r["fss_progress"] = 1.0
        elif name == "Scan":
            r = row(key, sys)
            r["scans"] += 1
            if ev.get("WasDiscovered") is False:
                r["first_discoveries"] += 1
        elif name == "SAAScanComplete":
            r = row(key, sys)
            r["dss_mapped"] += 1
        elif name == "ScanOrganic":
            r = row(key, sys)
            if ev.get("WasLogged"):
                r["bio_logged"] += 1
    for r in rows.values():
        if r["fss_complete"]:
            r["grade"] = "COMPLETE"
        elif r["fss_progress"] > 0 or r["scans"] > 0:
            r["grade"] = "PARTIAL"
        else:
            r["grade"] = "VISITED"
    return rows


def summarise_bodies_catalog(bodies: list[dict[str, Any]]) -> dict[str, Any]:
    """Break down an EDSM bodies catalog (community scan depth proxy)."""
    by_type: dict[str, int] = {}
    landable = terraformable = 0
    for b in bodies:
        t = str(b.get("subType") or b.get("type") or "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        if b.get("isLandable"):
            landable += 1
        if str(b.get("terraformingState") or "").lower().startswith("terraformable"):
            terraformable += 1
    return {"catalogued": len(bodies), "landable": landable,
            "terraformable": terraformable,
            "types": sorted(by_type.items(), key=lambda kv: -kv[1])[:15]}
