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
| `get_wallet_summary` | Credits + trade/mission sums |
| `get_odyssey_state` | Backpack + ShipLocker + suit |
| `edsm_sphere_systems` | Systems in radius |
| `edsm_system_info` | Population, government, claimable check |
| `system_distance` | LY distance + jumps between systems |
| `spansh_find_nearby_stations` | Stations near coords |
| `spansh_query_systems` | Flexible system search |
| `spansh_search_stations` | Full stations search passthrough |
| `find_commodity` | Best buy/sell stations for a commodity |
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
