# -*- coding: utf-8 -*-
"""
EMD Benchmark Generator v3

Elevator Maintenance Dispatch (EMD) benchmark instance generator.

Current base setting:
- Single service station at the map center.
- 15-day preventive maintenance cycle.
- Daily work limit: 480 minutes; overtime is not allowed.
- One preventive maintenance task per elevator.
- Service time is fixed to 30 minutes for all tasks.
- Manhattan distance is used to approximate urban grid travel.
- Residential (RES) tasks always use the full-cycle window.
- TW scenarios only control the proportion of non-RES clusters that activate
  their special building-type windows.
- Technician count is represented as a candidate pool; the actual number of
  used technicians is intended to be optimized by a downstream solver.

Standard scenario grid:
- n_elevators: 100, 500, 1000
- cluster_pattern: CU, CH, CZ
- tw_scenario: TW0, TW50, TW75
This gives 27 scenario combinations for one random seed.
"""

import argparse
import math
import os
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULTS = {
    "instance_prefix": "EMD",
    "map_size": 10.0,
    "station_id": "S01",
    "cycle_days": 15,
    "day1_weekday": 1,  # 1=Monday, ..., 7=Sunday
    "shift_start_min": 0,
    "shift_end_min": 480,
    "regular_work_min": 480,
    "max_work_min": 480,
    "allow_overtime": False,
    "service_min": 30.0,
    "speed_kmph": 15.0,
    "distance_metric": "manhattan",
    "cluster_size_min": 4,
    "cluster_size_max": 10,
    "cluster_size_target": 7,
    "cluster_radius_min": 0.08,
    "cluster_radius_max": 0.25,
    "zonal_zone_count": 3,
    "zonal_zone_radius": 1.8,
    "building_type_ratios": "RES:0.55,OFF:0.20,COM:0.15,SCH:0.10",
    "tw_policy": "hard",
    "technician_pool_factor": 2.0,
    "technician_pool_buffer": 2,
    "seed": 12,
}

BUILDING_TYPES = ["RES", "OFF", "COM", "SCH"]
TW_SCENARIO_RATIOS = {
    "TW0": 0.00,
    "TW50": 0.50,
    "TW75": 0.75,
    "TW100": 1.00,
}

BUILDING_TYPE_NAMES = {
    "RES": "Residential",
    "OFF": "Office",
    "COM": "Commercial",
    "SCH": "School",
}


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def parse_ratio_string(text: str, expected_keys: Optional[Sequence[str]] = None) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not text:
        raise ValueError("ratio string cannot be empty")
    for part in text.split(","):
        if not part.strip():
            continue
        key, value = part.split(":", 1)
        key = key.strip().upper()
        out[key] = float(value)
    if expected_keys is not None:
        missing = [k for k in expected_keys if k not in out]
        if missing:
            raise ValueError(f"missing ratio keys: {missing}")
    total = sum(out.values())
    if total <= 0:
        raise ValueError("ratio sum must be positive")
    return {k: v / total for k, v in out.items()}


def weekday_of_day(day: int, day1_weekday: int = 1) -> int:
    return ((int(day1_weekday) - 1 + int(day) - 1) % 7) + 1


def get_workdays_and_weekends(cycle_days: int, day1_weekday: int = 1) -> Tuple[List[int], List[int]]:
    workdays: List[int] = []
    weekends: List[int] = []
    for day in range(1, int(cycle_days) + 1):
        wd = weekday_of_day(day, day1_weekday)
        if wd <= 5:
            workdays.append(day)
        else:
            weekends.append(day)
    return workdays, weekends


def sample_point_in_disk(rng: np.random.Generator, cx: float, cy: float, radius: float) -> Tuple[float, float]:
    u = float(rng.random())
    v = float(rng.random())
    r = radius * math.sqrt(u)
    theta = 2.0 * math.pi * v
    return cx + r * math.cos(theta), cy + r * math.sin(theta)


def manhattan_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return abs(float(x1) - float(x2)) + abs(float(y1) - float(y2))


def compute_distance_time(x1: float, y1: float, x2: float, y2: float, speed_kmph: float) -> Tuple[float, float]:
    dist_km = manhattan_distance(x1, y1, x2, y2)
    travel_time_min = dist_km / float(speed_kmph) * 60.0 if speed_kmph > 0 else float("inf")
    return dist_km, travel_time_min


def auto_cluster_count(n_elevators: int, cluster_size_target: int) -> int:
    return max(1, int(math.ceil(int(n_elevators) / float(cluster_size_target))))


