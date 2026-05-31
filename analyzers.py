"""Basic diagnostics for PX4/QGC ULog exports."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

INTERESTING_PARAM_PREFIXES = (
    "EKF2_",
    "SENS_FLOW_",
    "SENS_TFLOW",
    "MPC_",
    "COM_POS",
)


def finite_stats(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    finite = values.dropna()
    if finite.empty:
        return {
            "count": int(values.size),
            "finite_count": 0,
            "min": None,
            "mean": None,
            "median": None,
            "max": None,
            "std": None,
            "missing_count": int(values.isna().sum()),
        }
    return {
        "count": int(values.size),
        "finite_count": int(finite.size),
        "min": float(finite.min()),
        "mean": float(finite.mean()),
        "median": float(finite.median()),
        "max": float(finite.max()),
        "std": float(finite.std(ddof=0)),
        "missing_count": int(values.isna().sum()),
    }


def summarize_dataframe(df: pd.DataFrame, max_variables: int = 80) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for column in df.columns:
        if column == "time_seconds":
            continue
        if len(stats) >= max_variables:
            break
        if pd.api.types.is_numeric_dtype(df[column]):
            item = finite_stats(df[column])
            item["variable"] = column
            stats.append(item)
    return stats


def unique_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in df:
        return {}
    counts = df[column].value_counts(dropna=False)
    return {str(k): int(v) for k, v in counts.items()}


def all_nan_columns(df: pd.DataFrame, columns: list[str]) -> bool | None:
    present = [column for column in columns if column in df]
    if not present:
        return None
    return bool(df[present].apply(pd.to_numeric, errors="coerce").isna().all().all())


def parameter_snapshot(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        name: value
        for name, value in sorted(parameters.items())
        if name.startswith(INTERESTING_PARAM_PREFIXES)
    }


def build_diagnostics(
    topic_frames: dict[str, pd.DataFrame],
    parameters: dict[str, Any],
    dropouts: list[dict[str, Any]],
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "parameter_snapshot": parameter_snapshot(parameters),
        "dropout_count": len(dropouts),
        "dropout_total_seconds": float(sum(item.get("duration_seconds", 0.0) for item in dropouts)),
        "checks": [],
    }

    status = first_frame(topic_frames, "vehicle_status")
    if status is not None:
        diagnostics["nav_state_counts"] = unique_counts(status, "nav_state")
        diagnostics["failsafe_counts"] = unique_counts(status, "failsafe")
        diagnostics["gcs_connection_lost_counts"] = unique_counts(status, "gcs_connection_lost")
        if is_constant_value(status, "nav_state", 1):
            diagnostics["checks"].append({
                "level": "warning",
                "message": "vehicle_status.nav_state was 1 for the whole export; this usually means Altitude mode, not Position mode.",
            })

    flags = first_frame(topic_frames, "estimator_status_flags")
    if flags is not None:
        diagnostics["cs_opt_flow_counts"] = unique_counts(flags, "cs_opt_flow")
        diagnostics["cs_rng_hgt_counts"] = unique_counts(flags, "cs_rng_hgt")
        diagnostics["cs_yaw_align_counts"] = unique_counts(flags, "cs_yaw_align")
        if is_constant_value(flags, "cs_opt_flow", 0):
            diagnostics["checks"].append({
                "level": "warning",
                "message": "estimator_status_flags.cs_opt_flow stayed 0; EKF did not enter optical-flow fusion according to status flags.",
            })
        if is_constant_value(flags, "cs_yaw_align", 0):
            diagnostics["checks"].append({
                "level": "warning",
                "message": "estimator_status_flags.cs_yaw_align stayed 0; yaw alignment was not established.",
            })

    aid = first_frame(topic_frames, "estimator_aid_src_optical_flow")
    if aid is not None:
        diagnostics["optical_flow_fused_counts"] = unique_counts(aid, "fused")
        diagnostics["optical_flow_rejected_counts"] = unique_counts(aid, "innovation_rejected")
        diagnostics["optical_flow_test_ratio_1"] = stats_if_present(aid, "test_ratio_1")
        diagnostics["optical_flow_test_ratio_2"] = stats_if_present(aid, "test_ratio_2")
        if is_constant_value(aid, "fused", 0):
            diagnostics["checks"].append({
                "level": "warning",
                "message": "estimator_aid_src_optical_flow.fused stayed 0; optical-flow observations were not fused.",
            })

    setpoint = first_frame(topic_frames, "vehicle_local_position_setpoint")
    if setpoint is not None:
        all_nan = all_nan_columns(setpoint, ["x", "y", "vx", "vy"])
        diagnostics["local_position_setpoint_xy_vxy_all_nan"] = all_nan
        if all_nan:
            diagnostics["checks"].append({
                "level": "warning",
                "message": "vehicle_local_position_setpoint x/y/vx/vy are all NaN; horizontal position control setpoints were not active.",
            })

    distance = first_frame(topic_frames, "distance_sensor")
    if distance is not None:
        diagnostics["distance_sensor_current_distance"] = stats_if_present(distance, "current_distance")

    flow = first_frame(topic_frames, "vehicle_optical_flow")
    if flow is not None:
        diagnostics["vehicle_optical_flow_quality"] = stats_if_present(flow, "quality")
        diagnostics["vehicle_optical_flow_distance_m"] = stats_if_present(flow, "distance_m")

    return diagnostics


def first_frame(topic_frames: dict[str, pd.DataFrame], topic_name: str) -> pd.DataFrame | None:
    prefix = f"{topic_name}:"
    for key, frame in topic_frames.items():
        if key.startswith(prefix):
            return frame
    return None


def stats_if_present(df: pd.DataFrame, column: str) -> dict[str, Any] | None:
    if column not in df:
        return None
    return finite_stats(df[column])


def is_constant_value(df: pd.DataFrame, column: str, value: int | float) -> bool:
    if column not in df:
        return False
    numeric = pd.to_numeric(df[column], errors="coerce").dropna()
    return not numeric.empty and bool((numeric == value).all())


def clean_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [clean_for_json(item) for item in value]
    if isinstance(value, np.generic):
        return clean_for_json(value.item())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value
