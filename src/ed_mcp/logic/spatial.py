"""3D spatial clustering and geometry analysis for galactic coordinates.

Pure-Python spatial algorithms (no heavy scikit-learn dependency).
Implements DBSCAN for density-based clustering plus geometry analysis
(PCA-style dominance, convex hull approximate, compactness metrics).

Results labeled as structural observations only -- not evidence of any
lore conclusion. Never treats unobserved systems as empty space.
"""
from __future__ import annotations

import collections
import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SpatialPoint:
    system_name: str
    coordinates: tuple[float, float, float]
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialCluster:
    cluster_id: int
    members: list[str]
    coordinates: tuple[float, float, float]  # centroid
    radius_ly: float  # max distance from centroid
    density: float  # members per volume
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GeometryResult:
    dominant_axis: str  # 'x', 'y', or 'z'
    linearity: float  # 0..1, how linear the arrangement
    planarity: float  # 0..1, how planar the arrangement
    spread: tuple[float, float, float]  # max-min per axis
    centroid: tuple[float, float, float]
    compactness: float  # inverse of spread normalized


def _parse_coords(record: dict[str, Any]) -> tuple[float, float, float] | None:
    """Extract (x, y, z) from various record shapes."""
    coords = record.get("coords")
    if coords:
        try:
            return (
                float(coords.get("x", coords[0]) if isinstance(coords, dict) else coords[0]),
                float(coords.get("y", coords[1]) if isinstance(coords, dict) else coords[1]),
                float(coords.get("z", coords[2]) if isinstance(coords, dict) else coords[2]),
            )
        except (TypeError, ValueError, IndexError):
            return None
    return None


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def dbscan(
    points: list[SpatialPoint],
    eps_ly: float = 50.0,
    min_samples: int = 3,
) -> dict[str, Any]:
    """Density-Based Spatial Clustering of Applications with Noise (DBSCAN).

    Clusters 3D points within eps_ly light years requiring min_samples
    neighbors to form a dense region. Points not reachable from any core
    point are labeled noise (-1).

    Returns cluster assignments, per-cluster stats, and noise count.
    Never drops points silently -- noise points are explicitly labeled.
    """
    n = len(points)
    if n == 0:
        return {
            "clusters": [],
            "cluster_count": 0,
            "noise_count": 0,
            "assignments": {},
            "parameters": {"eps_ly": eps_ly, "min_samples": min_samples},
        }

    coords = [p.coordinates for p in points]
    labels = [-1] * n
    cluster_id = 0

    def region_neighbors(idx: int) -> list[int]:
        neigh = []
        for j in range(n):
            if j != idx and _distance(coords[idx], coords[j]) <= eps_ly:
                neigh.append(j)
        return neigh

    for i in range(n):
        if labels[i] != -1:
            continue
        neighbors = region_neighbors(i)
        if len(neighbors) < min_samples:
            labels[i] = -1  # noise for now, may be reclassified
            continue
        # Start new cluster
        cluster_id += 1
        labels[i] = cluster_id
        seed_set = list(neighbors)
        while seed_set:
            j = seed_set.pop()
            if labels[j] == -1:
                labels[j] = cluster_id
            if labels[j] != cluster_id:
                labels[j] = cluster_id
                j_neighbors = region_neighbors(j)
                if len(j_neighbors) >= min_samples:
                    seed_set.extend(j_neighbors)

    # Build cluster results
    clusters_by_id: dict[int, list[int]] = collections.defaultdict(list)
    for idx, lab in enumerate(labels):
        if lab != -1:
            clusters_by_id[lab].append(idx)

    cluster_results: list[SpatialCluster] = []
    noise_count = 0
    for lab, idxs in clusters_by_id.items():
        member_points = [points[i] for i in idxs]
        member_names = [p.system_name for p in member_points]
        # Centroid
        cx = sum(p.coordinates[0] for p in member_points) / len(member_points)
        cy = sum(p.coordinates[1] for p in member_points) / len(member_points)
        cz = sum(p.coordinates[2] for p in member_points) / len(member_points)
        centroid = (cx, cy, cz)
        # Radius = max distance from centroid
        radius = max(_distance(centroid, p.coordinates) for p in member_points)
        # Density = members / volume of sphere
        volume = (4.0 / 3.0) * math.pi * (radius ** 3) if radius > 0 else 1.0
        density = len(member_points) / volume
        cluster_results.append(
            SpatialCluster(
                cluster_id=lab,
                members=member_names,
                coordinates=centroid,
                radius_ly=round(radius, 4),
                density=round(density, 6),
                parameters={"eps_ly": eps_ly, "min_samples": min_samples},
            )
        )
    noise_count = sum(1 for lab in labels if lab == -1)

    assignments = {points[i].system_name: labels[i] for i in range(n)}
    return {
        "clusters": [c.to_dict() for c in cluster_results],
        "cluster_count": len(cluster_results),
        "noise_count": noise_count,
        "assignments": assignments,
        "parameters": {"eps_ly": eps_ly, "min_samples": min_samples},
    }


