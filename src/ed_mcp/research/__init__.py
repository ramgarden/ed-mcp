"""Research foundations: provenance tracking, experiment management, artifact storage.

Pure, offline-capable modules for recording research provenance and running
bounded scientific experiments over ed-mcp data sources.

These modules add no arbitrary code execution, no external LLM dependency,
and no runtime dependency on ed-mcp from Project Seshat. They are additive to
the existing ed-mcp tool set.
"""
from __future__ import annotations

__all__ = ["provenance", "experiment", "artifact_store", "region"]
