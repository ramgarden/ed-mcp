"""Provenance tracking for research observations and query results.

Records source metadata for every observation: source name, record/message
identifier, retrieval timestamp, event timestamp, system identity,
coordinates, data type/schema, source payload hash, query parameters,
pagination/cursor info, completeness notes, and observation type
(directly observed / inferred / derived).

Never silently converts missing values into zero, false, or empty collections.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Provenance:
    """Immutable provenance record for a single source observation."""

    source: str
    source_record_id: str | None
    retrieval_timestamp_utc: str
    event_timestamp_utc: str | None
    system_name: str | None
    system_id: str | None
    coordinates: tuple[float, float, float] | None
    coordinate_reference: str | None
    data_type: str | None
    source_schema_version: str | None
    payload_sha256: str | None
    query_parameters: dict[str, Any] | None
    pagination_cursor: str | None
    completeness_notes: str | None
    observation_type: str = "directly_observed"

    @classmethod
    def now(cls) -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def create(
        cls,
        *,
        source: str,
        source_record_id: str | None = None,
        system_name: str | None = None,
        system_id: str | None = None,
        coordinates: tuple[float, float, float] | None = None,
        coordinate_reference: str | None = None,
        data_type: str | None = None,
        source_schema_version: str | None = None,
        raw_payload: dict[str, Any] | None = None,
        query_parameters: dict[str, Any] | None = None,
        pagination_cursor: str | None = None,
        completeness_notes: str | None = None,
        observation_type: str = "directly_observed",
        event_timestamp_utc: str | None = None,
    ) -> "Provenance":
        payload_sha256: str | None = None
        if raw_payload is not None:
            payload_json = json.dumps(raw_payload, sort_keys=True)
            payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        return cls(
            source=source,
            source_record_id=source_record_id,
            retrieval_timestamp_utc=cls.now(),
            event_timestamp_utc=event_timestamp_utc,
            system_name=system_name,
            system_id=system_id,
            coordinates=coordinates,
            coordinate_reference=coordinate_reference,
            data_type=data_type,
            source_schema_version=source_schema_version,
            payload_sha256=payload_sha256,
            query_parameters=query_parameters,
            pagination_cursor=pagination_cursor,
            completeness_notes=completeness_notes,
            observation_type=observation_type,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["coordinates"] is not None:
            d["coordinates"] = list(d["coordinates"])
        return d


@dataclass(frozen=True)
class Observation:
    """A single source observation with provenance and normalized value."""

    provenance: Provenance
    value: Any
    is_missing: bool = False
    missing_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance": self.provenance.to_dict(),
            "value": self.value,
            "is_missing": self.is_missing,
            "missing_reason": self.missing_reason,
        }
