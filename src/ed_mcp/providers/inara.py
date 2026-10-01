"""Inara API client (requires INARA_API_KEY).

Docs: https://inara.cz/settings-api/ — JSON API, commander name + API key auth.
Without a key every function returns {"configured": False, ...} so the LLM can
tell the user how to enable it instead of failing obscurely.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

BASE = "https://inara.cz/eliteapi/v1"


def is_configured(api_key: str | None = None) -> bool:
    return bool(api_key or os.environ.get("INARA_API_KEY"))


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            "User-Agent": "ed-mcp/0.1"}


def call(events: list[dict[str, Any]], commander: str = "ed-mcp",
         api_key: str | None = None) -> dict[str, Any]:
    key = api_key or os.environ.get("INARA_API_KEY", "")
    if not key:
        return {"configured": False,
                "hint": "Set INARA_API_KEY (https://inara.cz/settings-api/) to use Inara tools."}
    body = {"header": {"appName": "ed-mcp", "appVersion": "0.1.0",
                       "commanderName": commander, "APIkey": key},
            "events": events}
    with httpx.Client(base_url=BASE, timeout=20.0, headers=_headers(key)) as c:
        r = c.post("/", json=body)
        r.raise_for_status()
        return r.json()


def search_nearest(system_name: str, search: str = "station",
                   commander: str = "ed-mcp",
                   api_key: str | None = None) -> dict[str, Any]:
    """getNearestStations / systems / bodies / ... via generic event."""
    # Inara event names: getSystem, getStation, searchSystems, searchStations...
    return call([{"eventName": "searchSystems" if search == "system" else "searchStations",
                  "eventTimestamp": "2026-01-01T00:00:00Z",
                  "eventData": {"searchName": system_name}}],
                commander=commander, api_key=api_key)
