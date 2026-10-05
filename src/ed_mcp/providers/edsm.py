"""EDSM API client (no key needed for public system/sphere lookups).

Docs: https://www.edsm.net/en/api-v1
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

BASE = "https://www.edsm.net"


def _client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=timeout, headers={"User-Agent": "ed-mcp/0.1"})


def sphere_systems(
    system_name: str | None = None,
    x: float | None = None, y: float | None = None, z: float | None = None,
    radius_ly: float = 15.0,
    min_radius: float = 0.0,
) -> list[dict[str, Any]]:
    """Systems in a sphere. Either system_name (EDSM resolves coords) or x/y/z."""
    params: dict[str, Any] = {
        "radius": radius_ly, "minRadius": min_radius, "showId": 1,
        "showCoordinates": 1, "showInformation": 1, "showPrimaryStar": 1,
    }
    if system_name:
        params["systemName"] = system_name
    elif x is not None and y is not None and z is not None:
        params.update({"x": x, "y": y, "z": z})
    else:
        raise ValueError("Provide system_name or x/y/z coordinates.")
    with _client() as c:
        r = c.get("/api-v1/sphere-systems", params=params)
        r.raise_for_status()
        return r.json()


def cube_systems(x: float, y: float, z: float, size_ly: float = 30.0) -> list[dict[str, Any]]:
    with _client() as c:
        r = c.get("/api-v1/cube-systems", params={
            "x": x, "y": y, "z": z, "size": size_ly,
            "showId": 1, "showCoordinates": 1, "showInformation": 1,
            "showPrimaryStar": 1,
        })
        r.raise_for_status()
        return r.json()


def system_info(system_name: str) -> dict[str, Any]:
    """Detail for one system: population, government, allegiance, stations."""
    with _client() as c:
        r = c.get("/api-v1/system", params={
            "systemName": system_name, "showId": 1, "showCoordinates": 1,
            "showPermit": 1, "showInformation": 1, "showPrimaryStar": 1,
            "showStations": 1, "showBodies": 0,
        })
        r.raise_for_status()
        return r.json()


def systems_info(system_names: list[str]) -> list[dict[str, Any]]:
    """Batch detail for up to ~50 systems (used to filter claimable candidates)."""
    if not system_names:
        return []
    with _client() as c:
        out: list[dict[str, Any]] = []
        for i in range(0, len(system_names), 50):
            chunk = system_names[i:i + 50]
            r = c.get("/api-v1/systems", params={
                "systemName[]": chunk, "showId": 1, "showCoordinates": 1,
                "showPermit": 1, "showInformation": 1, "showPrimaryStar": 1,
            })
            r.raise_for_status()
            data = r.json()
            out.extend(data if isinstance(data, list) else [data])
        return out


def station_outfitting_near(
    system_name: str | None = None,
    x: float | None = None, y: float | None = None, z: float | None = None,
    radius_ly: float = 50.0,
) -> list[dict[str, Any]]:
    """Stations endpoint wrapper: EDSM /api-v1/stations around a sphere.

    Note: EDSM stations search is best-effort; Spansh is preferred for
    module-stock queries. This returns station list with services where known.
    """
    params: dict[str, Any] = {"radius": radius_ly}
    if system_name:
        params["systemName"] = system_name
    elif x is not None:
        params.update({"x": x, "y": y, "z": z})
    with _client() as c:
        r = c.get("/api-v1/stations", params=params)
        if r.status_code == 404:  # endpoint shape varies; surface gracefully
            return []
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return data.get("stations", [data])
        return data


SYS_V1 = "https://www.edsm.net/api-system-v1"


def system_bodies(system_name: str) -> dict[str, Any]:
    """Catalogued bodies for a system (EDSM api-system-v1/bodies).

    This is what *other players* (via EDB/EDDN feeds into EDSM) have
    catalogued — the community side of 'has anyone scanned this deeply'.
    Throttled server-side (~700/min); call sparingly.
    """
    with httpx.Client(base_url=SYS_V1, timeout=30.0,
                      headers={"User-Agent": "ed-mcp/0.1"}) as c:
        r = c.get("/bodies", params={"systemName": system_name})
        r.raise_for_status()
        data = r.json()
    if isinstance(data, list):  # ambiguous/unknown name
        return {"name": system_name, "bodies": [], "ambiguous": data[:5]}
    bodies = data.get("bodies", []) if isinstance(data, dict) else []
    return {"name": (data.get("name") if isinstance(data, dict) else system_name),
            "id": (data.get("id") if isinstance(data, dict) else None),
            "count": len(bodies), "bodies": bodies}


def system_estimated_value(system_name: str) -> dict[str, Any]:
    """EDSM estimated scan value for a system (explorer prioritisation)."""
    with httpx.Client(base_url=SYS_V1, timeout=30.0,
                      headers={"User-Agent": "ed-mcp/0.1"}) as c:
        r = c.get("/estimated-value", params={"systemName": system_name})
        r.raise_for_status()
        data = r.json()
    return data if isinstance(data, dict) else {"name": system_name, "value": data}
