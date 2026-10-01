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
