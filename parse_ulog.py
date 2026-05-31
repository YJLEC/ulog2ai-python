"""Command-line PX4/QGC ULog exporter for AI-assisted analysis."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyulog import ULog

from analyzers import build_diagnostics, clean_for_json, summarize_dataframe
from exporters import (
    build_jsonl_chunks,
    build_markdown,
    dataframe_to_csv,
    write_csv,
    write_json,
    write_jsonl,
)
from presets import get_preset

ULOG_MAGIC = b"ULog"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export one PX4/QGroundControl .ulg file into AI-readable Markdown, JSON, JSONL, and CSV files.",
    )
    parser.add_argument("ulg_file", help="Path to one .ulg file")
    parser.add_argument("--out", help="Output directory. Default: <ulg stem>_ai_export")
    parser.add_argument(
        "--preset",
        default="flow",
        choices=["basic", "flow", "full"],
        help="Topic preset to export. Default: flow",
    )
    parser.add_argument(
        "--max-rows-per-topic",
        type=int,
        default=20000,
        help="Downsample each topic CSV to at most this many rows. Default: 20000",
    )
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=8,
        help="Number of representative rows stored in JSON summaries. Default: 8",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_dir = export_ulog(
            Path(args.ulg_file),
            Path(args.out) if args.out else None,
            preset=args.preset,
            max_rows_per_topic=args.max_rows_per_topic,
            sample_rows=args.sample_rows,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("AI export complete:")
    print(f"  {output_dir / 'ulog_ai_packet.md'}")
    print(f"  {output_dir / 'ulog_ai_summary.json'}")
    print(f"  {output_dir / 'ulog_ai_chunks.jsonl'}")
    print(f"  {output_dir / 'topics_csv'}")
    return 0


def export_ulog(
    ulg_file: Path,
    output_dir: Path | None,
    preset: str = "flow",
    max_rows_per_topic: int = 20000,
    sample_rows: int = 8,
) -> Path:
    ulg_file = ulg_file.expanduser().resolve()
    if not ulg_file.is_file():
        raise FileNotFoundError(f"ULog file not found: {ulg_file}")
    validate_ulog_magic(ulg_file)

    if output_dir is None:
        output_dir = ulg_file.with_name(f"{ulg_file.stem}_ai_export")
    output_dir = output_dir.expanduser().resolve()
    topics_dir = output_dir / "topics_csv"
    topics_dir.mkdir(parents=True, exist_ok=True)

    ulog = ULog(str(ulg_file))
    available_rows = available_topics(ulog)
    available_names = list(dict.fromkeys(row["topic"] for row in available_rows))
    requested_topics = get_preset(preset, available_names)
    missing_topics = [topic for topic in requested_topics if topic not in available_names]

    write_csv(output_dir / "available_topics.csv", available_rows, ["topic", "instance", "message_count"])

    parameters = read_parameters(ulog)
    write_csv(
        output_dir / "parameters.csv",
        [{"parameter": name, "value": value} for name, value in sorted(parameters.items())],
        ["parameter", "value"],
    )

    logged_output = read_logged_output(ulog)
    write_csv(output_dir / "logged_output.csv", logged_output, ["time_seconds", "level", "message"])

    dropouts = read_dropouts(ulog)
    write_csv(output_dir / "dropout_intervals.csv", dropouts, ["start_seconds", "duration_seconds"])

    topic_frames: dict[str, pd.DataFrame] = {}
    selected_topic_reports: list[dict[str, Any]] = []

    for dataset in ulog.data_list:
        topic_name = dataset.name
        if topic_name not in requested_topics:
            continue
        instance = int(getattr(dataset, "multi_id", 0) or 0)
        report = export_dataset(
            dataset,
            topics_dir,
            output_dir,
            max_rows_per_topic=max_rows_per_topic,
            sample_rows=sample_rows,
        )
        selected_topic_reports.append(report)
        if not report.get("error"):
            topic_frames[f"{topic_name}:{instance}"] = report.pop("_frame")

    diagnostics = build_diagnostics(topic_frames, parameters, dropouts)

    start_seconds, end_seconds = log_time_bounds(topic_frames)
    summary = {
        "source_file": str(ulg_file),
        "sha256": sha256_file(ulg_file),
        "preset": preset,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "duration_seconds": (end_seconds - start_seconds) if start_seconds is not None and end_seconds is not None else None,
        "num_available_topics": len(available_rows),
        "available_topics_csv": "available_topics.csv",
        "parameters_csv": "parameters.csv",
        "logged_output_csv": "logged_output.csv",
        "dropout_intervals_csv": "dropout_intervals.csv",
        "missing_topics": missing_topics,
        "selected_topics": selected_topic_reports,
        "logged_output_preview": logged_output[:50],
        "diagnostics": diagnostics,
    }

    write_json(output_dir / "ulog_ai_summary.json", summary)
    write_jsonl(output_dir / "ulog_ai_chunks.jsonl", build_jsonl_chunks(summary))
    (output_dir / "ulog_ai_packet.md").write_text(build_markdown(clean_for_json(summary)), encoding="utf-8")

    return output_dir


def validate_ulog_magic(path: Path) -> None:
    with path.open("rb") as handle:
        magic = handle.read(4)
    if magic != ULOG_MAGIC:
        raise ValueError(f"Invalid file format: {path} does not start with ULog magic bytes")


def available_topics(ulog: ULog) -> list[dict[str, Any]]:
    rows = []
    for dataset in ulog.data_list:
        rows.append({
            "topic": dataset.name,
            "instance": int(getattr(dataset, "multi_id", 0) or 0),
            "message_count": dataset.data["timestamp"].shape[0] if "timestamp" in dataset.data else 0,
        })
    rows.sort(key=lambda item: (item["topic"], item["instance"]))
    return rows


def read_parameters(ulog: ULog) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    for name, value in getattr(ulog, "initial_parameters", {}).items():
        parameters[str(name)] = python_scalar(value)
    return parameters


def read_logged_output(ulog: ULog) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in getattr(ulog, "logged_messages", []) or []:
        timestamp = getattr(item, "timestamp", None)
        level = getattr(item, "log_level_str", None) or getattr(item, "log_level", "")
        message = getattr(item, "message", "")
        rows.append({
            "time_seconds": us_to_seconds(timestamp),
            "level": str(level),
            "message": str(message).strip(),
        })
    return rows


def read_dropouts(ulog: ULog) -> list[dict[str, Any]]:
    by_start: dict[float, float] = {}
    for dropout in getattr(ulog, "dropouts", []) or []:
        timestamp = getattr(dropout, "timestamp", None)
        duration = getattr(dropout, "duration", None)
        start_seconds = us_to_seconds(timestamp)
        duration_seconds = ms_to_seconds(duration)
        if start_seconds is None or duration_seconds is None or duration_seconds <= 0:
            continue
        by_start[start_seconds] = max(by_start.get(start_seconds, 0.0), duration_seconds)
    return [
        {"start_seconds": start, "duration_seconds": duration}
        for start, duration in sorted(by_start.items())
    ]


def export_dataset(
    dataset: Any,
    topics_dir: Path,
    output_dir: Path,
    max_rows_per_topic: int,
    sample_rows: int,
) -> dict[str, Any]:
    topic_name = dataset.name
    instance = int(getattr(dataset, "multi_id", 0) or 0)
    csv_name = f"{safe_name(topic_name)}_inst{instance}.csv"
    csv_path = topics_dir / csv_name

    report: dict[str, Any] = {
        "name": topic_name,
        "instance": instance,
        "csv_file": str(csv_path.relative_to(output_dir)),
        "rows": 0,
        "estimated_rate_hz": None,
        "downsampled": False,
        "stats": [],
        "sample": [],
        "error": "",
    }

    try:
        frame = dataset_to_dataframe(dataset)
        report["rows"] = int(len(frame))
        report["estimated_rate_hz"] = estimate_rate_hz(frame)
        report["stats"] = summarize_dataframe(frame)
        report["sample"] = sample_records(frame, sample_rows)

        csv_frame = frame
        if len(csv_frame) > max_rows_per_topic:
            csv_frame = downsample_frame(csv_frame, max_rows_per_topic)
            report["downsampled"] = True
            report["csv_note"] = "Downsampled for AI review; inspect the source .ulg for full fidelity."
        dataframe_to_csv(csv_path, csv_frame)
        report["_frame"] = frame
    except Exception as exc:
        report["error"] = str(exc)
    return report


def dataset_to_dataframe(dataset: Any) -> pd.DataFrame:
    data: dict[str, Any] = {}
    for name, values in dataset.data.items():
        array = np.asarray(values)
        if name == "timestamp":
            data["time_seconds"] = array.astype(float) / 1_000_000.0
        elif array.ndim == 1:
            data[safe_column(name)] = array
        else:
            flattened = array.reshape((array.shape[0], -1))
            for idx in range(flattened.shape[1]):
                data[f"{safe_column(name)}_{idx + 1}"] = flattened[:, idx]
    frame = pd.DataFrame(data)
    if "time_seconds" in frame:
        first = frame.pop("time_seconds")
        frame.insert(0, "time_seconds", first)
    return frame


def sample_records(frame: pd.DataFrame, sample_rows: int) -> list[dict[str, Any]]:
    if frame.empty or sample_rows <= 0:
        return []
    indexes = np.linspace(0, len(frame) - 1, min(sample_rows, len(frame)), dtype=int)
    return [
        {key: python_scalar(value) for key, value in row.items()}
        for row in frame.iloc[sorted(set(indexes))].to_dict(orient="records")
    ]


def downsample_frame(frame: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    indexes = np.linspace(0, len(frame) - 1, max_rows, dtype=int)
    return frame.iloc[sorted(set(indexes))].reset_index(drop=True)


def estimate_rate_hz(frame: pd.DataFrame) -> float | None:
    if "time_seconds" not in frame or len(frame) < 2:
        return None
    start = pd.to_numeric(frame["time_seconds"].iloc[0], errors="coerce")
    end = pd.to_numeric(frame["time_seconds"].iloc[-1], errors="coerce")
    if pd.isna(start) or pd.isna(end) or end <= start:
        return None
    return float((len(frame) - 1) / (end - start))


def log_time_bounds(topic_frames: dict[str, pd.DataFrame]) -> tuple[float | None, float | None]:
    starts = []
    ends = []
    for frame in topic_frames.values():
        if "time_seconds" in frame and not frame.empty:
            starts.append(float(frame["time_seconds"].iloc[0]))
            ends.append(float(frame["time_seconds"].iloc[-1]))
    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def us_to_seconds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 1_000_000.0
    except (TypeError, ValueError):
        return None


def ms_to_seconds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 1_000.0
    except (TypeError, ValueError):
        return None


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)


def safe_column(value: str) -> str:
    return safe_name(value.replace("[", "_").replace("]", ""))


def python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if pd.isna(value) if not isinstance(value, (list, tuple, dict, np.ndarray)) else False:
        return None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
