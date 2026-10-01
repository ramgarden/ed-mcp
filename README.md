# Elite Dangerous MCP service (`ed-mcp`)

Ask an LLM plain-English questions about Elite Dangerous and get answers grounded in
**your local journal files** plus public galaxy data from the **EDDN (Elite Dangerous
Data Network)**, **EDSM**, **Spansh**, and **Inara**.

Example queries this server is built to answer:

- _"Find all stars within 15 light years of the stars in the Teapot (Sagittarius)
  asterism that have zero population and are claimable for a brand-new space station."_
- _"Make a shopping list to set up my Anaconda as a maximum-cargo hauler: use my
  journal to find my current system, then find which nearby stations sell the modules
  I need, where to get them, and how much they cost."_

## How it works

```
Claude / LLM client  <--MCP (stdio)-->  ed-mcp server
                                            |-- local journals  (%USERPROFILE%\Saved Games\...)
                                            |-- EDSM API        (systems, sphere, stations)
                                            |-- Spansh API      (systems/stations search, trade)
                                            |-- Inara API       (needs INARA_API_KEY)
                                            |-- EDDN relay      (live ZeroMQ firehose docs + sampler)
```

### MCP tools

| Tool | Source | What it does |
|---|---|---|
| `get_commander_status` | journal | Commander name, current system/station, ship, credits, rank summary |
| `get_current_location` | journal | Current system + coordinates, station, body — always from latest journal |
| `get_ship_loadout` | journal | Current ship type + modules from latest `Loadout` event |
| `get_journal_history` | journal | Last N relevant events (`FSDJump`, `Docked`, `Location`, `Outfitting`, …) |
| `edsm_sphere_systems` | EDSM | Systems in a radius around coordinates / system name |
| `edsm_system_info` | EDSM | Population, government, allegiance, bodies for a system (claimable check) |
| `spansh_find_nearby_stations` | Spansh | Stations near coordinates with pads, distance, services |
| `spansh_query_systems` | Spansh | Flexible tradedangerous-style systems search near a reference |
| `inara_search_nearest` | Inara | Nearest stations/components via Inara API (needs key) |
| `eddn_live_sample` | EDDN | Sample N live EDDN messages from the relay (commodity/outfitting/shipyard) |
| `find_colonisation_candidates` | EDSM+local | Zero-pop, claimable systems near a constellation/centre (Teapot example) |
| `build_cargo_shopping_list` | journal+Spansh/EDSM | Anaconda max-cargo module list + where to buy near you + prices |

Two MCP **prompts** (`colonisation_survey`, `anaconda_cargo_refit`) encode the worked
examples above so the LLM follows a grounded workflow instead of guessing.

## Quickstart

Requires Python 3.10+.

```powershell
# 1. Clone
git clone https://github.com/ramgarden/ed-mcp.git
Set-Location ed-mcp

# 2. Install (venv recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 3. Configure (optional but recommended for Inara tools)
Copy-Item .env.example .env
# edit .env -> INARA_API_KEY=...

# 4. Run tests
pytest -q

# 5. Run the MCP server (stdio)
python -m ed_mcp.server
```

### Claude Desktop config

```json
{
  "mcpServers": {
    "ed-mcp": {
      "command": "C:\\Users\\YOU\\Source\\ed-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "ed_mcp.server"],
      "env": { "INARA_API_KEY": "…" }
    }
  }
}
```

For Claude Code / `mcp add`, any stdio MCP client works — point it at `python -m ed_mcp.server`.

## Journal location

Defaults (in order):

1. `ED_JOURNAL_DIR` env var
2. `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`
3. `~/.local/share/Frontier Developments/Elite Dangerous` (Proton/Linux)

If no journals are found the journal tools return a clear `{"found": false, …}`
payload so the LLM can ask the user for a path instead of hallucinating.

## Data sources & credits

- **EDDN** relay `tcp://eddn.edcd.io:9500` (ZeroMQ) — message docs: https://github.com/EDCD/EDDN
- **EDSM** API — https://www.edsm.net/en/api-v1
- **Spansh** API — https://spansh.co.uk/api
- **Inara** API — https://inara.cz/settings-api/ (key required)
- Journal spec — https://elite-journal.readthedocs.io/

This is a community tool. Not affiliated with Frontier Developments, EDDN/EDCD,
EDSM, Spansh, or Inara.
