# -*- coding: utf-8 -*-
"""Fixed business service-window rules for GIS-B-ME v3.

The spatial benchmark remains the Beijing/Chongqing/Shanghai GIS-B-ME design.
There is no time-window scenario dimension.  Every task inherits one frozen
rule from its assigned building type.  Residential tasks retain the full
15-day window; non-residential types use their business-specific availability.
"""

from __future__ import annotations

import pandas as pd

from gis_b_me_v2_rules import (
    BUILDING_TYPE_RATIOS,
    CYCLE_DAYS,
    DAY1_WEEKDAY,
    FIXED_SPEED_KMPH,
    PILOT_CANDIDATE_POOL_BY_SCALE,
    SERVICE_MIN,
    SHIFT_MIN,
    road_time_from_distance,
    weekday_of_day,
    workdays_and_weekends,
)


TIME_RULE_MODE = "fixed_business_windows_v3"
TW_SCENARIO_LABEL = "NO_TW_DIMENSION"


def windows_for_type(
    building_type: str,
    cycle_days: int = CYCLE_DAYS,
    day1_weekday: int = DAY1_WEEKDAY,
) -> list[tuple[int, int, int, str]]:
    """Return (day, ready, due, label); due is latest completion time."""
    btype = str(building_type).upper()
    workdays, weekends = workdays_and_weekends(cycle_days, day1_weekday)
    if btype == "RES":
        return [(d, 0, 480, "BASE_FULL_CYCLE") for d in range(1, int(cycle_days) + 1)]
    if btype == "OFF":
        return [(d, 120, 360, "OFF_WORKDAY_MIDDAY") for d in workdays]
    if btype == "COM":
        return [(d, 0, 480, "COM_WORKDAY_FULLDAY") for d in workdays]
    if btype == "SCH":
        return [(d, 0, 480, "SCH_WEEKEND_FULLDAY") for d in weekends]
    raise ValueError(f"Unsupported building type: {building_type}")


def build_task_windows_tw100(
    tasks_df: pd.DataFrame,
    cycle_days: int = CYCLE_DAYS,
    day1_weekday: int = DAY1_WEEKDAY,
    service_min: float = SERVICE_MIN,
    tw_policy: str = "hard",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    window_rows: list[dict] = []
    task_rows: list[dict] = []
    availability = {
        "RES": "full_cycle_fullday",
        "OFF": "workday_only_midday",
        "COM": "workday_only_fullday",
        "SCH": "weekend_only_fullday",
    }
    for _, task in tasks_df.iterrows():
        task_id = str(task["task_id"])
        btype = str(task["building_type"]).upper()
        daily_windows = windows_for_type(btype, cycle_days, day1_weekday)
        for index, (day, ready, due, label) in enumerate(daily_windows, start=1):
            window_rows.append(
                {
                    "task_id": task_id,
                    "window_id": index,
                    "day": int(day),
                    "ready_time_min": int(ready),
                    "due_time_min": int(due),
                    "latest_start_time_min": float(due) - float(service_min),
                    "window_label": label,
                    "window_type": str(tw_policy),
                    "penalty_weight": 0.0,
                }
            )
        first = daily_windows[0]
        row = dict(task)
        row.update(
            {
                "is_time_restricted": int(btype != "RES"),
                "time_rule_mode": TIME_RULE_MODE,
                "availability_class": availability[btype],
                "window_count": len(daily_windows),
                "primary_day": int(first[0]),
                "primary_ready_time": int(first[1]),
                "primary_due_time": int(first[2]),
                "tw_policy": str(tw_policy),
            }
        )
        task_rows.append(row)
    return pd.DataFrame(task_rows), pd.DataFrame(window_rows)
