"""Graph construction and analysis for galactic jump-range proximity graphs.

Pure-Python graph algorithms (no heavy NetworkX dependency). Constructs
inferred accessibility graphs from system coordinates using a declared
maximum jump distance, then computes degree, connected components,
betweenness centrality (Brandes), bridges/articulation points, and
motif counts.

Results are labeled as structural observations only -- not evidence of
any lore conclusion.
"""
from __future__ import annotations

import collections
import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GraphNode:
    system_name: str
    system_id: str | None
    coordinates: tuple[float, float, float] | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    distance_ly: float
    provenance: str = "jump_range_proximity"


@dataclass(frozen=True)
class GraphSnapshot:
    nodes: dict[str, GraphNode]
    edges: dict[str, GraphEdge]
    max_edge_distance: float
    graph_definition: str
    source_snapshot_id: str | None
    node_count: int = 0
    edge_count: int = 0
    missing_coordinates: int = 0

    @classmethod
    def build(
        cls,
        systems: list[dict[str, Any]],
        max_edge_distance: float,
        graph_definition: str = "jump_range_proximity",
        source_snapshot_id: str | None = None,
    ) -> "GraphSnapshot":
        """Build a jump-range proximity graph from EDSM-style system records.

        Systems with null coordinates are still included as isolated nodes
        (marked missing) but never receive edges -- we do not infer
        connectivity where coordinates are absent.
        """
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}
        missing_coords = 0

        for s in systems:
            name = s.get("name") or s.get("system_name") or ""
            if not name:
                continue
            info = s.get("information", {}) or {}
            coords = s.get("coords")
            coord_tuple: tuple[float, float, float] | None = None
            if coords:
                try:
                    coord_tuple = (
                        float(coords.get("x", coords[0]) if isinstance(coords, dict) else coords[0]),
                        float(coords.get("y", coords[1]) if isinstance(coords, dict) else coords[1]),
                        float(coords.get("z", coords[2]) if isinstance(coords, dict) else coords[2]),
                    )
                except (TypeError, ValueError, IndexError):
                    coord_tuple = None
            if coord_tuple is None:
                missing_coords += 1

            attributes = {
                "population": info.get("population"),
                "government": info.get("government"),
                "allegiance": info.get("allegiance"),
                "economy": info.get("economy"),
                "primary_star": info.get("primary_star"),
                "permit": info.get("permit"),
            }
            attributes = {k: v for k, v in attributes.items() if v is not None}
            nodes[name] = GraphNode(
                system_name=name,
                system_id=str(s.get("id")) if s.get("id") is not None else None,
                coordinates=coord_tuple,
                attributes=attributes,
            )

        node_names = list(nodes.keys())
        edge_count = 0
        for i in range(len(node_names)):
            for j in range(i + 1, len(node_names)):
                a = nodes[node_names[i]]
                b = nodes[node_names[j]]
                if a.coordinates is None or b.coordinates is None:
                    continue
                d = math.sqrt(
                    (a.coordinates[0] - b.coordinates[0]) ** 2
                    + (a.coordinates[1] - b.coordinates[1]) ** 2
                    + (a.coordinates[2] - b.coordinates[2]) ** 2
                )
                if d <= max_edge_distance:
                    edge_id = f"{node_names[i]}<->{node_names[j]}"
                    edges[edge_id] = GraphEdge(
                        source=node_names[i],
                        target=node_names[j],
                        distance_ly=round(d, 4),
                    )
                    edge_count += 1

        return cls(
            nodes=nodes,
            edges=edges,
            max_edge_distance=max_edge_distance,
            graph_definition=graph_definition,
            source_snapshot_id=source_snapshot_id,
            node_count=len(nodes),
            edge_count=edge_count,
            missing_coordinates=missing_coords,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "missing_coordinates": self.missing_coordinates,
            "max_edge_distance": self.max_edge_distance,
            "graph_definition": self.graph_definition,
            "source_snapshot_id": self.source_snapshot_id,
            "nodes": {
                name: {
                    "system_name": n.system_name,
                    "system_id": n.system_id,
                    "coordinates": list(n.coordinates) if n.coordinates else None,
                    "attributes": n.attributes,
                }
                for name, n in self.nodes.items()
            },
            "edges": {
                eid: {
                    "source": e.source,
                    "target": e.target,
                    "distance_ly": e.distance_ly,
                    "provenance": e.provenance,
                }
                for eid, e in self.edges.items()
            },
        }


def connected_components(snapshot: GraphSnapshot) -> dict[str, Any]:
    """Return connected components using BFS."""
    adjacency: dict[str, set[str]] = {n: set() for n in snapshot.nodes}
    for e in snapshot.edges.values():
        adjacency[e.source].add(e.target)
        adjacency[e.target].add(e.source)

    visited: set[str] = set()
    components: list[list[str]] = []
    for start in snapshot.nodes:
        if start in visited:
            continue
        comp: list[str] = []
        queue = collections.deque([start])
        visited.add(start)
        while queue:
            node = queue.popleft()
            comp.append(node)
            for nb in adjacency.get(node, set()):
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        components.append(comp)

    return {
        "component_count": len(components),
        "largest_component_size": max((len(c) for c in components), default=0),
        "components": [sorted(c) for c in components],
        "isolated_nodes": sum(1 for c in components if len(c) == 1),
    }


