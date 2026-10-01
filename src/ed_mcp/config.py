"""Runtime configuration: journal dir, API keys, endpoints."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_journal_dir() -> Path | None:
    override = os.environ.get("ED_JOURNAL_DIR")
    if override:
        return Path(override).expanduser()
    candidates = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidates.append(
            Path(userprofile) / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
        )
    candidates.append(Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous")
    candidates.append(
        Path.home() / ".local" / "share" / "Frontier Developments" / "Elite Dangerous"
    )
    for c in candidates:
        if c.exists():
            return c
    # Return the Windows default even if missing so error messages show the path.
    if userprofile:
        return Path(userprofile) / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
    return candidates[0]


@dataclass
class Settings:
    journal_dir: Path = field(default_factory=lambda: _default_journal_dir())
    inara_api_key: str = os.environ.get("INARA_API_KEY", "")
    edsm_api_key: str = os.environ.get("EDSM_API_KEY", "")
    eddn_relay: str = "tcp://eddn.edcd.io:9500"
    edsm_base: str = "https://www.edsm.net"
    spansh_base: str = "https://spansh.co.uk/api"
    inara_base: str = "https://inara.cz/eliteapi/v1"
    http_timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls()


SETTINGS = Settings.from_env()