def bounded_partition(
    rng: np.random.Generator,
    total: int,
    k: int,
    lo: int,
    hi: int,
    mode: str = "uniform",
) -> List[int]:
    """Partition total into k integer parts within [lo, hi]."""
    total = int(total)
    k = int(k)
    lo = int(lo)
    hi = int(hi)
    if k <= 0:
        return []
    if total < k * lo or total > k * hi:
        raise ValueError(f"cannot partition total={total} into k={k} parts with bounds [{lo}, {hi}]")

    sizes = np.full(k, lo, dtype=int)
    remaining = total - k * lo
    capacity = np.full(k, hi - lo, dtype=int)

    if mode == "heterogeneous":
        weights = rng.lognormal(mean=0.0, sigma=1.0, size=k)
    else:
        weights = np.ones(k)
    weights = weights / weights.sum()

    # First allocation by multinomial, then repair capacity violations.
    adds = rng.multinomial(remaining, weights)
    sizes += adds

    while np.any(sizes > hi):
        over_idx = np.where(sizes > hi)[0]
        for idx in over_idx:
            surplus = int(sizes[idx] - hi)
            sizes[idx] = hi
            while surplus > 0:
                candidates = np.where(sizes < hi)[0]
                if len(candidates) == 0:
                    raise RuntimeError("bounded partition repair failed")
                j = int(rng.choice(candidates))
                sizes[j] += 1
                surplus -= 1

    diff = total - int(sizes.sum())
    while diff != 0:
        if diff > 0:
            candidates = np.where(sizes < hi)[0]
            if len(candidates) == 0:
                raise RuntimeError("bounded partition add failed")
            j = int(rng.choice(candidates))
            sizes[j] += 1
            diff -= 1
        else:
            candidates = np.where(sizes > lo)[0]
            if len(candidates) == 0:
                raise RuntimeError("bounded partition subtract failed")
            j = int(rng.choice(candidates))
            sizes[j] -= 1
            diff += 1

    return [int(x) for x in sizes.tolist()]


def assign_building_types(
    rng: np.random.Generator,
    n_clusters: int,
    ratio_text: str,
) -> List[str]:
    ratios = parse_ratio_string(ratio_text, expected_keys=BUILDING_TYPES)
    labels = list(ratios.keys())
    probs = np.array([ratios[k] for k in labels], dtype=float)
    probs = probs / probs.sum()
    types = rng.choice(labels, size=int(n_clusters), replace=True, p=probs).tolist()
    return [str(t) for t in types]


def choose_restricted_non_res_clusters(
    rng: np.random.Generator,
    building_types: Sequence[str],
    tw_scenario: str,
) -> List[int]:
    scenario = str(tw_scenario).upper()
    if scenario not in TW_SCENARIO_RATIOS:
        raise ValueError(f"unknown tw_scenario: {tw_scenario}")
    ratio = TW_SCENARIO_RATIOS[scenario]
    restricted = [0] * len(building_types)
    non_res_indices = [i for i, t in enumerate(building_types) if str(t).upper() != "RES"]
    if not non_res_indices or ratio <= 0:
        return restricted
    n_pick = int(round(len(non_res_indices) * ratio))
    n_pick = max(0, min(len(non_res_indices), n_pick))
    selected = rng.choice(non_res_indices, size=n_pick, replace=False).tolist()
    for idx in selected:
        restricted[int(idx)] = 1
    return restricted


def generate_cluster_centers(
    rng: np.random.Generator,
    n_clusters: int,
    map_size: float,
    pattern: str,
    zone_count: int,
    zone_radius: float,
) -> Tuple[List[Tuple[float, float]], List[int]]:
    pattern = str(pattern).upper()
    n_clusters = int(n_clusters)
    W = float(map_size)
    margin = 0.4
    centers: List[Tuple[float, float]] = []
    zone_ids: List[int] = []

    if pattern in {"CU", "CH"}:
        # Stratified jittered grid for stable spatial coverage.
        cols = int(math.ceil(math.sqrt(n_clusters)))
        rows = int(math.ceil(n_clusters / cols))
        cell_w = W / cols
        cell_h = W / rows
        slots = [(r, c) for r in range(rows) for c in range(cols)]
        rng.shuffle(slots)
        for idx, (r, c) in enumerate(slots[:n_clusters]):
            x0, x1 = c * cell_w, (c + 1) * cell_w
            y0, y1 = r * cell_h, (r + 1) * cell_h
            x = float(rng.uniform(x0 + 0.15 * cell_w, x1 - 0.15 * cell_w))
            y = float(rng.uniform(y0 + 0.15 * cell_h, y1 - 0.15 * cell_h))
            centers.append((clamp(x, margin, W - margin), clamp(y, margin, W - margin)))
            zone_ids.append(0)
        return centers, zone_ids

    if pattern == "CZ":
        zc = max(1, int(zone_count))
        zone_centers: List[Tuple[float, float]] = []
        for _ in range(zc):
            zx = float(rng.uniform(1.5, W - 1.5)) if W > 3 else float(W / 2)
            zy = float(rng.uniform(1.5, W - 1.5)) if W > 3 else float(W / 2)
            zone_centers.append((zx, zy))
        probs = np.ones(zc) / zc
        for _ in range(n_clusters):
            zid = int(rng.choice(np.arange(zc), p=probs))
            zx, zy = zone_centers[zid]
            x, y = sample_point_in_disk(rng, zx, zy, float(zone_radius))
            centers.append((clamp(x, margin, W - margin), clamp(y, margin, W - margin)))
            zone_ids.append(zid + 1)
        return centers, zone_ids

    raise ValueError("cluster_pattern must be CU, CH, or CZ")


