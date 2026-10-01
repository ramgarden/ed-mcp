"""EDDN (Elite Dangerous Data Network) live relay helper.

The EDDN is a ZeroMQ PUB/SUB firehose at tcp://eddn.edcd.io:9500 broadcasting
JSON messages with schemas: commodity, outfitting, shipyard, journal, etc.
Docs + schemas: https://github.com/EDCD/EDDN

Subscribing requires pyzmq. Because MCP tools should stay fast, this module
offers a *bounded sample*: connect, collect N messages or T seconds, disconnect.
Long-lived listening belongs in a sidecar, not in an MCP call.
"""
from __future__ import annotations

import json
import time
from typing import Any


def sample(schema: str | None = None, max_messages: int = 5,
           timeout_s: float = 15.0,
           relay: str = "tcp://eddn.edcd.io:9500") -> dict[str, Any]:
    try:
        import zmq  # type: ignore
    except ImportError:
        return {"ok": False,
                "hint": "pip install pyzmq to use EDDN live sampling."}
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.RCVTIMEO, 2000)
    sock.setsockopt(zmq.LINGER, 0)
    try:
        sock.connect(relay)
        sock.setsockopt_string(zmq.SUBSCRIBE, schema or "")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"connect failed: {exc}"}
    collected: list[dict[str, Any]] = []
    deadline = time.time() + timeout_s
    try:
        while len(collected) < max_messages and time.time() < deadline:
            try:
                raw = sock.recv()
            except Exception:  # timeout -> keep waiting until deadline
                continue
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if schema and msg.get("$schemaRef") != schema and \
                    schema not in str(msg.get("$schemaRef", "")):
                # prefix subscription already filters; keep loose check
                pass
            # Slim to the interesting bits
            collected.append({
                "$schemaRef": msg.get("$schemaRef"),
                "header": msg.get("header"),
                "message_keys": list((msg.get("message") or {}).keys())[:20],
                "message_preview": str(msg.get("message"))[:2000],
            })
    finally:
        try:
            sock.disconnect(relay)
        except Exception:  # noqa: BLE001
            pass
        sock.close(linger=0)
    return {"ok": True, "relay": relay, "count": len(collected), "messages": collected,
            "schemas": "https://github.com/EDCD/EDDN/tree/master/schemas",
            "note": "Bounded sample only; run a sidecar subscriber for history."}
