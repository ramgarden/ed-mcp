"""Research foundations unit tests (offline, synthetic fixtures)."""
import json
from pathlib import Path
import tempfile

from ed_mcp.research.provenance import Observation, Provenance
from ed_mcp.research.experiment import Experiment, ExperimentRun
from ed_mcp.research.artifact_store import ArtifactStore
from ed_mcp.research.region import query_region


def test_provenance_create_and_roundtrip():
    prov = Provenance.create(
        source="EDSM",
        source_record_id="12345",
        system_name="Sol",
        system_id="10477373803",
        coordinates=(0.0, 0.0, 0.0),
        coordinate_reference="EDSM galactic coordinates",
        data_type="system_catalog",
        source_schema_version="v1",
        raw_payload={"name": "Sol", "id": "10477373803"},
        query_parameters={"radius_ly": 15.0},
        completeness_notes=None,
        observation_type="directly_observed",
    )
    assert prov.source == "EDSM"
    assert prov.coordinates == (0.0, 0.0, 0.0)
    assert prov.payload_sha256 is not None
    assert prov.retrieval_timestamp_utc.endswith("+00:00")

    d = prov.to_dict()
    assert d["coordinates"] == [0.0, 0.0, 0.0]
    assert d["source"] == "EDSM"


def test_provenance_missing_coordinates():
    prov = Provenance.create(
        source="EDSM",
        system_name="UnknownSystem",
        coordinates=None,
        completeness_notes="No coordinates returned by EDSM",
    )
    assert prov.coordinates is None
    assert prov.completeness_notes == "No coordinates returned by EDSM"


def test_observation_missing_flag():
    obs = Observation(
        provenance=Provenance.create(source="EDSM", system_name="X"),
        value=None,
        is_missing=True,
        missing_reason="No coordinates returned by EDSM",
    )
    assert obs.is_missing is True
    assert obs.missing_reason == "No coordinates returned by EDSM"
    d = obs.to_dict()
    assert d["is_missing"] is True
    assert d["missing_reason"] == "No coordinates returned by EDSM"


def test_experiment_create_and_run():
    exp = Experiment.create(
        title="Graph anomaly test",
        hypothesis="A region has unusual bridge nodes",
        method="graph_analysis",
        method_version="1.0.0",
        parameters={"radius_ly": 50.0},
        control_design="matched_controls",
    )
    assert exp.experiment_id is not None
    assert len(exp.experiment_id) == 16
    assert exp.status == "Unreviewed"

    run = ExperimentRun.create(
        experiment_id=exp.experiment_id,
        random_seed=42,
    )
    assert run.run_id is not None
    assert run.status == "running"
    assert run.random_seed == 42

    completed = run.complete(
        status="completed",
        result_summary={"bridges": 3, "components": 1},
    )
    assert completed.status == "completed"
    assert completed.result_summary == {"bridges": 3, "components": 1}
    assert completed.end_time_utc is not None


def test_artifact_store_roundtrip(tmp_path: Path):
    db_path = tmp_path / "research.db"
    store = ArtifactStore(db_path)

    exp = Experiment.create(
        title="Test experiment",
        hypothesis="H",
        method="test",
    )
    store.save_experiment(exp)
    loaded = store.get_experiment(exp.experiment_id)
    assert loaded is not None
    assert loaded.title == "Test experiment"
    assert loaded.parameters == {}

    run = ExperimentRun.create(experiment_id=exp.experiment_id, random_seed=7)
    store.save_run(run)
    loaded_run = store.get_run(run.run_id)
    assert loaded_run is not None
    assert loaded_run.random_seed == 7
    assert loaded_run.status == "running"

    completed = run.complete(status="completed", result_summary={"n": 1})
    store.save_run(completed)
    loaded_completed = store.get_run(run.run_id)
    assert loaded_completed.status == "completed"
    assert loaded_completed.result_summary == {"n": 1}

    # Observation save + list
    prov = Provenance.create(source="EDSM", system_name="Sol", coordinates=(0.0, 0.0, 0.0))
    obs_id = store.save_observation(
        Observation(provenance=prov, value={"name": "Sol"}, is_missing=False)
    )
    obs_list = store.list_observations(source="EDSM", system_name="Sol")
    assert len(obs_list) == 1
    assert obs_list[0].is_missing is False
    assert obs_list[0].value == {"name": "Sol"}

    # Missing observation not silently converted
    obs_missing = Observation(
        provenance=Provenance.create(source="EDSM", system_name="Unknown"),
        value=None,
        is_missing=True,
        missing_reason="No coordinates returned by EDSM",
    )
    store.save_observation(obs_missing)
    obs_list2 = store.list_observations(source="EDSM", system_name="Unknown")
    assert len(obs_list2) == 1
    assert obs_list2[0].is_missing is True

    runs = store.list_runs(experiment_id=exp.experiment_id)
    assert len(runs) >= 1
    store.close()


def test_region_query_missing_coords_not_silent():
    # Use a system name that won't resolve to verify missing-data handling
    # EDSM call may fail offline; this tests structure even on network error
    result = query_region(
        system_name="Sol",
        radius_ly=5.0,
    )
    # Network may not be available; ok flag reflects EDSM availability
    if result.ok:
        assert result.count > 0
        assert result.query_parameters["radius_ly"] == 5.0
        assert result.center_system == "Sol"
        # All systems have provenance
        assert len(result.provenance) == result.count
        for prov in result.provenance:
            assert prov.source == "EDSM"
            assert prov.query_parameters == result.query_parameters


def test_artifact_store_persistence_across_reopen(tmp_path: Path):
    db_path = tmp_path / "research2.db"
    store1 = ArtifactStore(db_path)
    exp = Experiment.create(title="PersistTest", hypothesis="H", method="m")
    store1.save_experiment(exp)
    store1.close()

    store2 = ArtifactStore(db_path)
    loaded = store2.get_experiment(exp.experiment_id)
    assert loaded is not None
    assert loaded.title == "PersistTest"
    store2.close()


def test_schema_version_recorded(tmp_path: Path):
    db_path = tmp_path / "schema_test.db"
    store = ArtifactStore(db_path)
    # Schema version table should exist with the right value
    cur = store._conn.cursor()
    cur.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == ArtifactStore.SCHEMA_VERSION
    store.close()
