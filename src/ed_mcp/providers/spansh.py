"""Spansh API client.

Docs: https://spansh.co.uk/api
Spansh exposes rich systems/stations search (used by traders/explorers).
Public search endpoints accept JSON bodies; results paginate.
"""
from __future__ import annotations

from typing import Any

import httpx

BASE = "https://spansh.co.uk/api"


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=timeout,
                        headers={"User-Agent": "ed-mcp/0.1", "Content-Type": "application/json"})


def _translate_search(filters: dict[str, Any] | None,
                      sorts: list[dict[str, Any]] | None,
                      page: int, size: int,
                      x: float | None = None, y: float | None = None,
                      z: float | None = None) -> dict[str, Any]:
    """Translate legacy ed-mcp search args to current Spansh search payload.

    Current API: POST /systems/search and /stations/search with
    {filters, sort, size, page (0-based), reference_coords}.
    Legacy callers pass sorts=[{"distance": {"direction": ..., "distance": {x,y,z}}}]
    and 1-based page; both shapes are accepted here.
    """
    sort: list[dict[str, Any]] = []
    ref: dict[str, Any] | None = None
    for s in sorts or []:
        if "distance" in s:
            d = s["distance"] or {}
            direction = d.get("direction", "asc")
            sort.append({"distance": {"direction": direction}})
            coords = d.get("distance") or {}
            if isinstance(coords, dict) and {"x", "y", "z"} <= set(coords):
                ref = {"x": coords["x"], "y": coords["y"], "z": coords["z"]}
        else:
            sort.append(s)
    if ref is None and x is not None and y is not None and z is not None:
        ref = {"x": x, "y": y, "z": z}
    body: dict[str, Any] = {
        "filters": filters or {},
        "sort": sort,
        "size": size,
        "page": max(0, page - 1),
    }
    if ref is not None:
        body["reference_coords"] = ref
    return body


def search_systems(filters: dict[str, Any] | None = None,
                   sorts: list[dict[str, Any]] | None = None,
                   page: int = 1, size: int = 20,
                   x: float | None = None, y: float | None = None,
                   z: float | None = None) -> dict[str, Any]:
    """POST /systems/search — flexible systems search.

    Example filters: {"population": {"value": [0, 0]}} for unpopulated.
    """
    body = _translate_search(filters, sorts, page, size, x, y, z)
    with _client() as c:
        r = c.post("/systems/search", json=body)
        r.raise_for_status()
        return r.json()


def search_stations(filters: dict[str, Any] | None = None,
                    sorts: list[dict[str, Any]] | None = None,
                    page: int = 1, size: int = 20,
                    x: float | None = None, y: float | None = None,
                    z: float | None = None) -> dict[str, Any]:
    """POST /stations/search — stations search (pads, services, market)."""
    body = _translate_search(filters, sorts, page, size, x, y, z)
    with _client() as c:
        r = c.post("/stations/search", json=body)
        r.raise_for_status()
        return r.json()


def nearest_stations(x: float, y: float, z: float, max_results: int = 10) -> dict[str, Any]:
    """Stations sorted by distance from coordinates (large pads first is caller-side)."""
    return search_stations(
        filters={},
        sorts=[{"distance": {"direction": "asc", "distance": {"x": x, "y": y, "z": z}}}],
        page=1,
        size=max_results,
    )


def quick_search(q: str) -> dict[str, Any]:
    """GET /search?q= — type-ahead across systems, bodies, stations."""
    with _client() as c:
        r = c.get("/search", params={"q": q})
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {"results": data}


def systems_in_cube(x: float, y: float, z: float, size: float = 30.0) -> dict[str, Any]:
    """Systems inside a cube centred on x/y/z (Spansh 'cube' filter)."""
    return search_systems(filters={"cube": {"value": [x - size / 2, y - size / 2,
                                                        z - size / 2, size]}})


def search_bodies(filters: dict[str, Any] | None = None,
                  sorts: list[dict[str, Any]] | None = None,
                  page: int = 1, size: int = 20,
                  x: float | None = None, y: float | None = None,
                  z: float | None = None) -> dict[str, Any]:
    """POST /bodies/search — exploration search (same payload shape as stations)."""
    body = _translate_search(filters, sorts, page, size, x, y, z)
    with _client() as c:
        r = c.post("/bodies/search", json=body)
        r.raise_for_status()
        return r.json()
