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


def search_systems(filters: dict[str, Any] | None = None,
                   sorts: list[dict[str, Any]] | None = None,
                   page: int = 1) -> dict[str, Any]:
    """POST /search/systems — flexible systems search.

    Example filters: {"population": {"value": [0, 0]}} for unpopulated.
    """
    body: dict[str, Any] = {"filters": filters or {}, "sorts": sorts or [], "page": page}
    with _client() as c:
        r = c.post("/search/systems", json=body)
        r.raise_for_status()
        return r.json()


def search_stations(filters: dict[str, Any] | None = None,
                    sorts: list[dict[str, Any]] | None = None,
                    page: int = 1) -> dict[str, Any]:
    """POST /search/stations — stations search (pads, services, modules)."""
    body: dict[str, Any] = {"filters": filters or {}, "sorts": sorts or [], "page": page}
    with _client() as c:
        r = c.post("/search/stations", json=body)
        r.raise_for_status()
        return r.json()


def nearest_stations(x: float, y: float, z: float, max_results: int = 10) -> dict[str, Any]:
    """Stations sorted by distance from coordinates (large pads first is caller-side)."""
    return search_stations(
        filters={},
        sorts=[{"distance": {"direction": "asc", "distance": {"x": x, "y": y, "z": z}}}],
        page=1,
    )


def systems_in_cube(x: float, y: float, z: float, size: float = 30.0) -> dict[str, Any]:
    """Systems inside a cube centred on x/y/z (Spansh 'cube' filter)."""
    return search_systems(filters={"cube": {"value": [x - size / 2, y - size / 2,
                                                        z - size / 2, size]}})