def analyze_geometry(points: list[SpatialPoint]) -> GeometryResult:
    """Analyze geometric structure of a point cloud.

    Computes linearity, planarity, spread, centroid, and compactness
    metrics to identify linear arrangements, planar structures, or
    spherical clusters.
    """
    n = len(points)
    if n == 0:
        return GeometryResult(
            dominant_axis="x",
            linearity=0.0,
            planarity=0.0,
            spread=(0.0, 0.0, 0.0),
            centroid=(0.0, 0.0, 0.0),
            compactness=0.0,
        )

    coords = [p.coordinates for p in points]
    cx = sum(c[0] for c in coords) / n
    cy = sum(c[1] for c in coords) / n
    cz = sum(c[2] for c in coords) / n
    centroid = (cx, cy, cz)

    # Spread (max-min per axis)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]
    spread = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    # Linearity: how much variance is along the dominant axis
    total_spread = spread[0] + spread[1] + spread[2]
    if total_spread > 0:
        max_axis = max(range(3), key=lambda i: spread[i])
        linearity = spread[max_axis] / total_spread
        dominant_axis = ["x", "y", "z"][max_axis]
    else:
        linearity = 0.0
        dominant_axis = "x"

    # Planarity: how much variance is in the two dominant axes
    sorted_spreads = sorted(spread, reverse=True)
    if total_spread > 0:
        planarity = (sorted_spreads[0] + sorted_spreads[1]) / total_spread
    else:
        planarity = 0.0

    # Compactness: inverse of normalized total spread (higher = more compact)
    max_spread = max(spread) if max(spread) > 0 else 1.0
    compactness = 1.0 / (1.0 + total_spread / max_spread)

    return GeometryResult(
        dominant_axis=dominant_axis,
        linearity=round(linearity, 4),
        planarity=round(planarity, 4),
        spread=tuple(round(s, 4) for s in spread),
        centroid=tuple(round(c, 4) for c in centroid),
        compactness=round(compactness, 4),
    )


def nearest_neighbor_stats(
    points: list[SpatialPoint],
) -> dict[str, Any]:
    """Nearest-neighbor distance statistics for spatial outlier detection.

    Returns mean, min, max, and per-point nearest-neighbor distances.
    Helps identify spatial outliers (unusually far from any neighbor).
    """
    n = len(points)
    if n == 0:
        return {"mean_nn_distance": 0.0, "min": 0.0, "max": 0.0, "per_point": {}}
    coords = [p.coordinates for p in points]
    per_point: dict[str, float] = {}
    distances: list[float] = []
    for i in range(n):
        best = float("inf")
        for j in range(n):
            if i == j:
                continue
            d = _distance(coords[i], coords[j])
            if d < best:
                best = d
        if best == float("inf"):
            best = 0.0
        per_point[points[i].system_name] = round(best, 4)
        distances.append(best)
    return {
        "mean_nn_distance": round(sum(distances) / len(distances), 4),
        "min": round(min(distances), 4),
        "max": round(max(distances), 4),
        "per_point": per_point,
    }


def spatial_sensitivity_analysis(
    points: list[SpatialPoint],
    eps_values: list[float] | None = None,
    min_samples_values: list[int] | None = None,
) -> dict[str, Any]:
    """Run DBSCAN across parameter combinations for sensitivity testing."""
    eps_values = eps_values or [25.0, 50.0, 75.0, 100.0]
    min_samples_values = min_samples_values or [2, 3, 5]
    results: dict[str, Any] = {}
    for eps in eps_values:
        for min_samp in min_samples_values:
            key = f"eps_{eps}_min{min_samp}"
            result = dbscan(points=points, eps_ly=eps, min_samples=min_samp)
            results[key] = {
                "eps_ly": eps,
                "min_samples": min_samp,
                "cluster_count": result["cluster_count"],
                "noise_count": result["noise_count"],
                "clusters": result["clusters"],
            }
    return results
