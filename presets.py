"""Topic presets for the ULog AI export tool."""

BASIC_TOPICS = [
    "vehicle_status",
    "manual_control_setpoint",
    "vehicle_attitude",
    "vehicle_attitude_setpoint",
    "vehicle_local_position",
    "vehicle_local_position_setpoint",
    "estimator_status",
    "estimator_status_flags",
    "battery_status",
]

FLOW_TOPICS = [
    "vehicle_status",
    "manual_control_setpoint",
    "vehicle_attitude",
    "vehicle_attitude_setpoint",
    "actuator_outputs",
    "vehicle_local_position",
    "vehicle_local_position_setpoint",
    "vehicle_optical_flow",
    "sensor_optical_flow",
    "distance_sensor",
    "estimator_status",
    "estimator_status_flags",
    "estimator_aid_src_optical_flow",
    "estimator_optical_flow_vel",
    "estimator_innovations",
    "estimator_innovation_test_ratios",
    "battery_status",
]

PRESETS = {
    "basic": BASIC_TOPICS,
    "flow": FLOW_TOPICS,
}


def get_preset(name: str, available_topics: list[str] | None = None) -> list[str]:
    """Return a topic list for a preset name.

    The "full" preset is resolved from available topics because it means every
    topic present in the input log.
    """
    key = name.lower()
    if key == "full":
        if available_topics is None:
            raise ValueError("available_topics is required for the full preset")
        return list(dict.fromkeys(available_topics))
    if key not in PRESETS:
        valid = ", ".join(sorted([*PRESETS.keys(), "full"]))
        raise ValueError(f"Unknown preset '{name}'. Valid presets: {valid}")
    return list(PRESETS[key])
