"""SQLite-backed research artifact store.

Persists experiment definitions, runs, source observations, and derived
results as bounded SQLite records with deterministic serialization.

Uses SQLite for portability and offline operation. Keeps raw observations
distinct from derived measurements and interpretations.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ed_mcp.research.experiment import Experiment, ExperimentRun
from ed_mcp.research.provenance import Observation, Provenance


class ArtifactStore:
    """SQLite-backed store for research artifacts (experiments, runs, observations)."""

    SCHEMA_VERSION = "1.0.0"

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                hypothesis TEXT NOT NULL,
                method TEXT NOT NULL,
                method_version TEXT NOT NULL,
                parameters TEXT NOT NULL,
                control_design TEXT,
                status TEXT NOT NULL DEFAULT 'Unreviewed'
            );
            CREATE TABLE IF NOT EXISTS experiment_runs (
                run_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                start_time_utc TEXT NOT NULL,
                end_time_utc TEXT,
                software_version TEXT NOT NULL,
                model_provider TEXT,
                model_identifier TEXT,
                random_seed INTEGER,
                status TEXT NOT NULL,
                result_summary TEXT,
                error_message TEXT
            );
            CREATE TABLE IF NOT EXISTS observations (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_record_id TEXT,
                retrieval_timestamp_utc TEXT NOT NULL,
                event_timestamp_utc TEXT,
                system_name TEXT,
                system_id TEXT,
                coordinates_x REAL,
                coordinates_y REAL,
                coordinates_z REAL,
                coordinate_reference TEXT,
                data_type TEXT,
                source_schema_version TEXT,
                payload_sha256 TEXT,
                query_parameters TEXT,
                pagination_cursor TEXT,
                completeness_notes TEXT,
                observation_type TEXT NOT NULL DEFAULT 'directly_observed',
                value TEXT,
                is_missing INTEGER NOT NULL DEFAULT 0,
                missing_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_observations_system
                ON observations(system_name);
            CREATE INDEX IF NOT EXISTS idx_observations_source
                ON observations(source);
            CREATE INDEX IF NOT EXISTS idx_runs_experiment
                ON experiment_runs(experiment_id);
            """
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (self.SCHEMA_VERSION,),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save_experiment(self, experiment: Experiment) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO experiments
                (experiment_id, title, hypothesis, method, method_version,
                 parameters, control_design, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment.experiment_id,
                experiment.title,
                experiment.hypothesis,
                experiment.method,
                experiment.method_version,
                json.dumps(experiment.parameters),
                experiment.control_design,
                experiment.status,
            ),
        )
        self._conn.commit()

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return Experiment(
            experiment_id=row["experiment_id"],
            title=row["title"],
            hypothesis=row["hypothesis"],
            method=row["method"],
            method_version=row["method_version"],
            parameters=json.loads(row["parameters"] or "{}"),
            control_design=row["control_design"],
            status=row["status"],
        )

    def save_run(self, run: ExperimentRun) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO experiment_runs
                (run_id, experiment_id, start_time_utc, end_time_utc,
                 software_version, model_provider, model_identifier,
                 random_seed, status, result_summary, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.experiment_id,
                run.start_time_utc,
                run.end_time_utc,
                run.software_version,
                run.model_provider,
                run.model_identifier,
                run.random_seed,
                run.status,
                json.dumps(run.result_summary) if run.result_summary is not None else None,
                run.error_message,
            ),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> ExperimentRun | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM experiment_runs WHERE run_id = ?",
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return ExperimentRun(
            run_id=row["run_id"],
            experiment_id=row["experiment_id"],
            start_time_utc=row["start_time_utc"],
            end_time_utc=row["end_time_utc"],
            software_version=row["software_version"],
            model_provider=row["model_provider"],
            model_identifier=row["model_identifier"],
            random_seed=row["random_seed"],
            status=row["status"],
            result_summary=json.loads(row["result_summary"]) if row["result_summary"] else None,
            error_message=row["error_message"],
        )

    def list_runs(self, experiment_id: str | None = None) -> list[ExperimentRun]:
        cur = self._conn.cursor()
        if experiment_id:
            cur.execute(
                "SELECT * FROM experiment_runs WHERE experiment_id = ? ORDER BY start_time_utc DESC",
                (experiment_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM experiment_runs ORDER BY start_time_utc DESC"
            )
        return [
            ExperimentRun(
                run_id=r["run_id"],
                experiment_id=r["experiment_id"],
                start_time_utc=r["start_time_utc"],
                end_time_utc=r["end_time_utc"],
                software_version=r["software_version"],
                model_provider=r["model_provider"],
                model_identifier=r["model_identifier"],
                random_seed=r["random_seed"],
                status=r["status"],
                result_summary=json.loads(r["result_summary"]) if r["result_summary"] else None,
                error_message=r["error_message"],
            )
            for r in cur.fetchall()
        ]

    def save_observation(self, observation: Observation) -> int:
        cur = self._conn.cursor()
        coords = observation.provenance.coordinates
        cur.execute(
            """
            INSERT INTO observations
                (source, source_record_id, retrieval_timestamp_utc,
                 event_timestamp_utc, system_name, system_id,
                 coordinates_x, coordinates_y, coordinates_z,
                 coordinate_reference, data_type, source_schema_version,
                 payload_sha256, query_parameters, pagination_cursor,
                 completeness_notes, observation_type, value, is_missing,
                 missing_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.provenance.source,
                observation.provenance.source_record_id,
                observation.provenance.retrieval_timestamp_utc,
                observation.provenance.event_timestamp_utc,
                observation.provenance.system_name,
                observation.provenance.system_id,
                coords[0] if coords else None,
                coords[1] if coords else None,
                coords[2] if coords else None,
                observation.provenance.coordinate_reference,
                observation.provenance.data_type,
                observation.provenance.source_schema_version,
                observation.provenance.payload_sha256,
                json.dumps(observation.provenance.query_parameters)
                if observation.provenance.query_parameters
                else None,
                observation.provenance.pagination_cursor,
                observation.provenance.completeness_notes,
                observation.provenance.observation_type,
                json.dumps(observation.value),
                1 if observation.is_missing else 0,
                observation.missing_reason,
            ),
        )
        self._conn.commit()
        return cur.lastrowid or 0

    def list_observations(
        self,
        *,
        source: str | None = None,
        system_name: str | None = None,
        limit: int = 100,
    ) -> list[Observation]:
        cur = self._conn.cursor()
        params: list[Any] = []
        where_clauses: list[str] = []
        if source is not None:
            where_clauses.append("source = ?")
            params.append(source)
        if system_name is not None:
            where_clauses.append("system_name = ?")
            params.append(system_name)
        sql = "SELECT * FROM observations"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
        observations: list[Observation] = []
        for r in rows:
            provenance = Provenance(
                source=r["source"],
                source_record_id=r["source_record_id"],
                retrieval_timestamp_utc=r["retrieval_timestamp_utc"],
                event_timestamp_utc=r["event_timestamp_utc"],
                system_name=r["system_name"],
                system_id=r["system_id"],
                coordinates=(
                    (r["coordinates_x"], r["coordinates_y"], r["coordinates_z"])
                    if r["coordinates_x"] is not None
                    else None
                ),
                coordinate_reference=r["coordinate_reference"],
                data_type=r["data_type"],
                source_schema_version=r["source_schema_version"],
                payload_sha256=r["payload_sha256"],
                query_parameters=json.loads(r["query_parameters"])
                if r["query_parameters"]
                else None,
                pagination_cursor=r["pagination_cursor"],
                completeness_notes=r["completeness_notes"],
                observation_type=r["observation_type"],
            )
            observations.append(
                Observation(
                    provenance=provenance,
                    value=json.loads(r["value"]) if r["value"] is not None else None,
                    is_missing=bool(r["is_missing"]),
                    missing_reason=r["missing_reason"],
                )
            )
        return observations
