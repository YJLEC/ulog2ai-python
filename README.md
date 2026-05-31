# QGC/PX4 ULog AI 解析工具

这个工具用于把 PX4/QGroundControl 的 `.ulg` 日志转换成更适合 AI、Excel 和 Python 阅读的格式。

工具不依赖 MATLAB，底层使用 Python 和 `pyulog`。

## 安装

先克隆仓库并进入项目目录：

```powershell
git clone https://github.com/YJLEC/ulog2ai-python.git
cd ulog2ai-python
```

创建并激活 conda 环境：

```powershell
conda env create -f environment.yml
conda activate ulog-ai
```

如果 `ulog-ai` 环境已经存在，可以直接更新依赖：

```powershell
conda activate ulog-ai
python -m pip install -r requirements.txt
```

## 使用

默认使用 `flow` 预设，适合通用飞行状态和光流定位问题分析：

```powershell
python parse_ulog.py C:\path\to\flight.ulg
```

指定输出目录：

```powershell
python parse_ulog.py C:\path\to\flight.ulg --out C:\path\to\flight_ai_export
```

选择预设：

```powershell
python parse_ulog.py C:\path\to\flight.ulg --preset basic
python parse_ulog.py C:\path\to\flight.ulg --preset flow
python parse_ulog.py C:\path\to\flight.ulg --preset full
```

## 输出内容

默认输出目录为 `<日志文件名>_ai_export`。

```text
ulog_ai_packet.md       适合上传给 ChatGPT 的报告和文件索引
ulog_ai_summary.json    结构化摘要和基础诊断结果
ulog_ai_chunks.jsonl    面向本地或私有大模型的分块数据
available_topics.csv    日志中所有 topic 和 instance 列表
parameters.csv          PX4 参数快照
logged_output.csv       PX4 commander/logger/warning 等消息
dropout_intervals.csv   ULog 记录丢包区间
topics_csv/             每个导出 topic instance 一个 CSV 文件
```

## 预设

`flow` 是默认预设，包含通用飞行状态、光流、测距和 EKF 相关 topic：

- `vehicle_status`, `manual_control_setpoint`
- `vehicle_attitude`, `vehicle_attitude_setpoint`, `actuator_outputs`
- `vehicle_local_position`, `vehicle_local_position_setpoint`
- `vehicle_optical_flow`, `sensor_optical_flow`, `distance_sensor`
- `estimator_status`, `estimator_status_flags`, `estimator_aid_src_optical_flow`, `estimator_optical_flow_vel`, `estimator_innovations`, `estimator_innovation_test_ratios`
- `battery_status`

其他预设：

- `basic`：较小的通用分析集合
- `flow`：默认，通用 + 光流定位分析集合
- `full`：导出日志中存在的所有 topic

## 常见诊断项

生成的 Markdown 和 JSON 会标出一些常见问题：

- `vehicle_status.nav_state` 一直为 `1`：通常表示实际处于 Altitude/定高模式，不是 Position/定点模式。
- `estimator_status_flags.cs_opt_flow` 一直为 `0`：EKF 状态中没有进入光流融合。
- `estimator_aid_src_optical_flow.fused` 一直为 `0`：光流观测没有被 EKF 融合。
- `vehicle_local_position_setpoint` 的 `x/y/vx/vy` 全是 NaN：水平位置控制 setpoint 没有生效。
- `distance_sensor.current_distance` 和 `vehicle_optical_flow.quality` 可用于检查测距和光流质量。

## 注意事项

- 当前版本一次只处理一个 `.ulg` 文件。
- 如果文件不是有效 ULog，工具会提示文件头无效并停止。
- 大型 topic 默认最多导出 20000 行 CSV；如发生下采样，会在摘要中标记。
