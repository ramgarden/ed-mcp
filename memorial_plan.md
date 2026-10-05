# Noah James Memorial — Tier 1 Orbital Outpost Plan (live ed-mcp rebuild)

Source: local ed-mcp service, live EDSM + EDDN attempts on 2026-10-04. No systems invented; gaps stated where live APIs gave no data.

## 1. Claimable system search — strictly 15 ly

### 1a. Reference: Ascella (strict, as requested)
Call: `edsm.sphere_systems(system_name="Ascella", radius_ly=15.0)` → 48 systems.
Batch detail: `edsm.systems_info(names)` + `colonisation.is_claimable_candidate()` (zero-pop, no faction, no stations, no permit).

Result: **0 claimable within strictly 15 ly of Ascella.** All 48 are populated, e.g.:
- Ascella itself 0.00 ly — pop 67,051,227 — Diamond Frogs — Industrial/Refinery
- Alrai Sector QN-K a8-2 4.13 ly — pop 200,160 — Industrial
- Nijotec 5.10 ly — pop 31,326 — Colony
- Lowat Yuan 5.14 ly — pop 67,945 — Industrial
- …full 48-system sphere returned live; none with population=0.

So a strict-Ascella memorial site does not exist in current EDSM data.

### 1b. Allowed alternative: Kaus Australis (Sagittarius Teapot)
Call: `edsm.sphere_systems(system_name="Kaus Australis", radius_ly=15.0)` → 54 systems, 14 claimable. Kaus Borealis checked too: 22 systems, 0 claimable.

All 14 completely unpopulated (0 pop, no faction, no stations) within 15 ly of Kaus Australis:

| # | System | Dist to Kaus Australis | Coords (x,y,z) |
|---|--------|------------------------|----------------|
| 1 | Scorpii Sector YF-O a6-2 | 4.43 ly | -3.22, -26.56, 140.66 |
| 2 | Scorpii Sector CM-M a7-1 | 7.67 ly | -3.34, -30.16, 145.47 |
| 3 | Scorpii Sector ZF-O a6-3 | 7.72 ly | 7.22, -28.28, 136.78 |
| 4 | Scorpii Sector VZ-P a5-0 | 8.12 ly | 5.16, -27.78, 134.12 |
| 5 | Scorpii Sector ZF-O a6-0 | 8.64 ly | 8.59, -27.56, 136.88 |
| 6 | Scorpii Sector VZ-P a5-2 | 9.79 ly | 6.84, -26.66, 133.00 |
| 7 | Scorpii Sector ZF-O a6-1 | 9.98 ly | 8.22, -29.94, 135.16 |
| 8 | Scorpii Sector DM-M a7-0 | 11.31 ly | 6.06, -33.31, 147.94 |
| 9 | Scorpii Sector XF-O a6-1 | 12.24 ly | -9.91, -30.84, 142.69 |
| 10 | Scorpii Sector DM-M a7-2 | 14.04 ly | 11.28, -30.22, 149.66 |
| 11 | Scorpii Sector DM-M a7-1 | 14.68 ly | 10.62, -31.34, 150.75 |
| 12 | Scorpii Sector BB-O a6-4 | 14.72 ly | 7.97, -38.78, 138.81 |
| 13 | HIP 89269 | 14.82 ly | 14.94, -27.34, 146.19 |
| 14 | Col 285 Sector HL-U a46-4 | 14.96 ly | -10.16, -33.00, 147.69 |

Recommended memorial target: **Scorpii Sector YF-O a6-2** — closest (4.43 ly from anchor), zero-pop / uncontrolled / stationless per live EDSM. Confirm in-game colonisation UI before travel; Frontier rules change.

## 2. Supply stations for ~21,000 t Aluminum (Trailblazer megaship)

Requirement: closest stations to anchor selling Aluminum in high supply, Large pads for Anaconda.

Live Spansh query (fixed 2026-10-04, `POST /stations/search`, filter `has_large_pad=[1]`, sorted by distance from TRUE Kaus Australis coords 1.16, -25.91, 140.94): 60 Large-pad stations scanned, 5 with Aluminum supply > 0. Market snapshots rotate — verify in-game before bulk buying.