def generate_clusters(
    rng: np.random.Generator,
    n_elevators: int,
    n_clusters: Optional[int],
    cluster_pattern: str,
    tw_scenario: str,
    map_size: float,
    building_type_ratios: str,
    cluster_size_min: int,
    cluster_size_max: int,
    cluster_size_target: int,
    cluster_radius_min: float,
    cluster_radius_max: float,
    zonal_zone_count: int,
    zonal_zone_radius: float,
    service_min: float,
) -> pd.DataFrame:
    if n_clusters is None or int(n_clusters) <= 0:
        n_clusters = auto_cluster_count(n_elevators, cluster_size_target)
    n_clusters = int(n_clusters)
    # Ensure feasibility of 4-10 bound by adjusting n_clusters if user passes an infeasible value.
    min_k = int(math.ceil(int(n_elevators) / float(cluster_size_max)))
    max_k = int(math.floor(int(n_elevators) / float(cluster_size_min)))
    if n_clusters < min_k:
        n_clusters = min_k
    if n_clusters > max_k:
        n_clusters = max_k

    size_mode = "heterogeneous" if str(cluster_pattern).upper() == "CH" else "uniform"
    sizes = bounded_partition(
        rng=rng,
        total=int(n_elevators),
        k=n_clusters,
        lo=int(cluster_size_min),
        hi=int(cluster_size_max),
        mode=size_mode,
    )
    centers, zone_ids = generate_cluster_centers(
        rng=rng,
        n_clusters=n_clusters,
        map_size=float(map_size),
        pattern=str(cluster_pattern).upper(),
        zone_count=int(zonal_zone_count),
        zone_radius=float(zonal_zone_radius),
    )
    btypes = assign_building_types(rng, n_clusters, building_type_ratios)
    restricted_flags = choose_restricted_non_res_clusters(rng, btypes, tw_scenario)

    rows: List[dict] = []
    for idx in range(n_clusters):
        radius = float(rng.uniform(float(cluster_radius_min), float(cluster_radius_max)))
        rows.append(
            {
                "cluster_id": f"C{idx + 1:04d}",
                "cluster_pattern": str(cluster_pattern).upper(),
                "zone_id": int(zone_ids[idx]),
                "building_type": str(btypes[idx]),
                "building_type_name": BUILDING_TYPE_NAMES.get(str(btypes[idx]), str(btypes[idx])),
                "center_x_km": float(centers[idx][0]),
                "center_y_km": float(centers[idx][1]),
                "cluster_radius_km": float(radius),
                "n_elevators": int(sizes[idx]),
                "base_service_min": float(service_min),
                "is_time_restricted": int(restricted_flags[idx]),
                "tw_scenario": str(tw_scenario).upper(),
            }
        )
    return pd.DataFrame(rows)


