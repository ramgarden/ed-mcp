"""Spatial analysis tests (offline synthetic fixtures)."""
from ed_mcp.logic import spatial as spatial_logic


def test_dbscan_simple_cluster():
    points = [
        spatial_logic.SpatialPoint("A", (0.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("B", (1.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("C", (0.0, 1.0, 0.0)),
        spatial_logic.SpatialPoint("D", (100.0, 0.0, 0.0)),  # noise
    ]
    result = spatial_logic.dbscan(points=points, eps_ly=5.0, min_samples=2)
    assert result["cluster_count"] == 1
    assert result["noise_count"] == 1
    assert result["assignments"]["D"] == -1


def test_dbscan_all_noise():
    points = [
        spatial_logic.SpatialPoint("A", (0.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("B", (1000.0, 0.0, 0.0)),
    ]
    result = spatial_logic.dbscan(points=points, eps_ly=5.0, min_samples=2)
    assert result["cluster_count"] == 0
    assert result["noise_count"] == 2


def test_dbscan_empty():
    result = spatial_logic.dbscan(points=[], eps_ly=5.0, min_samples=2)
    assert result["cluster_count"] == 0
    assert result["noise_count"] == 0


def test_geometry_linear():
    points = [
        spatial_logic.SpatialPoint("A", (0.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("B", (10.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("C", (20.0, 0.0, 0.0)),
    ]
    geom = spatial_logic.analyze_geometry(points)
    assert geom.dominant_axis == "x"
    assert geom.linearity > 0.8  # mostly linear along x


def test_geometry_spread():
    points = [
        spatial_logic.SpatialPoint("A", (0.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("B", (10.0, 20.0, 30.0)),
    ]
    geom = spatial_logic.analyze_geometry(points)
    assert geom.spread == (10.0, 20.0, 30.0)
    assert geom.centroid == (5.0, 10.0, 15.0)


def test_nearest_neighbor_stats():
    points = [
        spatial_logic.SpatialPoint("A", (0.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("B", (10.0, 0.0, 0.0)),
    ]
    stats = spatial_logic.nearest_neighbor_stats(points)
    assert stats["mean_nn_distance"] == 10.0
    assert stats["min"] == 10.0
    assert stats["max"] == 10.0


def test_nearest_neighbor_single():
    stats = spatial_logic.nearest_neighbor_stats(
        [spatial_logic.SpatialPoint("A", (0.0, 0.0, 0.0))]
    )
    assert stats["mean_nn_distance"] == 0.0


def test_spatial_sensitivity():
    points = [
        spatial_logic.SpatialPoint("A", (0.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("B", (1.0, 0.0, 0.0)),
        spatial_logic.SpatialPoint("C", (0.0, 1.0, 0.0)),
    ]
    results = spatial_logic.spatial_sensitivity_analysis(
        points=points,
        eps_values=[1.0, 5.0],
        min_samples_values=[2],
    )
    assert "eps_1.0_min2" in results
    assert "eps_5.0_min2" in results


def test_spatial_cluster_serialization():
    cluster = spatial_logic.SpatialCluster(
        cluster_id=1,
        members=["A", "B"],
        coordinates=(5.0, 5.0, 5.0),
        radius_ly=7.07,
        density=0.1,
        parameters={"eps_ly": 10.0, "min_samples": 2},
    )
    d = cluster.to_dict()
    assert d["cluster_id"] == 1
    assert d["members"] == ["A", "B"]
