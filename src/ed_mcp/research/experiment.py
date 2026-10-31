"""Research experiment lifecycle management.

Defines experiments (title, hypothesis, method, parameters, control design)
and runs (run ID, experiment ID, start/end time, software version, model
provider metadata, random seed, status). All immutable dataclasses with
serialization round-trips.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Experiment:
    """A bounded scientific research experiment definition."""

    experiment_id: str
    title: str
    hypothesis: str
    method: str
    method_version: str
    parameters: dict[str, Any]
    control_design: str | None
    status: str = "Unreviewed"

    @classmethod
    def create(
        cls,
        *,
        title: str,
        hypothesis: str,
        method: str,
        method_version: str = "1.0.0",
        parameters: dict[str, Any] | None = None,
        control_design: str | None = None,
        status: str = "Unreviewed",
    ) -> "Experiment":
        exp_id = hashlib.sha256(
            f"{title}:{method}:{method_version}".encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            experiment_id=exp_id,
            title=title,
            hypothesis=hypothesis,
            method=method,
            method_version=method_version,
            parameters=parameters or {},
            control_design=control_design,
            status=status,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentRun:
    """A single execution of an experiment."""

    run_id: str
    experiment_id: str
    start_time_utc: str
    end_time_utc: str | None
    software_version: str
    model_provider: str | None
    model_identifier: str | None
    random_seed: int | None
    status: str
    result_summary: dict[str, Any] | None = None
    error_message: str | None = None

    @classmethod
    def create(
        cls,
        *,
        experiment_id: str,
        software_version: str = "ed-mcp/0.1.0",
        model_provider: str | None = None,
        model_identifier: str | None = None,
        random_seed: int | None = None,
        status: str = "running",
    ) -> "ExperimentRun":
        now = datetime_now()
        run_id = hashlib.sha256(
            f"{experiment_id}:{now}:{software_version}".encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            run_id=run_id,
            experiment_id=experiment_id,
            start_time_utc=now,
            end_time_utc=None,
            software_version=software_version,
            model_provider=model_provider,
            model_identifier=model_identifier,
            random_seed=random_seed,
            status=status,
        )

    def complete(
        self,
        *,
        status: str = "completed",
        result_summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> "ExperimentRun":
        return ExperimentRun(
            run_id=self.run_id,
            experiment_id=self.experiment_id,
            start_time_utc=self.start_time_utc,
            end_time_utc=datetime_now(),
            software_version=self.software_version,
            model_provider=self.model_provider,
            model_identifier=self.model_identifier,
            random_seed=self.random_seed,
            status=status,
            result_summary=result_summary,
            error_message=error_message,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def datetime_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
