# -*- coding: utf-8 -*-
"""Validate a GIS-B solution independently against an instance and road matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "technician_id",
    "day",
    "route_order",
    "task_id",
    "arrival_time",
    "start_time",
    "finish_time",
    "travel_time_from_prev",
    "waiting_time",
    "service_time",
    "route_duration",
    "route_travel_time",
}


def close(left: float, right: float, tolerance: float) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def validate(instance_dir: Path, solution_path: Path, tolerance: float) -> dict[str, object]:
    workbook = instance_dir / "instance.xlsx"
    matrix_path = instance_dir / "road_matrix.parquet"
    if not workbook.exists() or not matrix_path.exists():
        raise FileNotFoundError("instance.xlsx and road_matrix.parquet are required")

    tasks = pd.read_excel(workbook, sheet_name="TASKS")
    windows = pd.read_excel(workbook, sheet_name="TASK_WINDOWS")
    nodes = pd.read_excel(workbook, sheet_name="NODES")
    technicians = pd.read_excel(workbook, sheet_name="TECHNICIANS")
    solution = pd.read_csv(solution_path)
    matrix = pd.read_parquet(matrix_path)

    missing_columns = sorted(REQUIRED_COLUMNS - set(solution.columns))
    failures: list[str] = []
    if missing_columns:
        failures.append(f"missing solution columns: {missing_columns}")
        return {"valid": False, "failures": failures}

    task_ids = set(tasks["task_id"].astype(str))
    solution_ids = solution["task_id"].astype(str)
    counts = solution_ids.value_counts()
    missing_tasks = sorted(task_ids - set(solution_ids))
    duplicated_tasks = sorted(counts[counts != 1].index.tolist())
    unknown_tasks = sorted(set(solution_ids) - task_ids)
    if missing_tasks:
        failures.append(f"missing tasks: {missing_tasks[:10]}")
    if duplicated_tasks:
        failures.append(f"tasks not served exactly once: {duplicated_tasks[:10]}")
    if unknown_tasks:
        failures.append(f"unknown tasks: {unknown_tasks[:10]}")

    task_node = tasks.set_index("task_id")["node_id"].astype(str).to_dict()
    service_by_task = tasks.set_index("task_id")["service_min"].astype(float).to_dict()
    valid_windows = {
        (str(row.task_id), int(row.day)): (float(row.ready_time_min), float(row.due_time_min))
        for row in windows.itertuples(index=False)
    }
    max_work = technicians.set_index("technician_id")["max_work_min"].astype(float).to_dict()
    station_rows = nodes[nodes["node_type"].astype(str).str.upper() == "STATION"]
    if len(station_rows) != 1:
        failures.append(f"expected one station node, got {len(station_rows)}")
        station_id = str(station_rows.iloc[0]["node_id"]) if len(station_rows) else "S01"
    else:
        station_id = str(station_rows.iloc[0]["node_id"])

    travel = matrix.set_index(["from_node_id", "to_node_id"])["road_time_min"].astype(float).to_dict()
    total_travel = 0.0
    total_waiting = 0.0
    max_daily = 0.0

    ordered = solution.sort_values(["technician_id", "day", "route_order"])
    for (technician_id, day), route in ordered.groupby(["technician_id", "day"], sort=False):
        technician_id = str(technician_id)
        day = int(day)
        route = route.reset_index(drop=True)
        expected_orders = list(range(1, len(route) + 1))
        actual_orders = route["route_order"].astype(int).tolist()
        if actual_orders != expected_orders:
            failures.append(f"non-consecutive route order for {technician_id} day {day}")

        previous_node = station_id
        previous_finish = 0.0
        route_travel = 0.0
        for row in route.itertuples(index=False):
            task_id = str(row.task_id)
            if task_id not in task_node:
                continue
            node_id = task_node[task_id]
            expected_travel = float(travel[(previous_node, node_id)])
            expected_arrival = previous_finish + expected_travel
            expected_waiting = max(0.0, float(row.start_time) - expected_arrival)
            expected_service = float(service_by_task[task_id])
            window = valid_windows.get((task_id, day))

            if not close(row.travel_time_from_prev, expected_travel, tolerance):
                failures.append(f"travel mismatch for {task_id}")
            if not close(row.arrival_time, expected_arrival, tolerance):
                failures.append(f"arrival mismatch for {task_id}")
            if not close(row.waiting_time, expected_waiting, tolerance):
                failures.append(f"waiting mismatch for {task_id}")
            if not close(row.service_time, expected_service, tolerance):
                failures.append(f"service mismatch for {task_id}")
            if not close(row.finish_time, float(row.start_time) + expected_service, tolerance):
                failures.append(f"finish mismatch for {task_id}")
            if window is None:
                failures.append(f"no valid window for {task_id} on day {day}")
            elif float(row.start_time) < window[0] - tolerance or float(row.finish_time) > window[1] + tolerance:
                failures.append(f"time-window violation for {task_id}")

            route_travel += expected_travel
            total_waiting += expected_waiting
            previous_node = node_id
            previous_finish = float(row.finish_time)

        return_travel = float(travel[(previous_node, station_id)])
        route_travel += return_travel
        route_duration = previous_finish + return_travel
        total_travel += route_travel
        max_daily = max(max_daily, route_duration)
        if technician_id not in max_work:
            failures.append(f"unknown technician {technician_id}")
        elif route_duration > max_work[technician_id] + tolerance:
            failures.append(f"daily work limit exceeded for {technician_id} day {day}")
        if not close(route["route_duration"].iloc[0], route_duration, tolerance):
            failures.append(f"route duration mismatch for {technician_id} day {day}")
        if not close(route["route_travel_time"].iloc[0], route_travel, tolerance):
            failures.append(f"route travel mismatch for {technician_id} day {day}")

    return {
        "valid": not failures,
        "instance": instance_dir.name,
        "solution": solution_path.name,
        "n_tasks": len(task_ids),
        "n_solution_rows": len(solution),
        "used_technicians": int(solution["technician_id"].nunique()),
        "total_travel_time": total_travel,
        "total_waiting_time": total_waiting,
        "max_daily_work_time": max_daily,
        "failure_count": len(failures),
        "failures": failures[:100],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-dir", type=Path, required=True)
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=1e-5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(args.instance_dir, args.solution, args.tolerance)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
