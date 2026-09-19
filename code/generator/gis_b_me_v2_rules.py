# -*- coding: utf-8 -*-
"""Frozen business-mix and service-availability rules for GIS-B-ME v2.

This module intentionally does not modify the legacy TW0/TW50/TW75 generator.
The v2 candidate treats building type as a frozen city-level attribute and
applies the corresponding hard service windows to every PM task.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


CYCLE_DAYS = 15
DAY1_WEEKDAY = 1  # Monday
SHIFT_MIN = 480
SERVICE_MIN = 30
FIXED_SPEED_KMPH = 15.0

BUILDING_TYPE_RATIOS = {
    "RES": 0.74,
    "OFF": 0.12,
    "COM": 0.08,
    "SCH": 0.06,
}

PILOT_CANDIDATE_POOL_BY_SCALE = {
    100: 5,
    500: 10,
    1000: 15,
}


def weekday_of_day(day: int, day1_weekday: int = DAY1_WEEKDAY) -> int:
    return ((int(day1_weekday) - 1 + int(day) - 1) % 7) + 1


def workdays_and_weekends(
    cycle_days: int = CYCLE_DAYS,
    day1_weekday: int = DAY1_WEEKDAY,
) -> tuple[list[int], list[int]]:
    workdays: list[int] = []
    weekends: list[int] = []
    for day in range(1, int(cycle_days) + 1):
        (workdays if weekday_of_day(day, day1_weekday) <= 5 else weekends).append(day)
    return workdays, weekends


def windows_for_type(
    building_type: str,
    cycle_days: int = CYCLE_DAYS,
    day1_weekday: int = DAY1_WEEKDAY,
) -> list[tuple[int, int, int, str]]:
    """Return (day, ready, due, label); due is latest completion time."""
    btype = str(building_type).upper()
    workdays, weekends = workdays_and_weekends(cycle_days, day1_weekday)
    if btype == "RES":
        return [(d, 120, 360, "RES_WEEKDAY_MIDDAY") for d in workdays]
    if btype == "OFF":
        return [
            *[(d, 120, 360, "OFF_WORKDAY_MIDDAY") for d in workdays],
            *[(d, 0, 480, "OFF_WEEKEND_FULLDAY") for d in weekends],
        ]
    if btype == "COM":
        return [(d, 0, 480, "COM_WORKDAY_FULLDAY") for d in workdays]
    if btype == "SCH":
        return [(d, 0, 480, "SCH_WEEKEND_FULLDAY") for d in weekends]
    raise ValueError(f"Unsupported building type: {building_type}")


def build_task_windows_v2(
    tasks_df: pd.DataFrame,
    cycle_days: int = CYCLE_DAYS,
    day1_weekday: int = DAY1_WEEKDAY,
    service_min: float = SERVICE_MIN,
    tw_policy: str = "hard",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    window_rows: list[dict] = []
    task_rows: list[dict] = []
    for _, task in tasks_df.iterrows():
        task_id = str(task["task_id"])
        btype = str(task["building_type"]).upper()
        daily_windows = sorted(
            windows_for_type(btype, cycle_days, day1_weekday),
            key=lambda item: item[0],
        )
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
                "is_time_restricted": 1,
                "time_rule_mode": "fixed_by_building_type_v2",
                "availability_class": {
                    "RES": "weekday_only_midday",
                    "OFF": "mixed_weekday_midday_weekend_fullday",
                    "COM": "weekday_only_fullday",
                    "SCH": "weekend_only_fullday",
                }[btype],
                "window_count": len(daily_windows),
                "primary_day": int(first[0]),
                "primary_ready_time": int(first[1]),
                "primary_due_time": int(first[2]),
                "tw_policy": str(tw_policy),
            }
        )
        task_rows.append(row)
    return pd.DataFrame(task_rows), pd.DataFrame(window_rows)


def largest_remainder_counts(total: int, ratios: dict[str, float] | None = None) -> dict[str, int]:
    ratios = dict(ratios or BUILDING_TYPE_RATIOS)
    raw = {key: float(total) * value for key, value in ratios.items()}
    counts = {key: int(math.floor(value)) for key, value in raw.items()}
    remaining = int(total) - sum(counts.values())
    order = sorted(ratios, key=lambda key: (raw[key] - counts[key], ratios[key], key), reverse=True)
    for key in order[:remaining]:
        counts[key] += 1
    return counts


def spatially_stratified_type_assignment(
    buildings: pd.DataFrame,
    seed: int,
    x_col: str = "projected_x",
    y_col: str = "projected_y",
    grid_size: int = 10,
) -> pd.Series:
    """Assign exact global ratios while interleaving types across spatial strata."""
    if buildings.empty:
        raise ValueError("Cannot assign types to an empty building pool.")
    frame = buildings[[x_col, y_col]].copy()
    x = frame[x_col].to_numpy(float)
    y = frame[y_col].to_numpy(float)
    x_span = max(float(x.max() - x.min()), 1.0)
    y_span = max(float(y.max() - y.min()), 1.0)
    gx = np.minimum(((x - x.min()) / x_span * grid_size).astype(int), grid_size - 1)
    gy = np.minimum(((y - y.min()) / y_span * grid_size).astype(int), grid_size - 1)
    frame["stratum"] = gy * grid_size + gx
    rng = np.random.default_rng(int(seed))

    interleaved: list[int] = []
    buckets: dict[int, list[int]] = {}
    for stratum, group in frame.groupby("stratum"):
        idx = group.index.to_numpy(int)
        rng.shuffle(idx)
        buckets[int(stratum)] = idx.tolist()
    while any(buckets.values()):
        for stratum in sorted(buckets):
            if buckets[stratum]:
                interleaved.append(buckets[stratum].pop())

    counts = largest_remainder_counts(len(buildings))
    labels: list[str] = []
    remaining = dict(counts)
    type_order = list(BUILDING_TYPE_RATIOS)
    cursor = int(seed) % len(type_order)
    while sum(remaining.values()):
        key = type_order[cursor % len(type_order)]
        cursor += 1
        if remaining[key] <= 0:
            continue
        labels.append(key)
        remaining[key] -= 1

    result = pd.Series(index=buildings.index, dtype="object")
    for index, label in zip(interleaved, labels):
        result.loc[index] = label
    if result.isna().any():
        raise RuntimeError("Spatially stratified type assignment left unassigned buildings.")
    return result


def service_availability_summary(
    type_counts: dict[str, int] | pd.Series,
    service_min: float = SERVICE_MIN,
) -> pd.DataFrame:
    rows: list[dict] = []
    baseline_minutes = CYCLE_DAYS * SHIFT_MIN
    for btype in BUILDING_TYPE_RATIOS:
        windows = windows_for_type(btype)
        total_window_minutes = sum(due - ready for _, ready, due, _ in windows)
        feasible_start_minutes = sum(max(0.0, due - ready - service_min) for _, ready, due, _ in windows)
        n_tasks = int(type_counts.get(btype, 0))
        rows.append(
            {
                "building_type": btype,
                "n_tasks": n_tasks,
                "service_days": len(windows),
                "available_window_minutes": total_window_minutes,
                "time_flexibility": total_window_minutes / baseline_minutes,
                "feasible_start_minutes": feasible_start_minutes,
                "service_only_capacity_per_technician": int(total_window_minutes // service_min),
                "service_only_lb": math.ceil(n_tasks * service_min / max(total_window_minutes, 1)),
            }
        )
    return pd.DataFrame(rows)


def theoretical_pressure_by_scale(scales: Iterable[int] = (100, 500, 1000)) -> pd.DataFrame:
    rows: list[dict] = []
    for scale in scales:
        counts = largest_remainder_counts(int(scale))
        availability = service_availability_summary(counts)
        lb_all = math.ceil(int(scale) * SERVICE_MIN / (CYCLE_DAYS * SHIFT_MIN))
        lb_type = int(availability["service_only_lb"].max())
        weighted_flexibility = sum(
            BUILDING_TYPE_RATIOS[t] * service_availability_summary({t: 0}).set_index("building_type").loc[t, "time_flexibility"]
            for t in BUILDING_TYPE_RATIOS
        )
        rows.append(
            {
                "scale": int(scale),
                **{f"n_{key.lower()}": value for key, value in counts.items()},
                "service_only_lb_all": lb_all,
                "service_only_lb_by_type": lb_type,
                "res_service_only_lb": int(availability.set_index("building_type").loc["RES", "service_only_lb"]),
                "sch_service_only_lb": int(availability.set_index("building_type").loc["SCH", "service_only_lb"]),
                "pilot_candidate_pool": PILOT_CANDIDATE_POOL_BY_SCALE[int(scale)],
                "weighted_time_flexibility": weighted_flexibility,
            }
        )
    return pd.DataFrame(rows)


def road_time_from_distance(distance_m: pd.Series | np.ndarray | float, speed_kmph: float = FIXED_SPEED_KMPH):
    return np.asarray(distance_m, dtype=float) / 1000.0 / float(speed_kmph) * 3600.0
