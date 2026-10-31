"""Bounded region query adapter composing existing ed-mcp source tools.

Composes `edsm_sphere_systems` into a bounded, provenance-tracked region
query. Results are capped (default 200, configurable) and include full
source provenance with query parameters.

Never silently converts missing data: systems without coordinates retain
`is_missing=True` with an explicit reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ed_mcp.providers import edsm as edsm_p
from ed_mcp.research.artifact_store import ArtifactStore
from ed_mcp.research.provenance import Observation, Provenance


@dataclass(frozen=True)
class RegionResult:
    ok: bool
    center_system: str | None
    center_coords: tuple[float, float, float] | None
    radius_ly: float
    systems: list[dict[str, Any]]
    count: int
    errors: list[str]
    provenance: list[Provenance]
    query_parameters: dict[str, Any]


def query_region(
    *,
    system_name: str | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    radius_ly: float = 15.0,
    store: ArtifactStore | None = None,
) -> RegionResult:
    """Query a bounded EDSM sphere around a system name or coords.

    Returns capped results (max 200) with full provenance. Systems missing
    coordinates are returned with `is_missing=True` and explicit reason
    rather than being filtered out silently.
    """
    errors: list[str] = []
    provenance_list: list[Provenance] = []
    systems_out: list[dict[str, Any]] = []
    query_params = {
        "source": "EDSM sphere-systems",
        "system_name": system_name,
        "x": x,
        "y": y,
        "z": z,
        "radius_ly": radius_ly,
        "min_radius": 0.0,
    }

    try:
        systems = edsm_p.sphere_systems(
            system_name=system_name,
            x=x,
            y=y,
            z=z,
            radius_ly=radius_ly,
        )
    except Exception as exc:
        return RegionResult(
            ok=False,
            center_system=system_name,
            center_coords=(x, y, z) if x is not None else None,
            radius_ly=radius_ly,
            systems=[],
            count=0,
            errors=[str(exc)],
            provenance=[],
            query_parameters=query_params,
        )

    center_coords: tuple[float, float, float] | None = None
    center_system_name = system_name

    for s in systems[:200]:
        name = s.get("name")
        coords = s.get("coords")
        coord_tuple: tuple[float, float, float] | None = None
        if coords and len(coords) >= 3:
            try:
                coord_tuple = (
                    float(coords.get("x", coords[0])),
                    float(coords.get("y", coords[1])),
                    float(coords.get("z", coords[2])),
                )
                if center_system_name == name or center_coords is None:
                    center_coords = coord_tuple
            except (TypeError, ValueError):
                coord_tuple = None

        prov = Provenance.create(
            source="EDSM",
            source_record_id=str(s.get("id")) if s.get("id") is not None else None,
            system_name=name,
            system_id=str(s.get("id")) if s.get("id") is not None else None,
            coordinates=coord_tuple,
            coordinate_reference="EDSM galactic coordinates (LY)",
            data_type="system_catalog",
            source_schema_version="EDSM API v1",
            raw_payload=s,
            query_parameters=query_params,
            completeness_notes=(
                "EDSM public catalog; coordinate completeness not guaranteed"
                if coord_tuple is None
                else None
            ),
            observation_type="directly_observed",
        )
        provenance_list.append(prov)

        missing = coord_tuple is None
        systems_out.append(
            {
                "name": name,
                "coords": coords,
                "distance": s.get("distance"),
                "bodyCount": s.get("bodyCount"),
                "information": s.get("information", {}),
                "_provenance": prov.to_dict(),
                "is_missing": missing,
                "missing_reason": "No coordinates returned by EDSM" if missing else None,
            }
        )

        if store is not None:
            store.save_observation(
                Observation(
                    provenance=prov,
                    value=s,
                    is_missing=missing,
                    missing_reason="No coordinates returned by EDSM" if missing else None,
                )
            )

    return RegionResult(
        ok=True,
        center_system=center_system_name,
        center_coords=center_coords,
        radius_ly=radius_ly,
        systems=systems_out,
        count=len(systems_out),
        errors=errors,
        provenance=provenance_list,
        query_parameters=query_params,
    )
