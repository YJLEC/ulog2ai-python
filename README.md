# QGC/PX4 ULog AI Export Tool

This tool converts one PX4/QGroundControl `.ulg` file into files that are easy to inspect with ChatGPT, local LLMs, Excel, or Python.

It does not require MATLAB. It uses Python and `pyulog`.

## Install with Conda

Open PowerShell in this folder:

```powershell
cd F:\workspace\matlab\ulog_ai_tool
conda env create -f environment.yml
conda activate ulog-ai
```

If the environment already exists, update it:

```powershell
conda activate ulog-ai
python -m pip install -r requirements.txt
```

## Usage

Default flow-focused export:

```powershell
conda activate ulog-ai
python parse_ulog.py D:\QGroundControl\log\log_52_UnknownDate.ulg
```

Choose an output folder:

```powershell
python parse_ulog.py D:\QGroundControl\log\log_52_UnknownDate.ulg --out F:\workspace\matlab\log_52_python_export
```

Choose a preset:

```powershell
python parse_ulog.py D:\QGroundControl\log\log_52_UnknownDate.ulg --preset basic
python parse_ulog.py D:\QGroundControl\log\log_52_UnknownDate.ulg --preset flow
python parse_ulog.py D:\QGroundControl\log\log_52_UnknownDate.ulg --preset full
```

## Output

The default output folder is `<ulg filename>_ai_export`.

```text
ulog_ai_packet.md       ChatGPT-friendly report and upload guide
ulog_ai_summary.json    Machine-readable summary and diagnostics
ulog_ai_chunks.jsonl    Chunked records for local/private LLM workflows
available_topics.csv    All topics and instances in the log
parameters.csv          Initial PX4 parameter snapshot
logged_output.csv       PX4 logger/commander/warning messages
dropout_intervals.csv   ULog dropout records
topics_csv/             One CSV per exported topic instance
```

## Presets

`flow` is the default. It exports general flight state plus optical-flow/range-finder/EKF topics:

- `vehicle_status`, `manual_control_setpoint`
- `vehicle_attitude`, `vehicle_attitude_setpoint`, `actuator_outputs`
- `vehicle_local_position`, `vehicle_local_position_setpoint`
- `vehicle_optical_flow`, `sensor_optical_flow`, `distance_sensor`
- `estimator_status`, `estimator_status_flags`, `estimator_aid_src_optical_flow`, `estimator_optical_flow_vel`, `estimator_innovations`, `estimator_innovation_test_ratios`
- `battery_status`

`basic` exports a smaller general set. `full` exports every topic present in the log.

## Common Checks

The Markdown and JSON summary highlight common optical-flow position-hold issues:

- `vehicle_status.nav_state` stayed `1`: likely Altitude mode, not Position mode.
- `estimator_status_flags.cs_opt_flow` stayed `0`: EKF did not report optical-flow fusion.
- `estimator_aid_src_optical_flow.fused` stayed `0`: optical-flow observations were not fused.
- `vehicle_local_position_setpoint` horizontal setpoints are all NaN: horizontal position control was not active.
- `distance_sensor.current_distance` and `vehicle_optical_flow.quality` statistics help verify range finder and flow quality.

## Notes

- The tool processes one `.ulg` file at a time.
- If the file does not start with the ULog magic bytes, the tool stops with an invalid-file message.
- Large topic CSVs are downsampled to 20000 rows by default. The summary records whether a CSV was downsampled.
