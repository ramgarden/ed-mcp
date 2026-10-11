"""Colonisation logic: claimable systems + construction scoreboard.

Frontier colonisation rules change; this module encodes the stable,
checkable core: unpopulated, no permit lock, not already settled, main star
scoopable preferred. Everything is returned with provenance so the LLM can
show *why* each candidate qualifies and what to double-check in-game.

The scoreboard reads ColonisationConstructionDepot events (whole-depot
manifest, all haulers) plus ColonisationContribution events (yours only):
the gap between depot ProvidedAmount and your contributions is fellow
haulers in open play.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def summarise_progress(depot_events: list[dict[str, Any]],
                       contrib_events: list[dict[str, Any]],
                       claim_events: list[dict[str, Any]],
                       now_iso: str | None = None) -> dict[str, Any]:
    """Full construction picture: depot board + claim + your pace + ETA.

    Pure (testable): pass filtered journal events. Depot ProvidedAmount
    counts everyone's deliveries; Contributions count only yours.
    """
    if not depot_events:
        return {"found": False,
                "hint": "No ColonisationConstructionDepot events. Dock at the colony ship to log one."}
    board = summarise_depot(depot_events[-1])
    claim = next((e for e in claim_events
                  if e.get("event") == "ColonisationSystemClaim"), None)
    beacon = next((e for e in claim_events
                   if e.get("event") == "ColonisationBeaconDeployed"), None)
    mine = 0
    for ev in contrib_events:
        for c in ev.get("Contributions", []) or []:
            mine += int(c.get("Amount", 0) or 0)
    now = _parse_ts(now_iso) or datetime.now(timezone.utc)
    t0 = _parse_ts(depot_events[0].get("timestamp"))
    days_elapsed = max(((now - t0).total_seconds() / 86400) if t0 else 0, 1 / 24)
    rate = mine / days_elapsed if contrib_events else 0.0
    remaining = board["total_remaining"]
    days_left = max(0.0, 28.0 - days_elapsed)
    board.update({
        "found": True,
        "remaining": remaining,
        "claimed_system": (claim or {}).get("StarSystem"),
        "claimed_at": (claim or {}).get("timestamp"),
        "beacon_at": (beacon or {}).get("timestamp"),
        "your_contributed_t": mine,
        "others_contributed_t": max(0, board["total_provided"] - mine),
        "contribution_events": len(contrib_events),
        "rate_t_per_day": round(rate, 1),
        "days_elapsed": round(days_elapsed, 2),
        "days_left": round(days_left, 2),
    })
    if remaining <= 0:
        board["eta"] = "complete"
    elif rate > 0:
        eta_days = remaining / rate
        board["eta_days"] = round(eta_days, 2)
        board["vs_deadline_days"] = round(eta_days - days_left, 2)
        board["needed_pace_t_per_day"] = (
            round(remaining / days_left, 1) if days_left > 0 else None)
    return board