def generate_nodes_and_tasks(
    rng: np.random.Generator,
    clusters_df: pd.DataFrame,
    station_id: str,
    map_size: float,
    service_min: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    W = float(map_size)
    station_x = W / 2.0
    station_y = W / 2.0
    nodes: List[dict] = [
        {
            "node_id": station_id,
            "node_type": "STATION",
            "x_km": float(station_x),
            "y_km": float(station_y),
            "cluster_id": "NA",
            "building_type": "NA",
            "station_id": station_id,
        }
    ]
    tasks: List[dict] = []
    elevator_idx = 0
    task_idx = 0
    for _, c in clusters_df.iterrows():
        cid = str(c["cluster_id"])
        btype = str(c["building_type"])
        cx = float(c["center_x_km"])
        cy = float(c["center_y_km"])
        radius = float(c["cluster_radius_km"])
        n = int(c["n_elevators"])
        for _ in range(n):
            elevator_idx += 1
            task_idx += 1
            x, y = sample_point_in_disk(rng, cx, cy, radius)
            x = clamp(x, 0.0, W)
            y = clamp(y, 0.0, W)
            node_id = f"E{elevator_idx:05d}"
            task_id = f"PM{task_idx:05d}"
            nodes.append(
                {
                    "node_id": node_id,
                    "node_type": "ELEVATOR",
                    "x_km": float(x),
                    "y_km": float(y),
                    "cluster_id": cid,
                    "building_type": btype,
                    "station_id": station_id,
                }
            )
            tasks.append(
                {
                    "task_id": task_id,
                    "task_type": "PM",
                    "elevator_id": node_id,
                    "node_id": node_id,
                    "cluster_id": cid,
                    "building_type": btype,
                    "station_id": station_id,
                    "x_km": float(x),
                    "y_km": float(y),
                    "service_min": float(service_min),
                    "priority": 3,
                    "is_time_restricted": int(c["is_time_restricted"]),
                }
            )
    return pd.DataFrame(nodes), pd.DataFrame(tasks)


def windows_for_building_type(
    building_type: str,
    is_restricted: int,
    cycle_days: int,
    day1_weekday: int,
) -> List[Tuple[int, int, int, str]]:
    """Return daily windows as (day, ready, due, label). due is latest completion time."""
    btype = str(building_type).upper()
    restricted = int(is_restricted) == 1
    workdays, weekends = get_workdays_and_weekends(cycle_days, day1_weekday)

    # RES is always a base type. Non-restricted non-RES tasks also use base full-cycle windows.
    if btype == "RES" or not restricted:
        return [(day, 0, 480, "BASE_FULL_CYCLE") for day in range(1, int(cycle_days) + 1)]

    if btype == "OFF":
        return [(day, 120, 360, "OFF_WORKDAY_MIDDAY") for day in workdays]
    if btype == "COM":
        return [(day, 0, 480, "COM_WORKDAY_FULLDAY") for day in workdays]
    if btype == "SCH":
        return [(day, 0, 480, "SCH_WEEKEND_FULLDAY") for day in weekends]

    return [(day, 0, 480, "BASE_FULL_CYCLE") for day in range(1, int(cycle_days) + 1)]


def build_task_windows(
    tasks_df: pd.DataFrame,
    cycle_days: int,
    day1_weekday: int,
    service_min: float,
    tw_policy: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    windows: List[dict] = []
    task_rows: List[dict] = []
    for _, r in tasks_df.iterrows():
        task_id = str(r["task_id"])
        btype = str(r["building_type"])
        restricted = int(r["is_time_restricted"])
        daily_windows = windows_for_building_type(
            building_type=btype,
            is_restricted=restricted,
            cycle_days=int(cycle_days),
            day1_weekday=int(day1_weekday),
        )
        for widx, (day, ready, due, label) in enumerate(daily_windows, start=1):
            windows.append(
                {
                    "task_id": task_id,
                    "window_id": int(widx),
                    "day": int(day),
                    "ready_time_min": int(ready),
                    "due_time_min": int(due),
                    "latest_start_time_min": int(due - float(service_min)),
                    "window_label": str(label),
                    "window_type": str(tw_policy),
                    "penalty_weight": 0.0,
                }
            )
        first = daily_windows[0]
        row = dict(r)
        row.update(
            {
                "window_count": int(len(daily_windows)),
                "primary_day": int(first[0]),
                "primary_ready_time": int(first[1]),
                "primary_due_time": int(first[2]),
                "tw_policy": str(tw_policy),
            }
        )
        task_rows.append(row)
    return pd.DataFrame(task_rows), pd.DataFrame(windows)


def estimate_technician_pool(
    tasks_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    cycle_days: int,
    regular_work_min: int,
    service_min: float,
    technician_pool_factor: float,
    technician_pool_buffer: int,
) -> Tuple[int, Dict[str, float]]:
    total_tasks = int(len(tasks_df))
    total_service = total_tasks * float(service_min)
    lb_all = math.ceil(total_service / (int(cycle_days) * float(regular_work_min))) if total_service > 0 else 1

    counts = tasks_df.groupby(["building_type", "is_time_restricted"]).size().to_dict()
    n_off_restricted = int(counts.get(("OFF", 1), 0))
    n_com_restricted = int(counts.get(("COM", 1), 0))
    n_sch_restricted = int(counts.get(("SCH", 1), 0))

    workdays, weekends = get_workdays_and_weekends(cycle_days, int(DEFAULTS["day1_weekday"]))
    lb_off = math.ceil(n_off_restricted * float(service_min) / (max(1, len(workdays)) * 240.0)) if n_off_restricted else 0
    lb_com = math.ceil(n_com_restricted * float(service_min) / (max(1, len(workdays)) * 480.0)) if n_com_restricted else 0
    lb_sch = math.ceil(n_sch_restricted * float(service_min) / (max(1, len(weekends)) * 480.0)) if n_sch_restricted else 0
    lb = max(1, int(lb_all), int(lb_off), int(lb_com), int(lb_sch))
    pool = int(math.ceil(float(technician_pool_factor) * lb) + int(technician_pool_buffer))
    pool = max(pool, lb + 1)
    stats = {
        "derived_lb_all_tasks": int(lb_all),
        "derived_lb_off_restricted": int(lb_off),
        "derived_lb_com_restricted": int(lb_com),
        "derived_lb_sch_restricted": int(lb_sch),
        "derived_technician_lower_bound": int(lb),
        "derived_technician_candidate_pool": int(pool),
    }
    return pool, stats


def build_technicians(
    n_technicians_max: int,
    station_id: str,
    speed_kmph: float,
    shift_start_min: int,
    shift_end_min: int,
    regular_work_min: int,
    max_work_min: int,
) -> pd.DataFrame:
    rows: List[dict] = []
    for k in range(1, int(n_technicians_max) + 1):
        rows.append(
            {
                "technician_id": f"K{k:03d}",
                "station_id": station_id,
                "speed_kmph": float(speed_kmph),
                "shift_start_min": int(shift_start_min),
                "shift_end_min": int(shift_end_min),
                "regular_work_min": int(regular_work_min),
                "max_work_min": int(max_work_min),
                "skill_group": "PM_GENERAL",
                "candidate_pool": 1,
                "active": 1,
            }
        )
    return pd.DataFrame(rows)


def build_distance_matrix(nodes_df: pd.DataFrame, speed_kmph: float) -> pd.DataFrame:
    rows: List[dict] = []
    nd = nodes_df[["node_id", "x_km", "y_km"]].to_dict("records")
    for a in nd:
        for b in nd:
            dist, tt = compute_distance_time(a["x_km"], a["y_km"], b["x_km"], b["y_km"], speed_kmph)
            rows.append(
                {
                    "from_node": str(a["node_id"]),
                    "to_node": str(b["node_id"]),
                    "distance_km_manhattan": float(dist),
                    "travel_time_min": float(tt),
                }
            )
    return pd.DataFrame(rows)


def validate_instance(
    nodes_df: pd.DataFrame,
    clusters_df: pd.DataFrame,
    technicians_df: pd.DataFrame,
    tasks_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    service_min: float,
) -> pd.DataFrame:
    checks: List[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add("unique_node_id", nodes_df["node_id"].is_unique, "")
    add("unique_task_id", tasks_df["task_id"].is_unique, "")
    add("one_task_per_elevator", int((nodes_df["node_type"] == "ELEVATOR").sum()) == len(tasks_df), "")
    win_counts = windows_df.groupby("task_id").size()
    add("each_task_has_window", set(tasks_df["task_id"]) == set(win_counts.index), "")
    add("ready_before_due", bool((windows_df["ready_time_min"] <= windows_df["due_time_min"]).all()), "")
    add(
        "service_fits_window",
        bool(((windows_df["due_time_min"] - windows_df["ready_time_min"]) >= float(service_min)).all()),
        "due_time is latest completion time",
    )
    add("service_fixed_30", bool((tasks_df["service_min"].round(6) == float(service_min)).all()), "")
    add("single_station", int((nodes_df["node_type"] == "STATION").sum()) == 1, "")
    add("technician_pool_nonempty", len(technicians_df) >= 1, "")
    add("cluster_size_bounds", bool(((clusters_df["n_elevators"] >= 4) & (clusters_df["n_elevators"] <= 10)).all()), "")
    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    checks.append({"check": "overall_status", "passed": status == "PASS", "detail": status})
    return pd.DataFrame(checks)


def build_config(
    params: Dict[str, object],
    clusters_df: pd.DataFrame,
    tasks_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    tech_stats: Dict[str, float],
) -> pd.DataFrame:
    rows: List[dict] = []
    for k in sorted(params.keys()):
        rows.append({"param": k, "value": params[k]})

    n_tasks = int(len(tasks_df))
    total_service = float(tasks_df["service_min"].sum()) if n_tasks else 0.0
    n_non_res_clusters = int((clusters_df["building_type"] != "RES").sum())
    n_restricted_clusters = int(clusters_df["is_time_restricted"].sum())
    n_restricted_tasks = int(tasks_df["is_time_restricted"].sum())
    avg_window_count = float(windows_df.groupby("task_id").size().mean()) if n_tasks else 0.0
    avg_window_width = float((windows_df["due_time_min"] - windows_df["ready_time_min"]).mean()) if len(windows_df) else 0.0

    derived = {
        "derived_total_elevators": n_tasks,
        "derived_total_clusters": int(len(clusters_df)),
        "derived_non_res_clusters": n_non_res_clusters,
        "derived_restricted_non_res_clusters": n_restricted_clusters,
        "derived_restricted_tasks": n_restricted_tasks,
        "derived_total_task_windows": int(len(windows_df)),
        "derived_avg_window_count_per_task": avg_window_count,
        "derived_avg_window_width_min": avg_window_width,
        "derived_total_pm_service_min": total_service,
        "derived_overtime_allowed": False,
        "objective_1": "minimize_used_technicians",
        "objective_2": "minimize_total_travel_time_manhattan",
        "objective_3": "minimize_workload_imbalance",
        "due_time_semantics": "latest_completion_time",
        "tw_scope": "TW scenarios restrict only non-RES clusters",
    }
    derived.update(tech_stats)
    for k, v in derived.items():
        rows.append({"param": k, "value": v})
    return pd.DataFrame(rows)


def build_readme() -> pd.DataFrame:
    rows = [
        {"sheet": "NODES", "description": "Station and elevator nodes with 2D coordinates."},
        {"sheet": "CLUSTERS", "description": "Building clusters, building type labels, cluster size, and TW activation flag."},
        {"sheet": "TECHNICIANS", "description": "Candidate technician pool. Used technician count is an optimization target."},
        {"sheet": "TASKS", "description": "One PM task per elevator. Service time is fixed to 30 minutes."},
        {"sheet": "TASK_WINDOWS", "description": "Daily service windows. due_time_min is latest completion time."},
        {"sheet": "CONFIG", "description": "Input parameters and derived statistics for reproducibility."},
        {"sheet": "VALIDATION", "description": "Basic structural validation checks for the generated instance."},
        {"sheet": "DISTANCE_MATRIX", "description": "Optional Manhattan distance and travel time matrix."},
    ]
    return pd.DataFrame(rows)


def plot_instance(nodes_df: pd.DataFrame, clusters_df: pd.DataFrame, out_png: str, map_size: float, title: str) -> None:
    if not out_png:
        return
    plt.figure(figsize=(7, 7))
    elev = nodes_df[nodes_df["node_type"] == "ELEVATOR"].copy()
    station = nodes_df[nodes_df["node_type"] == "STATION"].copy()
    type_markers = {"RES": "o", "OFF": "s", "COM": "^", "SCH": "D"}
    for btype, marker in type_markers.items():
        sub = elev[elev["building_type"] == btype]
        if not sub.empty:
            plt.scatter(sub["x_km"], sub["y_km"], s=9, marker=marker, alpha=0.65, label=btype)
    if not station.empty:
        plt.scatter(station["x_km"], station["y_km"], s=160, marker="X", label="STATION")
    restricted = clusters_df[clusters_df["is_time_restricted"] == 1]
    if not restricted.empty:
        plt.scatter(restricted["center_x_km"], restricted["center_y_km"], s=40, marker="+", label="restricted cluster")
    plt.xlim(0, float(map_size))
    plt.ylim(0, float(map_size))
    plt.gca().set_aspect("equal", adjustable="box")
    plt.title(title)
    plt.xlabel("x (km)")
    plt.ylabel("y (km)")
    plt.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    plt.tight_layout()
    plt.savefig(out_png, dpi=220)
    plt.close()


def generate_instance(
    out_xlsx: str,
    out_png: Optional[str] = None,
    instance_name: Optional[str] = None,
    n_elevators: int = 500,
    n_clusters: Optional[int] = None,
    cluster_pattern: str = "CU",
    tw_scenario: str = "TW0",
    seed: int = DEFAULTS["seed"],
    map_size: float = DEFAULTS["map_size"],
    include_distance_matrix: bool = False,
    building_type_ratios: str = DEFAULTS["building_type_ratios"],
) -> Dict[str, object]:
    t0 = time.time()
    rng = np.random.default_rng(int(seed))
    cluster_pattern = str(cluster_pattern).upper()
    tw_scenario = str(tw_scenario).upper()
    if instance_name is None:
        instance_name = f"{DEFAULTS['instance_prefix']}-{cluster_pattern}-{int(n_elevators)}-{tw_scenario}-{int(seed):03d}"

    clusters_df = generate_clusters(
        rng=rng,
        n_elevators=int(n_elevators),
        n_clusters=n_clusters,
        cluster_pattern=cluster_pattern,
        tw_scenario=tw_scenario,
        map_size=float(map_size),
        building_type_ratios=building_type_ratios,
        cluster_size_min=int(DEFAULTS["cluster_size_min"]),
        cluster_size_max=int(DEFAULTS["cluster_size_max"]),
        cluster_size_target=int(DEFAULTS["cluster_size_target"]),
        cluster_radius_min=float(DEFAULTS["cluster_radius_min"]),
        cluster_radius_max=float(DEFAULTS["cluster_radius_max"]),
        zonal_zone_count=int(DEFAULTS["zonal_zone_count"]),
        zonal_zone_radius=float(DEFAULTS["zonal_zone_radius"]),
        service_min=float(DEFAULTS["service_min"]),
    )
    nodes_df, tasks_df_raw = generate_nodes_and_tasks(
        rng=rng,
        clusters_df=clusters_df,
        station_id=str(DEFAULTS["station_id"]),
        map_size=float(map_size),
        service_min=float(DEFAULTS["service_min"]),
    )
    tasks_df, windows_df = build_task_windows(
        tasks_df=tasks_df_raw,
        cycle_days=int(DEFAULTS["cycle_days"]),
        day1_weekday=int(DEFAULTS["day1_weekday"]),
        service_min=float(DEFAULTS["service_min"]),
        tw_policy=str(DEFAULTS["tw_policy"]),
    )
    n_pool, tech_stats = estimate_technician_pool(
        tasks_df=tasks_df,
        windows_df=windows_df,
        cycle_days=int(DEFAULTS["cycle_days"]),
        regular_work_min=int(DEFAULTS["regular_work_min"]),
        service_min=float(DEFAULTS["service_min"]),
        technician_pool_factor=float(DEFAULTS["technician_pool_factor"]),
        technician_pool_buffer=int(DEFAULTS["technician_pool_buffer"]),
    )
    technicians_df = build_technicians(
        n_technicians_max=n_pool,
        station_id=str(DEFAULTS["station_id"]),
        speed_kmph=float(DEFAULTS["speed_kmph"]),
        shift_start_min=int(DEFAULTS["shift_start_min"]),
        shift_end_min=int(DEFAULTS["shift_end_min"]),
        regular_work_min=int(DEFAULTS["regular_work_min"]),
        max_work_min=int(DEFAULTS["max_work_min"]),
    )
    validation_df = validate_instance(
        nodes_df=nodes_df,
        clusters_df=clusters_df,
        technicians_df=technicians_df,
        tasks_df=tasks_df,
        windows_df=windows_df,
        service_min=float(DEFAULTS["service_min"]),
    )

    params = {
        "instance_name": instance_name,
        "map_size": float(map_size),
        "n_elevators": int(n_elevators),
        "n_clusters": int(len(clusters_df)),
        "cluster_pattern": cluster_pattern,
        "tw_scenario": tw_scenario,
        "tw_scenario_scope": "non_RES_clusters_only",
        "seed": int(seed),
        "station_count": 1,
        "station_location": "map_center",
        "cycle_days": int(DEFAULTS["cycle_days"]),
        "day1_weekday": int(DEFAULTS["day1_weekday"]),
        "shift_start_min": int(DEFAULTS["shift_start_min"]),
        "shift_end_min": int(DEFAULTS["shift_end_min"]),
        "regular_work_min": int(DEFAULTS["regular_work_min"]),
        "max_work_min": int(DEFAULTS["max_work_min"]),
        "allow_overtime": bool(DEFAULTS["allow_overtime"]),
        "service_min": float(DEFAULTS["service_min"]),
        "distance_metric": str(DEFAULTS["distance_metric"]),
        "speed_kmph": float(DEFAULTS["speed_kmph"]),
        "cluster_size_min": int(DEFAULTS["cluster_size_min"]),
        "cluster_size_max": int(DEFAULTS["cluster_size_max"]),
        "cluster_radius_min": float(DEFAULTS["cluster_radius_min"]),
        "cluster_radius_max": float(DEFAULTS["cluster_radius_max"]),
        "building_type_ratios": building_type_ratios,
        "technician_mode": "candidate_pool_minimize_used_technicians",
    }
    config_df = build_config(params, clusters_df, tasks_df, windows_df, tech_stats)
    readme_df = build_readme()

    os.makedirs(os.path.dirname(os.path.abspath(out_xlsx)) or ".", exist_ok=True)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        nodes_df.to_excel(writer, sheet_name="NODES", index=False)
        clusters_df.to_excel(writer, sheet_name="CLUSTERS", index=False)
        technicians_df.to_excel(writer, sheet_name="TECHNICIANS", index=False)
        tasks_df.to_excel(writer, sheet_name="TASKS", index=False)
        windows_df.to_excel(writer, sheet_name="TASK_WINDOWS", index=False)
        config_df.to_excel(writer, sheet_name="CONFIG", index=False)
        validation_df.to_excel(writer, sheet_name="VALIDATION", index=False)
        readme_df.to_excel(writer, sheet_name="README", index=False)
        if include_distance_matrix:
            dm_df = build_distance_matrix(nodes_df, speed_kmph=float(DEFAULTS["speed_kmph"]))
            dm_df.to_excel(writer, sheet_name="DISTANCE_MATRIX", index=False)

    if out_png:
        plot_instance(nodes_df, clusters_df, out_png=out_png, map_size=float(map_size), title=instance_name)

    return {
        "instance_name": instance_name,
        "out_xlsx": out_xlsx,
        "out_png": out_png or "",
        "n_elevators": int(len(tasks_df)),
        "n_clusters": int(len(clusters_df)),
        "n_technician_candidates": int(len(technicians_df)),
        "n_restricted_clusters": int(clusters_df["is_time_restricted"].sum()),
        "n_restricted_tasks": int(tasks_df["is_time_restricted"].sum()),
        "validation_status": "PASS" if bool(validation_df.iloc[-1]["passed"]) else "FAIL",
        "runtime_sec": round(time.time() - t0, 4),
    }


def parse_int_list(text: str) -> List[int]:
    return [int(x.strip()) for x in str(text).split(",") if x.strip()]


def parse_str_list(text: str) -> List[str]:
    return [str(x.strip()).upper() for x in str(text).split(",") if x.strip()]


def generate_batch(
    out_dir: str,
    scales: Sequence[int],
    cluster_patterns: Sequence[str],
    tw_scenarios: Sequence[str],
    seeds: Sequence[int],
    map_size: float,
    include_png: bool,
    include_distance_matrix_small_only: bool,
) -> pd.DataFrame:
    os.makedirs(out_dir, exist_ok=True)
    rows: List[dict] = []
    for n in scales:
        for pattern in cluster_patterns:
            for tw in tw_scenarios:
                for seed in seeds:
                    name = f"{DEFAULTS['instance_prefix']}-{str(pattern).upper()}-{int(n)}-{str(tw).upper()}-{int(seed):03d}"
                    xlsx_path = os.path.join(out_dir, f"{name}.xlsx")
                    png_path = os.path.join(out_dir, f"{name}.png") if include_png else None
                    include_dm = bool(include_distance_matrix_small_only and int(n) <= 100)
                    row = generate_instance(
                        out_xlsx=xlsx_path,
                        out_png=png_path,
                        instance_name=name,
                        n_elevators=int(n),
                        n_clusters=None,
                        cluster_pattern=str(pattern).upper(),
                        tw_scenario=str(tw).upper(),
                        seed=int(seed),
                        map_size=float(map_size),
                        include_distance_matrix=include_dm,
                    )
                    rows.append(row)
                    print(f"[OK] {name} validation={row['validation_status']}")
    summary_df = pd.DataFrame(rows)
    summary_path = os.path.join(out_dir, "batch_summary.csv")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"[OK] wrote {summary_path}")
    return summary_df


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate EMD benchmark instances")
    p.add_argument("--out_xlsx", help="Output Excel path for single instance")
    p.add_argument("--out_png", default="", help="Output plot path for single instance")
    p.add_argument("--instance_name", default="", help="Optional instance name")
    p.add_argument("--n_elevators", type=int, default=500)
    p.add_argument("--n_clusters", type=int, default=0, help="0 means auto: ceil(n_elevators/7)")
    p.add_argument("--cluster_pattern", choices=["CU", "CH", "CZ"], default="CU")
    p.add_argument("--tw_scenario", choices=["TW0", "TW50", "TW75", "TW100"], default="TW0")
    p.add_argument("--seed", type=int, default=int(DEFAULTS["seed"]))
    p.add_argument("--map_size", type=float, default=float(DEFAULTS["map_size"]))
    p.add_argument("--include_distance_matrix", action="store_true")
    p.add_argument("--building_type_ratios", default=str(DEFAULTS["building_type_ratios"]))

    p.add_argument("--batch", action="store_true", help="Generate a batch of standard scenarios")
    p.add_argument("--out_dir", default="/mnt/data/emd_v3_batch", help="Batch output directory")
    p.add_argument("--batch_scales", default="100,500,1000")
    p.add_argument("--batch_patterns", default="CU,CH,CZ")
    p.add_argument("--batch_tw", default="TW0,TW50,TW75")
    p.add_argument("--batch_seeds", default="12", help="Use one seed for 27 instances, or e.g. 12,34,56 for 81 instances")
    p.add_argument("--batch_png", action="store_true")
    p.add_argument("--batch_distance_matrix_small_only", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch:
        generate_batch(
            out_dir=str(args.out_dir),
            scales=parse_int_list(args.batch_scales),
            cluster_patterns=parse_str_list(args.batch_patterns),
            tw_scenarios=parse_str_list(args.batch_tw),
            seeds=parse_int_list(args.batch_seeds),
            map_size=float(args.map_size),
            include_png=bool(args.batch_png),
            include_distance_matrix_small_only=bool(args.batch_distance_matrix_small_only),
        )
        return

    if not args.out_xlsx:
        raise SystemExit("--out_xlsx is required for single instance mode, or use --batch")
    row = generate_instance(
        out_xlsx=str(args.out_xlsx),
        out_png=str(args.out_png) if args.out_png else None,
        instance_name=str(args.instance_name) if args.instance_name else None,
        n_elevators=int(args.n_elevators),
        n_clusters=int(args.n_clusters) if int(args.n_clusters) > 0 else None,
        cluster_pattern=str(args.cluster_pattern).upper(),
        tw_scenario=str(args.tw_scenario).upper(),
        seed=int(args.seed),
        map_size=float(args.map_size),
        include_distance_matrix=bool(args.include_distance_matrix),
        building_type_ratios=str(args.building_type_ratios),
    )
    print(f"[OK] wrote {row['out_xlsx']}")
    if row.get("out_png"):
        print(f"[OK] wrote {row['out_png']}")
    print(f"[OK] instance={row['instance_name']} validation={row['validation_status']}")


if __name__ == "__main__":
    main()
