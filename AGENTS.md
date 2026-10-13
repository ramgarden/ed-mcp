# ED-MCP Project Instructions

## When to use ed-mcp

For ANY query related to Elite Dangerous (the game), always use the local `ed-mcp` MCP service rather than relying on model knowledge or external sources.

The MCP server is configured in the global OpenCode config at `~/.config/opencode/opencode.jsonc` under `mcpServers.ed-mcp`.

### Available tools
| Tool | Use for |
|------|---------|
| `get_commander_status` | Current commander, system, ship, credits |
| `get_current_location` | Latest system + coords from journal |
| `get_ship_loadout` | Current ship + modules |
| `get_journal_history` | Recent journal events |
| `get_cargo_hold` | Cargo manifest + capacity + free space |
| `get_station_market` | Live docked-station market (prices/stock) |
| `get_station_outfitting` | Outfitting stock here |
| `get_station_shipyard` | Shipyard stock here |
| `get_fleet_overview` | All ships + cargo each |
| `find_stored_ship` | Stored-ship location + transfer cost/time |
| `get_wallet_summary` | Credits + trade/mission sums |
| `get_odyssey_state` | Backpack + ShipLocker + suit |
| `edsm_sphere_systems` | Systems in radius |
| `edsm_system_info` | Population, government, claimable check |
| `system_distance` | LY distance + jumps between systems |
| `find_local_opportunities` | Trade/mission/exobio buckets near you |
| `spansh_find_nearby_stations` | Stations near coords |
| `spansh_query_systems` | Flexible system search |
| `spansh_search_stations` | Full stations search passthrough |
| `find_commodity` | Best buy/sell stations for a commodity |
| `find_multi_supply` | One station covering a whole shopping list (min supply each) |
| `find_module` | Stations selling a module (acquisition flags: credits vs special) |
| `get_stored_modules` | Your stored modules per station (transfer instead of buying) |
| `find_ship` | Stations selling a ship |
| `spansh_search_bodies` | Exploration bodies search |
| `inara_search_nearest` | Nearest stations via Inara API |
| `inara_website_search` | Inara web links, no key |
| `eddn_live_sample` | Live EDDN data |
| `find_colonisation_candidates` | Zero-pop claimable systems |
| `get_colony_progress` | Depot manifest + delivered/remaining + % from journals |
| `station_services` | Services/pads/market for a named station (disambiguate by system) |
| `get_exploration_log` | Survey ledger per system (COMPLETE/PARTIAL/VISITED) |
| `system_scan_status` | Community catalog + value + your row for one system |
| `find_search_backlog` | Nearby systems you have not fully scanned |
| `build_cargo_shopping_list` | Anaconda max-cargo modules + stations |

### Key data sources
- Local journal files: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`
- EDSM API, Spansh API, Inara API (INARA_API_KEY needed), EDDN relay

### Notes
- Journal tools always use the player's local files — each user's instance reads their own journals
- The MCP server runs locally; it does not expose journals over the network
- For material/commodity queries, check market data via Spansh or EDDN
- For station/outfitting queries, prefer Spansh over EDSM
- Always return the FULL system name (e.g. `Col 359 Sector IZ-T a20-2`, not `IZ-T a20-2`) so it can be copy-pasted into the game's galaxy map search
- Promote one-off scripts into the service: whenever you hand-write a throwaway query script against ed-mcp providers/Spansh/EDSM to answer something, turn it into a proper MCP tool (pure logic in `logic/`, thin tool wrapper in `server.py`) with offline unit tests, update README + AGENTS.md tool tables, and commit + push. Never leave repeated query patterns as scratch files.

## Live-query cookbook (how to answer gameplay questions)

When the MCP server isn't reachable but the repo venv is, query providers directly
with `.venv/Scripts/python.exe`. Journal dir resolves itself via
`journal.resolve_journal_dir()` (`%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`).

```python
from ed_mcp.providers import journal as j, spansh, edsm
j.get_status()           # commander, credits, ship
j.get_location()         # system / station / latest event + timestamp
j.get_cargo_hold()       # used_t / free_t / inventory (Name, Name_Localised, Count)
j.get_station_market()   # live docked-station market; timestamp = freshness proof
j.get_colony_progress()  # depot manifest: required/provided/remaining per commodity + pace/ETA
j.get_wallet_summary()   # credits + market buy/sell totals
edsm.system_info("HIP 90994")  # coords for distance math / Spansh sorts
```

Spansh station search near a point (coords from `edsm.system_info` or journals):
```python
SITE = {"x": -22.28125, "y": -42.65625, "z": 344.65625}  # Col 359 Sector IZ-T a20-2
p = spansh.search_stations(
    filters={"has_market": {"value": [1]}, "has_large_pad": {"value": [1]}},
    sorts=[{"distance": {"direction": "asc", "distance": SITE}}], page=1, size=100)
```

### Gotchas learned the hard way
- `Market.json` commodity rows use **lowercase** keys: `name` / `buy` / `sell` / `supply` / `demand`
  (NOT `Name_Localised`/`Stock`/`SellPrice` — those are journal-event keys, e.g. `MarketBuy.BuyPrice`).
- Unlocalised installs render names as `$steel_name;` — strip `$`/`_name;` and compare spaceless-lowercase.
- MarketBuy/MarketSell journal events carry NO station/system — track them from surrounding
  `Location`/`Docked`/`FSDJump` events while iterating chronologically.
- Spansh `demand: 1` rows are phantoms (stale snapshots), never size a load from them.
  Treat any Spansh price older than ~1 week as a rumor: verify in-game before filling the hold.
- Bindings live at `%LOCALAPPDATA%\Frontier Developments\Elite Dangerous\Options\Bindings\Custom.*.binds`
  (XML; `Primary Device=... Key=...` per action). I can read them, and type text via a
  countdown SendKeys script — but never drive the galaxy-map UI blind (no screen/OCR loop),
  and never automate while the player is away (Frontier prohibits unattended automation).

### Standing gameplay rules (enforce every session)
1. A price only counts if seen **live in-game today** (journal `Market.json` timestamp or player confirm).
2. New loop ⇒ test with a small quantity first (10t proves the price; 400t assumes it).
3. Colony shopping: `get_colony_progress().remaining` ∩ docked-station `supply`, capped by `cargo.free_t`.
4. Refuel rule: supply stations must be true starports (or in-system hops) within one tank leg.
