"""Inara API client (requires INARA_API_KEY + approved app access).

Docs: https://inara.cz/inapi/doc/ — JSON API, API key in the header body.
Correct endpoint is https://inara.cz/inapi/v1/ (not /eliteapi/v1, which 503s).
Without a key every function returns {"configured": False, ...} so the LLM can
tell the user how to enable it instead of failing obscurely.
If the key's app has no event access, Inara returns HTTP 200 with
header.eventStatus 400 "This application has no access allowed" — surfaced
verbatim with a hint instead of crashing.
"""
from __future__ import annotations

import os
import urllib.parse
from typing import Any

import httpx

BASE = "https://inara.cz/inapi/v1"


def is_configured(api_key: str | None = None) -> bool:
    return bool(api_key or os.environ.get("INARA_API_KEY"))


def _default_commander(commander: str = "ed-mcp") -> str:
    """Prefer the journal commander (Inara expects the key owner's name)."""
    if commander and commander != "ed-mcp":
        return commander
    try:
        from ed_mcp.providers import journal as journal_p
        status = journal_p.get_status()
        if status.get("found") and status.get("commander"):
            return str(status["commander"])
    except Exception:  # noqa: BLE001
        pass
    return commander


def call(events: list[dict[str, Any]], commander: str = "ed-mcp",
         api_key: str | None = None) -> dict[str, Any]:
    key = api_key or os.environ.get("INARA_API_KEY", "")
    if not key:
        return {"configured": False,
                "hint": "Set INARA_API_KEY (https://inara.cz/settings-api/) to use Inara tools."}
    commander = _default_commander(commander)
    body = {"header": {"appName": "ed-mcp", "appVersion": "0.1.0",
                       "commanderName": commander, "APIkey": key},
            "events": events}
    with httpx.Client(base_url=BASE, timeout=20.0,
                      headers={"Content-Type": "application/json",
                               "User-Agent": "ed-mcp/0.1"}) as c:
        r = c.post("/", json=body)
        r.raise_for_status()
        data = r.json()
    header = data.get("header", {}) if isinstance(data, dict) else {}
    if header.get("eventStatus") == 400 and "no access" in str(header.get("eventStatusText", "")).lower():
        data["hint"] = ("Inara key works but this app has no event access. "
                        "At https://inara.cz/settings-api/ open your ed-mcp app and "
                        "enable access for search/get events, then retry.")
    return data


def search_nearest(system_name: str, search: str = "station",
                   commander: str = "ed-mcp",
                   api_key: str | None = None) -> dict[str, Any]:
    """getNearestStations / systems / bodies / ... via generic event."""
    # Inara event names: getSystem, getStation, searchSystems, searchStations...
    return call([{"eventName": "searchSystems" if search == "system" else "searchStations",
                  "eventTimestamp": "2026-10-04T00:00:00Z",
                  "eventData": {"searchName": system_name}}],
                commander=commander, api_key=api_key)


def website_search_urls(system_name: str = "", commodity: str = "",
                        station_name: str = "") -> dict[str, str]:
    """Inara website search links (no API key needed) — open in a browser.

    Mirrors what the Inara website search offers when the API app has no access:
    nearest stations, commodity search, station search.
    """
    base = "https://inara.cz/elite"
    urls: dict[str, str] = {}
    if system_name:
        q = urllib.parse.quote(system_name)
        urls["nearest"] = f"{base}/nearest/?search={q}"
        urls["system_search"] = f"{base}/search/?search={q}"
    if station_name or system_name:
        q = urllib.parse.quote(station_name or system_name)
        urls["stations"] = f"{base}/stations/?search={q}"
    if commodity:
        q = urllib.parse.quote(commodity)
        ref = f"&searchref={urllib.parse.quote(system_name)}" if system_name else ""
        urls["commodities"] = f"{base}/commodities/?search={q}{ref}"
    if not urls:
        urls["search"] = f"{base}/search/"
    return urls


def website_search(system_name: str = "", commodity: str = "",
                   station_name: str = "") -> dict[str, Any]:
    """Best-effort fetch of Inara website search pages (no key).

    Returns the URLs plus page titles/snippets so the LLM can cite them.
    Pages are JS-assisted; if parsing yields nothing, the URLs are still
    returned for the user to open. Never fabricates station/stock rows.
    """
    urls = website_search_urls(system_name, commodity, station_name)
    pages: list[dict[str, Any]] = []
    with httpx.Client(timeout=20.0, headers={"User-Agent": "ed-mcp/0.1"},
                      follow_redirects=True) as c:
        for label, url in urls.items():
            try:
                r = c.get(url)
                text = r.text or ""
                title = ""
                low = text.lower()
                i = low.find("<title>")
                if i >= 0:
                    title = text[i + 7:low.find("</title>", i + 7)][:200].strip()
                pages.append({"link": label, "url": url, "status": r.status_code,
                              "title": title, "length": len(text),
                              "blocked_hint": "login/captcha/JS" if r.status_code != 200 else ""})
            except Exception as exc:  # noqa: BLE001
                pages.append({"link": label, "url": url, "error": str(exc)[:200]})
    return {"urls": urls, "pages": pages,
            "note": "Website fallback when the Inara API app has no access; verify stock in-game."}
