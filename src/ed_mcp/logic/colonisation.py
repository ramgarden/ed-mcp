"""Colonisation-candidate logic: zero-population, claimable systems.

Frontier colonisation rules change; this module encodes the stable,
checkable core: unpopulated, no permit lock, not already settled, main star
scoopable preferred. Everything is returned with provenance so the LLM can
show *why* each candidate qualifies and what to double-check in-game.
"""
from __future__ import annotations

from typing import Any


def is_claimable_candidate(info: dict[str, Any]) -> tuple[bool, list[str]]:
    """Decide from an EDSM system-info payload. Returns (ok, reasons)."""
    reasons: list[str] = []
    ok = True

    pop = info.get("information", {}).get("population", 0) if info.get("information") else 0
    if pop not in (0, None):
        ok = False
        reasons.append(f"populated (population={pop})")
    else:
        reasons.append("zero population")

    permit = info.get("permitRequired") or info.get("information", {}).get("permitRequired")
    if permit:
        ok = False
        reasons.append("permit locked")

    faction = (info.get("information", {}) or {}).get("faction") or ""
    if faction:
        ok = False
        reasons.append(f"controlled by {faction}")
    else:
        reasons.append("uncontrolled (no faction)")

    stations = info.get("stations") or []
    if stations:
        ok = False
        reasons.append(f"already has {len(stations)} station(s)")
    else:
        reasons.append("no stations")

    return ok, reasons


def dedupe_by_name(systems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for s in systems:
        name = (s.get("name") or "").lower()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(s)
    return out


def summarise_depot(depot: dict[str, Any]) -> dict[str, Any]:
    """Scoreboard for a ColonisationConstructionDepot journal event (pure).

    Returns per-commodity required/provided/remaining/pct plus totals and
    overall progress. Sorted least-complete first so the next haul is obvious.
    """
    rows: list[dict[str, Any]] = []
    total_req = total_prov = 0
    for r in depot.get("ResourcesRequired", []) or []:
        req = int(r.get("RequiredAmount", 0) or 0)
        prov = int(r.get("ProvidedAmount", 0) or 0)
        total_req += req
        total_prov += prov
        rows.append({
            "commodity": r.get("Name_Localised") or r.get("Name"),
            "required": req, "provided": prov,
            "remaining": max(0, req - prov),
            "pct": round(100.0 * prov / req, 1) if req else 100.0,
            "pay_per_t": r.get("Payment"),
            "complete": prov >= req,
        })
    rows.sort(key=lambda t: (t["pct"], -t["remaining"]))
    return {
        "timestamp": depot.get("timestamp"),
        "progress": depot.get("ConstructionProgress", 0.0),
        "complete": bool(depot.get("ConstructionComplete", False)),
        "failed": bool(depot.get("ConstructionFailed", False)),
        "total_required": total_req, "total_provided": total_prov,
        "total_remaining": total_req - total_prov,
        "overall_pct": round(100.0 * total_prov / total_req, 2) if total_req else 0.0,
        "lines_complete": sum(1 for t in rows if t["complete"]),
        "lines_total": len(rows),
        "resources": rows,
    }
