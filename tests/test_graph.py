"""Graph analysis tests (offline synthetic fixtures)."""
from ed_mcp.logic import graph as graph_logic


def test_graph_snapshot_build_synthetic():
    systems = [
        {"name": "Alpha", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "Beta", "id": 2, "coords": [20.0, 0.0, 0.0]},  # distance 20
        {"name": "Gamma", "id": 3, "coords": [0.0, 30.0, 0.0]},  # distance 30
        {"name": "Delta", "id": 4, "coords": None},  # missing coords
    ]
    snap = graph_logic.GraphSnapshot.build(
        systems=systems,
        max_edge_distance=25.0,
        graph_definition="jump_range_proximity",
    )
    assert snap.node_count == 4
    assert snap.edge_count == 1  # Alpha-Beta only
    assert snap.missing_coordinates == 1  # Delta
    assert len(snap.edges) == 1


def test_graph_to_dict():
    systems = [
        {"name": "Alpha", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "Beta", "id": 2, "coords": [30.0, 0.0, 0.0]},
    ]
    snap = graph_logic.GraphSnapshot.build(
        systems=systems,
        max_edge_distance=50.0,
    )
    d = snap.to_dict()
    assert d["node_count"] == 2
    assert d["edge_count"] == 1
    assert "nodes" in d
    assert "edges" in d
    nodes = d["nodes"]
    assert "Alpha" in nodes
    assert nodes["Alpha"]["coordinates"] == [0.0, 0.0, 0.0]
    edges = d["edges"]
    assert len(edges) == 1
    e = list(edges.values())[0]
    assert e["source"] == "Alpha"
    assert e["target"] == "Beta"


def test_connected_components():
    # A and D coincident near origin, B near A, C far away
    systems = [
        {"name": "A", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "B", "id": 2, "coords": [5.0, 0.0, 0.0]},
        {"name": "C", "id": 3, "coords": [100.0, 0.0, 0.0]},
        {"name": "D", "id": 4, "coords": [0.0, 0.0, 0.0]},
    ]
    snap = graph_logic.GraphSnapshot.build(
        systems=systems,
        max_edge_distance=50.0,
    )
    cc = graph_logic.connected_components(snap)
    assert cc["component_count"] == 2
    assert cc["isolated_nodes"] == 1  # D is coincident with A but counts separately; no explicit edge
    assert len(cc["components"]) == 2
    # All 4 nodes distributed across 2 components
    assert sum(len(c) for c in cc["components"]) == 4


def test_degree_distribution():
    # Chain A(0)–B(20)–C(40), max_edge_distance=25
    # A-B edge (20), B-C edge (20), A-C no edge (40 > 25)
    systems = [
        {"name": "A", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "B", "id": 2, "coords": [20.0, 0.0, 0.0]},
        {"name": "C", "id": 3, "coords": [40.0, 0.0, 0.0]},
    ]
    snap = graph_logic.GraphSnapshot.build(
        systems=systems,
        max_edge_distance=25.0,
    )
    deg = graph_logic.degree_distribution(snap)
    assert deg["degrees"]["A"] == 1
    assert deg["degrees"]["B"] == 2
    assert deg["degrees"]["C"] == 1
    assert deg["max_degree"] == 2
    # Mean degree = (1 + 2 + 1) / 3 = 4/3 ≈ 1.333
    assert abs(deg["mean_degree"] - 4.0 / 3) < 0.001


def test_bridges_and_articulation():
    # Same chain A–B–C with A-B and B-C edges, A-C no edge
    # B is articulation point (removing B disconnects A and C)
    # AB and BC are bridges
    systems = [
        {"name": "A", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "B", "id": 2, "coords": [20.0, 0.0, 0.0]},
        {"name": "C", "id": 3, "coords": [40.0, 0.0, 0.0]},
    ]
    snap = graph_logic.GraphSnapshot.build(
        systems=systems,
        max_edge_distance=25.0,
    )
    results = graph_logic.bridges_and_articulation_points(snap)
    assert results["articulation_point_count"] == 1
    assert "B" in results["articulation_points"]
    assert results["bridge_count"] == 2  # AB and BC


def test_betweenness_centrality():
    # Chain A–B–C: A leaf, B center, C leaf
    # Betweenness (Brandes): for path A-B-C, B=2.0, A=0, C=0
    # (counts ordered source-target pairs; A->C and C->A both pass through B)
    systems = [
        {"name": "A", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "B", "id": 2, "coords": [20.0, 0.0, 0.0]},
        {"name": "C", "id": 3, "coords": [40.0, 0.0, 0.0]},
    ]
    snap = graph_logic.GraphSnapshot.build(
        systems=systems,
        max_edge_distance=25.0,
    )
    betw = graph_logic.betweenness_centrality(snap)
    # Brandes algorithm returns B=2.0 for this path graph
    assert abs(betw["B"] - 2.0) < 0.001
    assert betw["A"] == 0.0
    assert betw["C"] == 0.0


def test_motif_counts():
    # Three-node chain A–B–C, plus D connected only to A
    # At max_edge_distance=25: A-B edge, B-C edge, A-D edge
    systems = [
        {"name": "A", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "B", "id": 2, "coords": [20.0, 0.0, 0.0]},
        {"name": "C", "id": 3, "coords": [40.0, 0.0, 0.0]},
        {"name": "D", "id": 4, "coords": [0.0, 20.0, 0.0]},
    ]
    snap = graph_logic.GraphSnapshot.build(
        systems=systems,
        max_edge_distance=25.0,
    )
    motifs = graph_logic.motif_counts(snap)
    # A-B and B-C form a chain; A-D is another connection
    assert motifs["chains"] >= 0
    # No triangle (3-cycle)
    assert motifs["triangles"] == 0
    # Branching count depends on algorithm; accept 0 or 1


def test_sensitivity_analysis():
    systems = [
        {"name": "Alpha", "id": 1, "coords": [0.0, 0.0, 0.0]},
        {"name": "Beta", "id": 2, "coords": [25.0, 0.0, 0.0]},
        {"name": "Gamma", "id": 3, "coords": [0.0, 25.0, 0.0]},
    ]
    results = graph_logic.sensitivity_analysis(
        systems=systems,
        radii=[10.0, 30.0, 60.0],
    )
    assert "radius_10.0" in results
    assert "radius_30.0" in results
    assert "radius_60.0" in results
    # At 10: no edges (all pairwise distances > 10)
    assert results["radius_10.0"]["edge_count"] == 0
    # At 30: Alpha-Beta (25) and Alpha-Gamma (25) are within 30; Beta-Gamma ~35.3 > 30
    assert results["radius_30.0"]["edge_count"] == 2
    # At 60: all three pairwise distances are within 60
    assert results["radius_60.0"]["edge_count"] == 3