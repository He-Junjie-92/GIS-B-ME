# -*- coding: utf-8 -*-
"""Formal building-capacity rules for the GIS-B multi-elevator benchmark."""

from __future__ import annotations

import math
import re
from typing import Any, Dict

import numpy as np


BUILDING_CAPACITY_RULES: Dict[str, dict] = {
    "RES": {
        "area_breaks_m2": (250, 600, 1200, 2500, 4000),
        "area_counts": (1, 2, 3, 4, 5, 6),
        "level_breaks": (8, 18, 30, 45),
        "level_counts": (1, 2, 3, 4, 5),
        "max_count": 6,
    },
    "OFF": {
        "area_breaks_m2": (180, 450, 900, 1800, 3500),
        "area_counts": (1, 2, 3, 4, 5, 6),
        "level_breaks": (6, 12, 20, 30, 45),
        "level_counts": (1, 2, 3, 4, 5, 6),
        "max_count": 6,
    },
    "COM": {
        "area_breaks_m2": (250, 600, 1200, 2500, 5000),
        "area_counts": (1, 2, 3, 4, 6, 8),
        "level_breaks": (4, 8, 15, 25, 40),
        "level_counts": (1, 2, 3, 4, 6, 8),
        "max_count": 8,
    },
    "SCH": {
        "area_breaks_m2": (350, 800, 1600, 3200),
        "area_counts": (1, 2, 3, 4, 5),
        "level_breaks": (4, 8, 15, 25),
        "level_counts": (1, 2, 3, 4, 5),
        "max_count": 5,
    },
}

FLOOR_HEIGHT_APPROX_M = 3.0
AREA_WINSOR_QUANTILE = 0.99
SEARCH_RADIUS_MULTIPLIERS = (1.0, 1.5, 2.0)
RULE_VERSION = "GIS-B-ME-capacity-v1.0"


def parse_osm_number(value: Any) -> float:
    """Parse the first positive numeric value from an OSM scalar-like field."""
    if value is None:
        return math.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if math.isfinite(number) and number > 0 else math.nan
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", "."))
    if not match:
        return math.nan
    number = float(match.group(0))
    return number if math.isfinite(number) and number > 0 else math.nan


def derive_levels(level_value: Any, height_value: Any) -> tuple[float, str]:
    """Return usable levels and a transparent data-quality label."""
    levels = parse_osm_number(level_value)
    if math.isfinite(levels):
        return float(max(1, round(levels))), "levels_observed"
    height = parse_osm_number(height_value)
    if math.isfinite(height):
        return float(max(1, round(height / FLOOR_HEIGHT_APPROX_M))), "height_derived"
    return math.nan, "area_only"


def _tier_count(value: float, breaks: tuple[float, ...], counts: tuple[int, ...]) -> int:
    if not math.isfinite(value):
        return int(counts[0])
    index = int(np.searchsorted(np.asarray(breaks, dtype=float), value, side="right"))
    return int(counts[index])


def estimate_building_capacity(
    building_type: str,
    area_m2: float,
    levels: float = math.nan,
    area_cap_m2: float = math.inf,
    threshold_factor: float = 1.0,
) -> dict:
    """Estimate a benchmark task-capacity upper bound for one building."""
    building_type = str(building_type).upper()
    if building_type not in BUILDING_CAPACITY_RULES:
        raise ValueError(f"Unsupported building type: {building_type}")
    rule = BUILDING_CAPACITY_RULES[building_type]
    threshold_factor = float(threshold_factor)
    if not math.isfinite(threshold_factor) or threshold_factor <= 0:
        raise ValueError("threshold_factor must be a positive finite number")
    observed_area = float(area_m2)
    effective_area = min(observed_area, float(area_cap_m2))
    area_count = _tier_count(
        effective_area,
        tuple(float(value) * threshold_factor for value in rule["area_breaks_m2"]),
        tuple(rule["area_counts"]),
    )
    if math.isfinite(float(levels)):
        level_count = _tier_count(
            float(levels),
            tuple(float(value) * threshold_factor for value in rule["level_breaks"]),
            tuple(rule["level_counts"]),
        )
        raw_count = max(area_count, level_count)
        basis = "building_levels" if level_count > area_count else "footprint_area"
    else:
        level_count = math.nan
        raw_count = area_count
        basis = "footprint_area"
    capacity = min(int(raw_count), int(rule["max_count"]))
    return {
        "estimated_elevator_capacity": int(capacity),
        "area_capacity": int(area_count),
        "level_capacity": level_count,
        "capacity_basis": basis,
        "capacity_area_effective_m2": float(effective_area),
        "capacity_threshold_factor": threshold_factor,
    }


def jsonable_rules() -> dict:
    return {
        "rule_version": RULE_VERSION,
        "floor_height_approx_m": FLOOR_HEIGHT_APPROX_M,
        "area_winsor_quantile": AREA_WINSOR_QUANTILE,
        "search_radius_multipliers": list(SEARCH_RADIUS_MULTIPLIERS),
        "building_types": {
            key: {
                item_key: list(item_value) if isinstance(item_value, tuple) else item_value
                for item_key, item_value in value.items()
            }
            for key, value in BUILDING_CAPACITY_RULES.items()
        },
    }
