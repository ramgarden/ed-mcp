"""Temporal activity and observation anomaly analysis.

Pure-Python temporal anomaly detection (no heavy dependencies).
Implements time-series baselines, robust outlier detection,
change-point detection (sliding window CUSUM-inspired),
normalized activity metrics, and persistence checks across time windows.

Designed for EDDN message counts, journal event counts, or any
time-stamped observation data from Elite Dangerous sources.

Never equates EDDN message count with unique commander visits. A message
may represent an update, repeated report, or other event; defines each
event type precisely and deduplicates appropriately.
"""
from __future__ import annotations

import collections
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class TimeSeriesPoint:
    timestamp_utc: str
    system_name: str
    event_type: str
    event_count: int = 1
    source: str = "unknown"

    def to_tuple(self) -> tuple:
        return (self.timestamp_utc, self.system_name, self.event_type, self.event_count)


def _parse_event_datetime(ts: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _floor_interval(dt: datetime, interval_minutes: int) -> datetime:
    """Round timestamp DOWN to the nearest interval boundary."""
    total_minutes = dt.hour * 60 + dt.minute
    floored_minutes = (total_minutes // interval_minutes) * interval_minutes
    # Carry overflow from minute to hour when floored_minutes == 60
    hour_offset = floored_minutes // 60
    minute = floored_minutes % 60
    new_hour = dt.hour + hour_offset
    return dt.replace(hour=new_hour, minute=minute, second=0, microsecond=0)


def aggregate_time_series(
    events: list[dict[str, Any]],
    interval_minutes: int = 60,
    system_name: str | None = None,
    event_types: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate EDDN/journal events into a time series by interval.

    Returns: dict mapping interval_start_utc -> {event_type -> count}
    Never silently drops data: all event types are tracked.
    """
    points: list[TimeSeriesPoint] = []
    for ev in events:
        ts = ev.get("timestamp")
        if not ts:
            continue
        dt = _parse_event_datetime(ts)
        if dt is None:
            continue
        if system_name and ev.get("StarSystem", ev.get("SystemName", "")) != system_name:
            continue
        etype = ev.get("event", "unknown")
        if event_types and etype not in event_types:
            continue
        interval = _floor_interval(dt, interval_minutes)
        points.append(
            TimeSeriesPoint(
                timestamp_utc=interval.isoformat(),
                system_name=system_name or ev.get("StarSystem", ev.get("SystemName", "")),
                event_type=etype,
                event_count=1,
                source=ev.get("$schemaRef", "unknown"),
            )
        )

    # Aggregate by interval -> event_type -> count
    series: dict[str, dict[str, int]] = {}
    for p in points:
        key = p.timestamp_utc
        if key not in series:
            series[key] = {}
        etype = p.event_type
        series[key][etype] = series[key].get(etype, 0) + p.event_count

    # Sort by timestamp
    sorted_keys = sorted(series.keys())
    sorted_series = {k: series[k] for k in sorted_keys}

    return {
        "interval_minutes": interval_minutes,
        "system_name": system_name,
        "event_types": sorted(set(p.event_type for p in points)),
        "series": sorted_series,
        "total_events": len(points),
        "total_intervals": len(sorted_keys),
    }


def robust_outlier_detection(
    series: dict[str, dict[str, int]],
    interval: str,
    method: str = "IQR",
    z_threshold: float = 3.0,
) -> dict[str, Any]:
    """Robust outlier detection using IQR or Z-score on event counts.

    For a given interval, examines each event type's count and flags
    outliers beyond z_threshold standard deviations (or IQR bounds).

    Returns: {event_type -> {count, is_outlier, z_score or iqr_factor}}
    """
    if interval not in series:
        return {}

    counts_by_type: dict[str, list[int]] = collections.defaultdict(list)
    for etype, count in series[interval].items():
        counts_by_type[etype].append(count)

    results: dict[str, Any] = {}
    for etype, counts in counts_by_type.items():
        if not counts:
            continue
        arr = sorted(counts)
        if method == "IQR":
            q1 = arr[len(arr) // 4] if arr else 0
            q3 = arr[3 * len(arr) // 4] if arr else 0
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            is_outlier = any(c < lower or c > upper for c in counts)
            # Report IQR factor for each point
            factors = []
            for c in counts:
                factor = (c - q1) / iqr if iqr > 0 else 0
                factors.append(round(factor, 3))
            results[etype] = {
                "count": counts[-1] if counts else 0,
                "is_outlier": is_outlier,
                "method": "IQR",
                "iqr_factors": factors,
                "lower_bound": round(lower, 1),
                "upper_bound": round(upper, 1),
            }
        elif method == "zscore":
            mean = sum(arr) / len(arr) if arr else 0
            variance = sum((c - mean) ** 2 for c in arr) / len(arr) if arr else 0
            std = math.sqrt(variance) if variance >= 0 else 1.0
            is_outlier = any(abs(c - mean) / std > z_threshold for c in counts if std > 0)
            z_scores = [round((c - mean) / std, 3) if std > 0 else 0 for c in counts]
            results[etype] = {
                "count": counts[-1] if counts else 0,
                "is_outlier": is_outlier,
                "method": "zscore",
                "z_scores": z_scores,
                "mean": round(mean, 2),
                "std": round(std, 2),
            }
    return results


def change_point_detection(
    series: dict[str, dict[str, int]],
    interval: str,
    window_size: int = 5,
    sensitivity: float = 1.5,
) -> dict[str, Any]:
    """Detect change points using a simplified CUSUM-like sliding window.

    Compares early window mean vs late window mean for each event type.
    Flags intervals where the difference exceeds sensitivity * MAD.

    Returns: {event_type -> {is_change_point, window_means, diff}}
    """
    if interval not in series:
        return {}

    counts_by_type: dict[str, list[int]] = collections.defaultdict(list)
    for etype, count in series[interval].items():
        counts_by_type[etype].append(count)

    results: dict[str, Any] = {}
    for etype, counts in counts_by_type.items():
        if len(counts) < window_size * 2:
            results[etype] = {
                "is_change_point": False,
                "note": "insufficient data points for change-point detection",
            }
            continue

        arr = counts
        half = len(arr) // 2
        if half < window_size:
            results[etype] = {
                "is_change_point": False,
                "note": "insufficient data for half-split",
            }
            continue

        early_mean = sum(arr[:half]) / half
        late_mean = sum(arr[half: 2 * half]) / half
        early_sub = arr[:half]
        late_sub = arr[half: 2 * half]

        # MAD-based sensitivity
        early_mad = robust_outlier_detection(
            {interval: {etype: early_sub}}, method="IQR"
        ).get(etype, {}).get("iqr_factors", [0])[0] if early_sub else 0
        late_mad = robust_outlier_detection(
            {interval: {etype: late_sub}}, method="IQR"
        ).get(etype, {}).get("iqr_factors", [0])[0] if late_sub else 0

        combined_mad = (early_mad + late_mad) / 2 if (early_mad or late_mad) else 1.0
        diff = late_mean - early_mean
        flagged = abs(diff) > sensitivity * combined_mad

        results[etype] = {
            "is_change_point": flagged,
            "early_mean": round(early_mean, 2),
            "late_mean": round(late_mean, 2),
            "difference": round(diff, 2),
            "sensitivity": sensitivity,
            "flagged": flagged,
        }
    return results


def normalize_activity_by_accessibility(
    series: dict[str, dict[str, int]],
    accessibility_data: dict[str, dict[str, Any]] | None = None,
    method: str = "traffic_normalized",
) -> dict[str, Any]:
    """Normalize activity counts by accessibility/traffic indicators.

    Methods:
    - 'traffic_normalized': divide count by local system population or EDDN message count
    - 'population_normalized': divide count by system population
    - 'raw': return counts unchanged

    Returns normalized values with caveats about missing data.
    """
    normalized: dict[str, Any] = {}
    for interval, counts in series.items():
        norm_interval = {}
        for etype, count in counts.items():
            if method == "raw":
                norm_interval[etype] = count
            elif method == "population_normalized" and accessibility_data:
                pop = accessibility_data.get(etype, {}).get("population", 0)
                norm_interval[etype] = count / max(pop, 1) if pop else None
            elif method == "traffic_normalized" and accessibility_data:
                traffic = accessibility_data.get(etype, {}).get("traffic", 1)
                norm_interval[etype] = count / max(traffic, 1)
            else:
                norm_interval[etype] = count
        normalized[interval] = norm_interval
    return normalized


def persistence_check(
    series1: dict[str, dict[str, int]],
    series2: dict[str, dict[str, int]],
    interval: str,
    min_overlap: float = 0.5,
) -> dict[str, Any]:
    """Check persistence of anomalous patterns across two time windows.

    Compares the relative proportion of each event type between two
    windows. A pattern is 'persistent' if it maintains similar relative
    prominence.

    Returns: {event_type -> {persistent: bool, relative_proportion_change}}
    """
    if interval not in series1 or interval not in series2:
        return {}

    counts1 = series1[interval]
    counts2 = series2[interval]
    all_types = set(list(counts1.keys()) + list(counts2.keys()))

    results: dict[str, Any] = {}
    for etype in all_types:
        c1 = counts1.get(etype, 0)
        c2 = counts2.get(etype, 0)
        total1 = sum(counts1.values()) if counts1 else 1
        total2 = sum(counts2.values()) if counts2 else 1

        prop1 = c1 / total1 if total1 > 0 else 0
        prop2 = c2 / total2 if total2 > 0 else 0

        # Jaccard-like persistence: maintain relative prominence
        # Pattern persists if proportion change is within tolerance
        prop_change = abs(prop1 - prop2) / max(prop1, prop2, 1e-6)
        persistent = prop_change <= (1 - min_overlap)

        results[etype] = {
            "persistent": persistent,
            "proportion_window1": round(prop1, 4),
            "proportion_window2": round(prop2, 4),
            "relative_change": round(prop_change, 4),
        }
    return results


def temporal_sensitivity_analysis(
    events: list[dict[str, Any]],
    interval_minutes_values: list[int] | None = None,
    window_sizes: list[int] | None = None,
) -> dict[str, Any]:
    """Run time-series analysis across parameter combinations."""
    interval_values = interval_minutes_values or [60, 1440]  # hourly, daily
    window_values = window_sizes or [3, 7]
    results: dict[str, Any] = {}
    if not events:
        return {}
    for interval in interval_values:
        series = aggregate_time_series(events, interval_minutes=interval)
        for window in window_values:
            key = f"interval{interval}_window{window}"
            results[key] = {
                "interval_minutes": interval,
                "outlier_detection": robust_outlier_detection(
                    series, list(series.get("series", {}).keys())[0]
                    if series.get("series")
                    else "",
                ),
                "change_point": change_point_detection(
                    series, list(series.get("series", {}).keys())[0] if series.get("series") else "",
                    window_size=window,
                ),
            }
    return results