def degree_distribution(snapshot: GraphSnapshot) -> dict[str, Any]:
    """Degree per node and distribution statistics."""
    degrees: dict[str, int] = {n: 0 for n in snapshot.nodes}
    for e in snapshot.edges.values():
        degrees[e.source] += 1
        degrees[e.target] += 1

    counts = sorted(degrees.values())
    if counts:
        mean = sum(counts) / len(counts)
        median = counts[len(counts) // 2]
        max_deg = max(counts)
        min_deg = min(counts)
    else:
        mean = median = max_deg = min_deg = 0.0

    histogram: dict[int, int] = {}
    for d in counts:
        histogram[d] = histogram.get(d, 0) + 1

    return {
        "degrees": dict(sorted(degrees.items())),
        "mean_degree": round(mean, 3),
        "median_degree": median,
        "max_degree": max_deg,
        "min_degree": min_deg,
        "degree_histogram": histogram,
        "average_degree": round(sum(counts) / len(counts), 3) if counts else 0.0,
    }


def bridges_and_articulation_points(snapshot: GraphSnapshot) -> dict[str, Any]:
    """Find bridges and articulation points using Tarjan's algorithm.

    Runs per connected component.
    """
    adjacency: dict[str, list[str]] = {n: [] for n in snapshot.nodes}
    for e in snapshot.edges.values():
        adjacency[e.source].append(e.target)
        adjacency[e.target].append(e.source)

    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    articulation: set[str] = set()
    bridges: list[tuple[str, str]] = []
    timer = [0]

    def dfs(u: str) -> None:
        children = 0
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in adjacency.get(u, []):
            if v not in disc:
                children += 1
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent.get(u) is None and children > 1:
                    articulation.add(u)
                if parent.get(u) is not None and low[v] >= disc[u]:
                    articulation.add(u)
                if low[v] > disc[u]:
                    bridges.append((u, v) if u < v else (v, u))
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for node in snapshot.nodes:
        if node not in disc:
            parent[node] = None
            dfs(node)

    return {
        "bridge_count": len(bridges),
        "bridges": sorted(bridges),
        "articulation_point_count": len(articulation),
        "articulation_points": sorted(articulation),
    }


def betweenness_centrality(snapshot: GraphSnapshot) -> dict[str, float]:
    """Brandes algorithm for betweenness centrality (unweighted).

    Only counts shortest paths within each connected component.
    """
    adjacency: dict[str, set[str]] = {n: set() for n in snapshot.nodes}
    for e in snapshot.edges.values():
        adjacency[e.source].add(e.target)
        adjacency[e.target].add(e.source)

    betweenness: dict[str, float] = {n: 0.0 for n in snapshot.nodes}

    for s in snapshot.nodes:
        stack: list[str] = []
        pred: dict[str, list[str]] = {v: [] for v in snapshot.nodes}
        sigma: dict[str, float] = {v: 0.0 for v in snapshot.nodes}
        sigma[s] = 1.0
        dist: dict[str, int] = {v: -1 for v in snapshot.nodes}
        dist[s] = 0
        queue = collections.deque([s])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adjacency.get(v, set()):
                if dist[w] < 0:
                    queue.append(w)
                    dist[w] = dist[v] + 1
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        delta: dict[str, float] = {v: 0.0 for v in snapshot.nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                betweenness[w] += delta[w]

    return betweenness


def motif_counts(snapshot: GraphSnapshot) -> dict[str, int]:
    """Count small motifs: chains (3-node path), loops (triangles),
    and branching (3-node star)."""
    adjacency: dict[str, set[str]] = {n: set() for n in snapshot.nodes}
    for e in snapshot.edges.values():
        adjacency[e.source].add(e.target)
        adjacency[e.target].add(e.source)

    nodes = sorted(snapshot.nodes)
    node_set = set(nodes)
    triangles = 0
    chains = 0
    branching = 0

    for i, u in enumerate(nodes):
        nbrs_u = adjacency.get(u, set())
        for v in nbrs_u:
            if v <= u:
                continue
            nbrs_v = adjacency.get(v, set())
            common = nbrs_u & nbrs_v
            triangles += len([w for w in common if w > v])
            # Chains: u-v-w where w is not u and w != v
            for w in nbrs_v:
                if w != u and w != v:
                    chains += 1
        # Branching: u connected to >= 2 neighbors that are not connected to each other
        nbr_list = sorted(nbrs_u)
        for i2 in range(len(nbr_list)):
            for j2 in range(i2 + 1, len(nbr_list)):
                a, b = nbr_list[i2], nbr_list[j2]
                if b not in adjacency.get(a, set()):
                    branching += 1

    return {
        "triangles": triangles,
        "chains": chains // 2,  # each chain counted twice
        "branching": branching,
    }


def sensitivity_analysis(
    systems: list[dict[str, Any]],
    radii: list[float],
    graph_definition: str = "jump_range_proximity",
) -> dict[str, Any]:
    """Run graph construction across multiple jump-range radii.

    Returns per-radius metrics: component count, largest component size,
    edge count, average degree, bridge count, articulation point count.
    """
    results: dict[str, Any] = {}
    for r in radii:
        snap = GraphSnapshot.build(
            systems=systems,
            max_edge_distance=r,
            graph_definition=graph_definition,
        )
        cc = connected_components(snap)
        deg = degree_distribution(snap)
        bridges = bridges_and_articulation_points(snap)
        betw = betweenness_centrality(snap)
        motifs = motif_counts(snap)
        results[f"radius_{r}"] = {
            "max_edge_distance": r,
            "node_count": snap.node_count,
            "edge_count": snap.edge_count,
            "missing_coordinates": snap.missing_coordinates,
            "component_count": cc["component_count"],
            "largest_component_size": cc["largest_component_size"],
            "isolated_nodes": cc["isolated_nodes"],
            "mean_degree": deg["mean_degree"],
            "max_degree": deg["max_degree"],
            "bridge_count": bridges["bridge_count"],
            "articulation_point_count": bridges["articulation_point_count"],
            "max_betweenness": round(max(betw.values()), 6) if betw else 0.0,
            "triangles": motifs["triangles"],
        }
    return results