| Supply station (system) | From anchor | To target | Pads / type | Aluminum (supply / sell / updated) |
|---|---|---|---|---|
| **Shkaplerov Beacon** (Scorpii Sector XF-O a6-6) | 11.20 ly | 6.86 ly | Lx5 Ocellus Starport | 3,452,081 / 2,049 / 2026-10-02 |
| Torres Sanctuary (Scorpii Sector XF-O a6-6) | 11.20 ly | 6.86 ly | Lx4 Planetary Outpost | 3,686,652 / 2,359 / 2026-09-14 |
| Laister Base (Scorpii Sector XF-O a6-6) | 11.20 ly | 6.86 ly | Lx2 Planetary Outpost | 746,668 / 2,459 / 2026-05-04 (stale) |
| German Platform (Scorpii Sector XF-O a6-6) | 11.20 ly | 6.86 ly | Lx7 Coriolis Starport | 167,048 / 2,630 / 2026-09-12 |
| MacVicar Prospect (Goll) | 7.01 ly | 5.98 ly | Lx4 Planetary Outpost | 4,816 / 2,050 / 2026-07-18 |

Recommended loader: **Shkaplerov Beacon** — true starport (Ocellus, 5 large pads, Anaconda-friendly), freshest market update, 3.45 Mt Aluminum listed. Same-system backups: Torres Sanctuary / German Platform.

Still-unavailable live sources (recorded, not blocking): Inara API key exists but app has no event access (`eventStatus 400`) — enable at https://inara.cz/settings-api/; Inara website fetch is bot-blocked (HTTP 503) so use the new `inara_website_search` links in a browser; EDDN relay connects but yielded 0 messages in test windows (likely filtered/blocked network).

## 3. Flight plan + haul math (Anaconda)

Your spec: Anaconda 452 t, 21,000 t Aluminum, 28-day deadline.

Math (confirmed):
- 21,000 / 452 = 46.46 → **ceil = 47 round trips** (46 × 452 = 20,792 < 21,000; 47 × 452 = 21,244).
- Pace: 47 / 28 = **1.68 trips/day** (~0.60 days per round trip budget).

Route (verified live):
- Supply: **Shkaplerov Beacon, Scorpii Sector XF-O a6-6** (Lx5 Ocellus) → **Scorpii Sector YF-O a6-2** memorial / Trailblazer: **6.86 ly one-way, ~13.7 ly round trip** (11.20 ly anchor→supply positioning leg only on trip 1).
- Lifetime distance at 47 trips: ~644 ly hauling + 11.2 ly positioning.
- Flow per trip: load 452 t Aluminum at Shkaplerov Beacon → jump to Scorpii Sector YF-O a6-2 → deliver to Trailblazer megaship → empty return → repeat.

Live-ship warning from your journals (via `journal.get_status/get_loadout`, 174 files, commander RAMGARDEN):
- Latest Loadout (2026-10-03T06:53Z) is **`explorer_nx 'Cassy' [RA-18E]` = 108 t** (6 racks: 32+32+16+16+8+4), docked Ix / Scully-Power Station — not the Anaconda.
- Last Anaconda seen: **`anaconda 'ANNIE' [AN-N1E]` 2026-10-03T04:35Z = 368 t**, not 452 t. No 452-t Anaconda Loadout in history (max ever 368 t on 2026-09-30).
- Impact: at 368 t → 21,000/368 = 57.06 → **58 trips**; at current 108 t → 195 trips. Refit ANNIE to full 452-t cargo (strip shield/fighter/fuel-scoop per `anaconda_max_cargo.json` pattern) or re-plan trip count before the 28-day clock starts.

Correct ed-mcp usage (this rebuild's calls):
```python
from ed_mcp.providers import edsm, eddn, spansh, inara
edsm.sphere_systems(system_name="Ascella", radius_ly=15.0)
edsm.systems_info(names)          # batch, then colonisation.is_claimable_candidate()
edsm.system_info("Scorpii Sector YF-O a6-2")
spansh.search_stations(filters={"has_large_pad": {"value": [1]}}, page=1, size=60)  # POST /stations/search
spansh.quick_search("Shkaplerov")  # GET /search?q=
inara.search_nearest("Ascella")    # needs app access; else inara.website_search()
eddn.sample(schema="commodity", max_messages=6, timeout_s=25.0)
from ed_mcp.providers import journal as journal_p
journal_p.get_status(); journal_p.get_location(); journal_p.get_loadout()
```
