"""Export helpers for the ULog AI export tool."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from analyzers import clean_for_json


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(clean_for_json(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_jsonl(path: Path, chunks: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(clean_for_json(chunk), ensure_ascii=False))
            handle.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def dataframe_to_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def build_markdown(summary: dict[str, Any]) -> str:
    diagnostics = summary.get("diagnostics", {})
    lines: list[str] = [
        "# ULog AI Analysis Packet",
        "",
        "## How to ask an AI",
        (
            "Analyze this PX4/QGroundControl ULog export. Start with flight timeline, "
            "mode state, failsafe or error messages, estimator health, optical-flow "
            "fusion, range finder data, attitude tracking, actuator saturation, and "
            "battery anomalies. Cite exact CSV files and time_seconds values for every claim."
        ),
        "",
        "## Source",
        f"- Source file: `{summary.get('source_file', '')}`",
        f"- SHA256: `{summary.get('sha256', '')}`",
        f"- Log start seconds: `{summary.get('start_seconds', '')}`",
        f"- Log end seconds: `{summary.get('end_seconds', '')}`",
        f"- Duration seconds: `{summary.get('duration_seconds', '')}`",
        f"- Available topics: `{summary.get('num_available_topics', '')}`",
        "",
        "## Main Files",
        "- `ulog_ai_summary.json`: compact machine-readable summary",
        "- `ulog_ai_chunks.jsonl`: chunked records for local/private LLMs",
        "- `available_topics.csv`: all ULog topics and instance message counts",
        "- `logged_output.csv`: PX4 log messages when available",
        "- `parameters.csv`: parameter snapshot",
        "- `dropout_intervals.csv`: logging dropouts",
        "- `topics_csv/*.csv`: flattened selected topic data",
        "",
    ]

    checks = diagnostics.get("checks", [])
    if checks:
        lines.append("## Key Checks")
        for check in checks:
            lines.append(f"- {check.get('level', 'info').upper()}: {check.get('message', '')}")
        lines.append("")

    lines.extend([
        "## Diagnostics",
        f"- `nav_state_counts`: `{diagnostics.get('nav_state_counts', {})}`",
        f"- `cs_opt_flow_counts`: `{diagnostics.get('cs_opt_flow_counts', {})}`",
        f"- `optical_flow_fused_counts`: `{diagnostics.get('optical_flow_fused_counts', {})}`",
        f"- `optical_flow_rejected_counts`: `{diagnostics.get('optical_flow_rejected_counts', {})}`",
        f"- `local_position_setpoint_xy_vxy_all_nan`: `{diagnostics.get('local_position_setpoint_xy_vxy_all_nan', '')}`",
        f"- `dropout_count`: `{diagnostics.get('dropout_count', 0)}`",
        f"- `dropout_total_seconds`: `{diagnostics.get('dropout_total_seconds', 0)}`",
        "",
        "## Exported Topics",
    ])

    for topic in summary.get("selected_topics", []):
        if topic.get("error"):
            lines.append(
                f"- `{topic.get('name')}` instance `{topic.get('instance')}`: "
                f"export failed: {topic.get('error')}"
            )
        else:
            note = " downsampled" if topic.get("downsampled") else ""
            lines.append(
                f"- `{topic.get('name')}` instance `{topic.get('instance')}`: "
                f"`{topic.get('csv_file')}`, rows `{topic.get('rows')}`, "
                f"rate Hz `{topic.get('estimated_rate_hz')}`{note}"
            )

    missing = summary.get("missing_topics", [])
    if missing:
        lines.extend(["", "## Missing Requested Topics"])
        for topic in missing:
            lines.append(f"- `{topic}`")

    return "\n".join(lines) + "\n"


def build_jsonl_chunks(summary: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = summary.get("diagnostics", {})
    chunks: list[dict[str, Any]] = [
        {
            "type": "overview",
            "source_file": summary.get("source_file"),
            "sha256": summary.get("sha256"),
            "duration_seconds": summary.get("duration_seconds"),
            "num_available_topics": summary.get("num_available_topics"),
        },
        {
            "type": "diagnostics",
            "diagnostics": diagnostics,
        },
        {
            "type": "logged_output",
            "messages": summary.get("logged_output_preview", []),
        },
        {
            "type": "parameters",
            "parameter_snapshot": diagnostics.get("parameter_snapshot", {}),
        },
    ]
    for topic in summary.get("selected_topics", []):
        chunks.append({
            "type": "topic_summary",
            "topic": topic.get("name"),
            "instance": topic.get("instance"),
            "csv_file": topic.get("csv_file"),
            "rows": topic.get("rows"),
            "estimated_rate_hz": topic.get("estimated_rate_hz"),
            "stats": topic.get("stats", []),
            "sample": topic.get("sample", []),
            "error": topic.get("error", ""),
        })
    return chunks
