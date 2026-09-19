# -*- coding: utf-8 -*-
"""Generate one GIS-B EMD benchmark prototype instance.

GIS-B anchors EMD maintenance tasks to real OSM building footprints and routes
them through the real OSM driving network. Building geometry and locations are
real; building type ratios and TW rules remain controlled by the benchmark.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point

from road_matrix_io import write_road_matrix


BENCHMARK_SRC = Path(__file__).resolve().parents[2] / "src"
GIS_SRC = Path(__file__).resolve().parent
for path in [BENCHMARK_SRC, GIS_SRC]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from EMD_Benchmark_Generator_v3 import (  # noqa: E402
    DEFAULTS,
    build_config,
    build_readme,
    build_task_windows,
    build_technicians,
    estimate_technician_pool,
    generate_clusters,
    validate_instance,
)
from generate_gis_a_instance import (  # noqa: E402
    bbox_tuple,
    build_gis_validation,
    build_road_matrix,
    build_road_network_metadata,
    local_square,
    prepare_graph,
)
from building_capacity_rules import (  # noqa: E402
    AREA_WINSOR_QUANTILE,
    BUILDING_CAPACITY_RULES,
    RULE_VERSION,
    SEARCH_RADIUS_MULTIPLIERS,
    derive_levels,
    estimate_building_capacity,
    jsonable_rules,
    parse_osm_number,
)
from gis_b_me_v2_rules import (  # noqa: E402
    BUILDING_TYPE_RATIOS as V2_BUILDING_TYPE_RATIOS,
    FIXED_SPEED_KMPH as V2_FIXED_SPEED_KMPH,
    PILOT_CANDIDATE_POOL_BY_SCALE as V2_PILOT_CANDIDATE_POOL_BY_SCALE,
    build_task_windows_v2,
    road_time_from_distance,
)
from gis_b_me_tw100_rules import (  # noqa: E402
    TIME_RULE_MODE as TW100_TIME_RULE_MODE,
    TW_SCENARIO_LABEL,
    build_task_windows_tw100,
)


def load_config(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    config_dir = path.resolve().parent
    for field in (
        "output_root",
        "shared_road_network_path",
        "shared_building_candidates_path",
    ):
        value = str(config.get(field, "")).strip()
        if value and not Path(value).is_absolute():
            config[field] = str((config_dir / value).resolve())
    return config


def instance_name(cfg: Dict[str, object]) -> str:
    if str(cfg.get("time_rule_mode", "")).lower() in {
        "fixed_by_building_type_v2",
        TW100_TIME_RULE_MODE,
    }:
        return "GISB-{city}-{pattern}-{scale}-S{seed:03d}".format(
            city=str(cfg["city_id"]).upper(),
            pattern=str(cfg["cluster_pattern"]).upper(),
            scale=int(cfg["scale"]),
            seed=int(cfg["seed"]),
        )
    return "GISB-{city}-{pattern}-{scale}-{tw}-{seed:03d}".format(
        city=str(cfg["city_id"]).upper(),
        pattern=str(cfg["cluster_pattern"]).upper(),
        scale=int(cfg["scale"]),
        tw=str(cfg["tw_scenario"]).upper(),
        seed=int(cfg["seed"]),
    )


def load_city_assets(cfg: Dict[str, object]) -> tuple[nx.MultiDiGraph, gpd.GeoDataFrame]:
    graph_path = str(cfg.get("shared_road_network_path", "")).strip()
    buildings_path = str(cfg.get("shared_building_candidates_path", "")).strip()
    if graph_path and buildings_path:
        G = ox.load_graphml(Path(graph_path))
        buildings = gpd.read_file(Path(buildings_path))
        if buildings.crs is None:
            buildings = buildings.set_crs("EPSG:4326")
        buildings = buildings.to_crs(G.graph["crs"])
        required = {
            "building_anchor_id",
            "building_osm_id",
            "area_m2",
            "projected_x",
            "projected_y",
            "nearest_osm_node_id",
            "snap_distance_m",
            "lon",
            "lat",
        }
        missing = required.difference(buildings.columns)
        if missing:
            raise ValueError(f"Shared building candidates missing columns: {sorted(missing)}")
        return G, buildings.reset_index(drop=True)
    G = prepare_graph(cfg)
    return G, download_building_candidates(cfg, G)


def download_building_candidates(cfg: Dict[str, object], G: nx.MultiDiGraph) -> gpd.GeoDataFrame:
    raw = ox.features_from_bbox(bbox_tuple(cfg), tags={"building": True})
    if raw.empty:
        raise RuntimeError("No OSM buildings found in bbox.")
    buildings = raw[raw.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if buildings.empty:
        raise RuntimeError("No polygonal OSM buildings found in bbox.")

    buildings = buildings.reset_index()
    # OSMnx 2.x names the feature index levels ``element`` and ``id``;
    # older releases used ``element_type`` and ``osmid``.  Never fall back to
    # the DataFrame row number because that produces plausible-looking but
    # invalid OSM identifiers.
    element_col = "element" if "element" in buildings.columns else "element_type"
    id_col = "id" if "id" in buildings.columns else "osmid"
    missing_id_columns = [c for c in (element_col, id_col) if c not in buildings.columns]
    if missing_id_columns:
        raise RuntimeError(
            "OSM building feature index columns are missing after reset_index(): "
            f"{missing_id_columns}; available={list(buildings.columns)}"
        )
    buildings["building_osm_id"] = (
        buildings[element_col].astype(str) + "/" + buildings[id_col].astype(str)
    )
    buildings_4326 = buildings.set_geometry("geometry").set_crs("EPSG:4326", allow_override=True)
    buildings_proj = buildings_4326.to_crs(G.graph["crs"])
    buildings_proj["area_m2"] = buildings_proj.geometry.area.astype(float)
    buildings_proj = buildings_proj[buildings_proj["area_m2"] >= float(cfg.get("min_building_area_m2", 40.0))].copy()
    if buildings_proj.empty:
        raise RuntimeError("No buildings remain after area filtering.")

    reps = buildings_proj.geometry.representative_point()
    road_node_ids = np.array([int(nid) for nid in G.nodes()], dtype=np.int64)
    road_xy = np.array([[float(G.nodes[int(nid)]["x"]), float(G.nodes[int(nid)]["y"])] for nid in road_node_ids], dtype=float)
    tree = cKDTree(road_xy)
    distances, idxs = tree.query(np.array([[p.x, p.y] for p in reps], dtype=float), k=1)
    buildings_proj["projected_x"] = [float(p.x) for p in reps]
    buildings_proj["projected_y"] = [float(p.y) for p in reps]
    buildings_proj["nearest_osm_node_id"] = [int(road_node_ids[int(i)]) for i in idxs]
    buildings_proj["snap_distance_m"] = distances.astype(float)
    buildings_proj["osm_building_tag"] = buildings_proj.get("building", "").astype(str)

    threshold = float(cfg.get("max_snap_distance_m", 150.0))
    buildings_proj = buildings_proj[buildings_proj["snap_distance_m"] <= threshold].copy()
    if buildings_proj.empty:
        raise RuntimeError("No buildings remain after snap-distance filtering.")

    transformer = Transformer.from_crs(G.graph["crs"], "EPSG:4326", always_xy=True)
    lon_lat = [transformer.transform(float(x), float(y)) for x, y in zip(buildings_proj["projected_x"], buildings_proj["projected_y"])]
    buildings_proj["lon"] = [float(x[0]) for x in lon_lat]
    buildings_proj["lat"] = [float(x[1]) for x in lon_lat]
    buildings_proj["building_anchor_id"] = [f"B{i+1:05d}" for i in range(len(buildings_proj))]
    return buildings_proj.reset_index(drop=True)


def select_cluster_buildings(
    buildings: gpd.GeoDataFrame,
    clusters: pd.DataFrame,
    rng: np.random.Generator,
    pattern: str,
) -> pd.DataFrame:
    pattern = str(pattern).upper()
    b = buildings.copy()
    coords = b[["projected_x", "projected_y"]].to_numpy(dtype=float)
    selected_indices: List[int] = []
    n = len(clusters)
    if len(b) < n:
        raise RuntimeError(f"Need {n} building anchors, but only {len(b)} candidates are available.")

    if pattern in {"CU", "CH"}:
        minx, miny = coords.min(axis=0)
        maxx, maxy = coords.max(axis=0)
        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))
        cells = [(r, c) for r in range(rows) for c in range(cols)]
        rng.shuffle(cells)
        used = set()
        for r, c in cells:
            if len(selected_indices) >= n:
                break
            x0 = minx + (maxx - minx) * c / cols
            x1 = minx + (maxx - minx) * (c + 1) / cols
            y0 = miny + (maxy - miny) * r / rows
            y1 = miny + (maxy - miny) * (r + 1) / rows
            candidates = b[(b["projected_x"].between(x0, x1)) & (b["projected_y"].between(y0, y1))]
            candidate_indices = [int(i) for i in candidates.index if int(i) not in used]
            if candidate_indices:
                idx = int(rng.choice(candidate_indices))
                selected_indices.append(idx)
                used.add(idx)
        if len(selected_indices) < n:
            remaining = [int(i) for i in b.index if int(i) not in used]
            rng.shuffle(remaining)
            selected_indices.extend(remaining[: n - len(selected_indices)])

    elif pattern == "CZ":
        tree = cKDTree(coords)
        zone_count = int(DEFAULTS["zonal_zone_count"])
        zone_indices = rng.choice(np.arange(len(b)), size=min(zone_count, len(b)), replace=False)
        used = set()
        for zi in zone_indices:
            k = min(len(b), int(math.ceil(n / len(zone_indices))) + 10)
            _, near = tree.query(coords[int(zi)], k=k)
            near_list = np.atleast_1d(near).astype(int).tolist()
            for idx in near_list:
                if len(selected_indices) >= n:
                    break
                if idx not in used:
                    selected_indices.append(idx)
                    used.add(idx)
            if len(selected_indices) >= n:
                break
        if len(selected_indices) < n:
            remaining = [int(i) for i in b.index if int(i) not in used]
            rng.shuffle(remaining)
            selected_indices.extend(remaining[: n - len(selected_indices)])
    else:
        raise ValueError("cluster_pattern must be CU, CH, or CZ")

    anchors = b.loc[selected_indices[:n]].reset_index(drop=True)
    out = clusters.copy().reset_index(drop=True)
    for col in [
        "building_anchor_id",
        "building_osm_id",
        "osm_building_tag",
        "area_m2",
        "projected_x",
        "projected_y",
        "lon",
        "lat",
        "nearest_osm_node_id",
        "snap_distance_m",
    ]:
        out[f"anchor_{col}"] = anchors[col].to_list()
    if "frozen_building_type" in anchors.columns:
        out["anchor_frozen_building_type"] = anchors["frozen_building_type"].astype(str).to_list()
    out["center_projected_x"] = out["anchor_projected_x"]
    out["center_projected_y"] = out["anchor_projected_y"]
    out["center_lon"] = out["anchor_lon"]
    out["center_lat"] = out["anchor_lat"]
    out["center_osm_node_id"] = out["anchor_nearest_osm_node_id"]
    out["center_snap_distance_m"] = out["anchor_snap_distance_m"]
    out["source_mode"] = "osm_building_anchor_controlled_type"
    out["urban_zone"] = out.get("zone_id", 0)
    return out


def assign_task_buildings(
    buildings: gpd.GeoDataFrame,
    clusters: pd.DataFrame,
    rng: np.random.Generator,
    search_radius_m: float,
    area_cap_m2: float,
    capacity_threshold_factor: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    coords = buildings[["projected_x", "projected_y"]].to_numpy(dtype=float)
    tree = cKDTree(coords)
    nodes: List[dict] = []
    tasks: List[dict] = []

    # Station is represented by the road node nearest the center of all selected anchors.
    sx = float(clusters["center_projected_x"].mean())
    sy = float(clusters["center_projected_y"].mean())
    station_idx = int(tree.query(np.array([sx, sy]), k=1)[1])
    station_building = buildings.iloc[station_idx]
    nodes.append(
        {
            "node_id": DEFAULTS["station_id"],
            "node_type": "STATION",
            "x_km": 0.0,
            "y_km": 0.0,
            "cluster_id": "NA",
            "building_type": "NA",
            "station_id": DEFAULTS["station_id"],
            "lon": float(station_building["lon"]),
            "lat": float(station_building["lat"]),
            "building_anchor_id": "NA",
            "building_osm_id": "NA",
            "building_area_m2": math.nan,
            "building_levels": math.nan,
            "building_height_m": math.nan,
            "capacity_data_quality": "NA",
            "estimated_elevator_capacity": 0,
            "assigned_elevators_in_building": 0,
            "capacity_basis": "NA",
            "osm_building_tag": "NA",
            "osm_node_id": int(station_building["nearest_osm_node_id"]),
            "snap_distance_m": 0.0,
            "projected_x": float(station_building["projected_x"]),
            "projected_y": float(station_building["projected_y"]),
            "gis_source": "OSM",
            "crs": "EPSG:4326",
        }
    )

    used_building_ids = {str(station_building["building_anchor_id"])}
    task_idx = 0
    for _, c in clusters.iterrows():
        center_xy = np.array([float(c["center_projected_x"]), float(c["center_projected_y"])], dtype=float)
        remaining = int(c["n_elevators"])
        candidate_order: list[int] = []
        seen_indices: set[int] = set()
        for multiplier in SEARCH_RADIUS_MULTIPLIERS:
            near = sorted(
                int(i)
                for i in tree.query_ball_point(
                    center_xy,
                    r=float(search_radius_m) * float(multiplier),
                )
                if int(i) not in seen_indices
                and str(buildings.iloc[int(i)]["building_anchor_id"]) not in used_building_ids
            )
            if near:
                shuffled = rng.permutation(np.asarray(near, dtype=int)).astype(int).tolist()
                candidate_order.extend(shuffled)
                seen_indices.update(near)

        if len(candidate_order) < len(buildings):
            distances = np.linalg.norm(coords - center_xy, axis=1)
            fallback = sorted(
                (
                    (float(distances[i]), int(i))
                    for i in range(len(buildings))
                    if int(i) not in seen_indices
                    and str(buildings.iloc[int(i)]["building_anchor_id"]) not in used_building_ids
                ),
                key=lambda item: (item[0], item[1]),
            )
            candidate_order.extend(index for _, index in fallback)

        for idx in candidate_order:
            if remaining <= 0:
                break
            b = buildings.iloc[idx]
            bid = str(b["building_anchor_id"])
            if bid in used_building_ids:
                continue
            levels, quality = derive_levels(
                b.get("building:levels", math.nan),
                b.get("height", math.nan),
            )
            height_value = parse_osm_number(b.get("height", math.nan))
            assigned_building_type = str(
                b.get("frozen_building_type", c["building_type"])
            ).upper()
            capacity = estimate_building_capacity(
                assigned_building_type,
                float(b["area_m2"]),
                levels=levels,
                area_cap_m2=area_cap_m2,
                threshold_factor=capacity_threshold_factor,
            )
            assigned = min(int(capacity["estimated_elevator_capacity"]), remaining)
            used_building_ids.add(bid)

            for _ in range(assigned):
                task_idx += 1
                node_id = f"E{task_idx:05d}"
                task_id = f"PM{task_idx:05d}"
                row = {
                    "node_id": node_id,
                    "node_type": "ELEVATOR",
                    "x_km": float(b["projected_x"] / 1000.0),
                    "y_km": float(b["projected_y"] / 1000.0),
                    "cluster_id": str(c["cluster_id"]),
                    "building_type": assigned_building_type,
                    "station_id": DEFAULTS["station_id"],
                    "lon": float(b["lon"]),
                    "lat": float(b["lat"]),
                    "building_anchor_id": bid,
                    "building_osm_id": str(b["building_osm_id"]),
                    "building_area_m2": float(b["area_m2"]),
                    "building_levels": levels,
                    "building_height_m": height_value,
                    "capacity_data_quality": quality,
                    "estimated_elevator_capacity": int(
                        capacity["estimated_elevator_capacity"]
                    ),
                    "assigned_elevators_in_building": assigned,
                    "capacity_basis": str(capacity["capacity_basis"]),
                    "capacity_area_effective_m2": float(
                        capacity["capacity_area_effective_m2"]
                    ),
                    "osm_building_tag": str(b["osm_building_tag"]),
                    "osm_node_id": int(b["nearest_osm_node_id"]),
                    "snap_distance_m": float(b["snap_distance_m"]),
                    "projected_x": float(b["projected_x"]),
                    "projected_y": float(b["projected_y"]),
                    "gis_source": "OSM",
                    "crs": "EPSG:4326",
                }
                nodes.append(row)
                tasks.append(
                    {
                        "task_id": task_id,
                        "task_type": "PM",
                        "elevator_id": node_id,
                        **{
                            key: value
                            for key, value in row.items()
                            if key not in {"node_type"}
                        },
                        "service_min": float(DEFAULTS["service_min"]),
                        "priority": 3,
                        "is_time_restricted": int(c["is_time_restricted"]),
                    }
                )
            remaining -= assigned

        if remaining:
            raise RuntimeError(
                f"Insufficient unused building capacity for cluster {c['cluster_id']}: "
                f"{remaining} of {int(c['n_elevators'])} tasks remain."
            )
    nodes_df = pd.DataFrame(nodes)
    tasks_df = pd.DataFrame(tasks)
    return nodes_df, tasks_df


def build_used_buildings(nodes: pd.DataFrame, tasks: pd.DataFrame) -> pd.DataFrame:
    elev = nodes[nodes["node_type"].astype(str).str.upper() == "ELEVATOR"].copy()
    task_counts = tasks.groupby("building_anchor_id").size().rename("n_tasks_assigned").reset_index()
    type_counts = (
        tasks.groupby(["building_anchor_id", "building_type"])
        .size()
        .rename("n_tasks_by_type")
        .reset_index()
        .sort_values(["building_anchor_id", "n_tasks_by_type"], ascending=[True, False])
        .drop_duplicates("building_anchor_id")
        .rename(columns={"building_type": "assigned_building_type"})
    )
    cols = [
        "building_anchor_id",
        "building_osm_id",
        "osm_building_tag",
        "building_area_m2",
        "building_levels",
        "building_height_m",
        "capacity_data_quality",
        "estimated_elevator_capacity",
        "assigned_elevators_in_building",
        "capacity_basis",
        "capacity_area_effective_m2",
        "lon",
        "lat",
        "projected_x",
        "projected_y",
        "osm_node_id",
        "snap_distance_m",
        "city_id",
        "gis_source",
        "crs",
    ]
    out = elev[cols].drop_duplicates("building_anchor_id").copy()
    out = out.merge(task_counts, on="building_anchor_id", how="left")
    out = out.merge(type_counts[["building_anchor_id", "assigned_building_type"]], on="building_anchor_id", how="left")
    out["n_tasks_assigned"] = out["n_tasks_assigned"].fillna(0).astype(int)
    out["capacity_utilization"] = (
        out["n_tasks_assigned"] / out["estimated_elevator_capacity"].astype(float)
    )
    return out.sort_values("building_anchor_id").reset_index(drop=True)


def write_geo_outputs(
    out_dir: Path,
    G: nx.MultiDiGraph,
    nodes: pd.DataFrame,
    clusters: pd.DataFrame,
    buildings: gpd.GeoDataFrame,
    building_candidates_sample_size: int,
    write_city_assets: bool,
) -> None:
    if write_city_assets:
        road_nodes, road_edges = ox.graph_to_gdfs(G, nodes=True, edges=True)
        road_nodes.to_crs("EPSG:4326").to_file(out_dir / "road_nodes.geojson", driver="GeoJSON")
        road_edges.to_crs("EPSG:4326").to_file(out_dir / "road_edges.geojson", driver="GeoJSON")
        sample = buildings.sample(min(int(building_candidates_sample_size), len(buildings)), random_state=7) if len(buildings) else buildings
        sample.to_crs("EPSG:4326").to_file(out_dir / "building_candidates_sample.geojson", driver="GeoJSON")

    task_gdf = gpd.GeoDataFrame(
        nodes.copy(),
        geometry=[Point(xy) for xy in zip(nodes["lon"], nodes["lat"])],
        crs="EPSG:4326",
    )
    task_gdf.to_file(out_dir / "task_points.geojson", driver="GeoJSON")

    used = nodes[nodes["node_type"].astype(str).str.upper() == "ELEVATOR"].drop_duplicates("building_anchor_id").copy()
    used_gdf = gpd.GeoDataFrame(
        used,
        geometry=[Point(xy) for xy in zip(used["lon"], used["lat"])],
        crs="EPSG:4326",
    )
    used_gdf.to_file(out_dir / "used_building_anchors.geojson", driver="GeoJSON")
    used_gdf.to_file(out_dir / "used_buildings.geojson", driver="GeoJSON")

    cluster_gdf = gpd.GeoDataFrame(
        clusters.copy(),
        geometry=[Point(xy) for xy in zip(clusters["center_lon"], clusters["center_lat"])],
        crs="EPSG:4326",
    )
    cluster_gdf.to_file(out_dir / "clusters.geojson", driver="GeoJSON")


def plot_preview(out_dir: Path, G: nx.MultiDiGraph, nodes: pd.DataFrame, clusters: pd.DataFrame, buildings: gpd.GeoDataFrame, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _, ax = ox.plot_graph(
        G,
        show=False,
        close=False,
        node_size=0,
        edge_color="#c3c3c3",
        edge_linewidth=0.42,
        bgcolor="white",
    )
    sample = buildings.sample(min(600, len(buildings)), random_state=7) if len(buildings) else buildings
    sample.boundary.plot(ax=ax, color="#dddddd", linewidth=0.25, alpha=0.8)

    elev = nodes[nodes["node_type"].astype(str).str.upper() == "ELEVATOR"]
    station = nodes[nodes["node_type"].astype(str).str.upper() == "STATION"]
    colors = {"RES": "#4C78A8", "OFF": "#F58518", "COM": "#54A24B", "SCH": "#B279A2"}
    for btype, sub in elev.groupby("building_type"):
        ax.scatter(sub["projected_x"], sub["projected_y"], s=11, label=str(btype), color=colors.get(str(btype), "#777777"), alpha=0.82)
    ax.scatter(station["projected_x"], station["projected_y"], s=100, marker="X", label="STATION", color="#D62728")
    restricted = clusters[clusters["is_time_restricted"].astype(int) == 1]
    if len(restricted):
        ax.scatter(restricted["center_projected_x"], restricted["center_projected_y"], s=40, marker="+", label="restricted cluster", color="#7F3C8D")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=7)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_dir / "map_preview.png", dpi=220)
    plt.close()


def write_gis_b_instance_readme(
    out_dir: Path,
    name: str,
    matrix_filename: str,
    shared_assets: bool,
) -> None:
    road_note = (
        "- City road graph and building-candidate pool are stored once under `shared/cities/<CITY>/`."
        if shared_assets
        else "- Road graph, road GeoJSON layers, and the building sample are stored locally."
    )
    text = f"""# {name}

GIS-B-ME-v1.0 benchmark instance.

Files:

- `instance.xlsx`: EMD instance tables with GIS and building-anchor fields.
- `{matrix_filename}`: full road-network OD matrix.
- `task_points.geojson`: station and elevator task points.
- `clusters.geojson`: benchmark cluster anchors placed on OSM buildings.
- `used_buildings.geojson`: OSM building anchors used by tasks.
- `map_preview.png`: road network, building sample, station, and task preview.
- `config.json`: generation config snapshot.
{road_note}

The instance count denotes elevator maintenance tasks, not buildings. Multiple
independent elevator tasks may share one real OSM building anchor. Building
capacity uses controlled building type, OSM footprint area, and available OSM
level/height fields under rule version `{RULE_VERSION}`.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def generate(cfg: Dict[str, object]) -> Dict[str, object]:
    t0 = time.time()
    name = instance_name(cfg)
    out_dir = Path(str(cfg["output_root"])) / name
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(int(cfg["seed"]))
    G, buildings = load_city_assets(cfg)
    time_rule_mode = str(cfg.get("time_rule_mode", "")).lower()
    v2_mode = time_rule_mode == "fixed_by_building_type_v2"
    tw100_mode = time_rule_mode == TW100_TIME_RULE_MODE
    me_mode = v2_mode or tw100_mode
    if me_mode and "frozen_building_type" not in buildings.columns:
        raise ValueError(
            "GIS-B-ME v2 requires frozen_building_type in the shared building pool."
        )
    shared_assets = bool(
        str(cfg.get("shared_road_network_path", "")).strip()
        and str(cfg.get("shared_building_candidates_path", "")).strip()
    )
    area_cap_m2 = float(buildings["area_m2"].quantile(AREA_WINSOR_QUANTILE))

    # Use projected building bounds only to set a local map size for standard
    # cluster metadata. Actual cluster centers are replaced by OSM building
    # anchors immediately afterward.
    minx = float(buildings["projected_x"].min())
    miny = float(buildings["projected_y"].min())
    maxx = float(buildings["projected_x"].max())
    maxy = float(buildings["projected_y"].max())
    x0, y0, side_m = local_square((minx, miny, maxx, maxy))
    map_size_km = side_m / 1000.0

    clusters = generate_clusters(
        rng=rng,
        n_elevators=int(cfg["scale"]),
        n_clusters=None,
        cluster_pattern=str(cfg["cluster_pattern"]).upper(),
        tw_scenario=("TW0" if me_mode else str(cfg["tw_scenario"]).upper()),
        map_size=float(map_size_km),
        building_type_ratios=(
            "RES:0.74,OFF:0.12,COM:0.08,SCH:0.06"
            if me_mode
            else str(DEFAULTS["building_type_ratios"])
        ),
        cluster_size_min=int(DEFAULTS["cluster_size_min"]),
        cluster_size_max=int(DEFAULTS["cluster_size_max"]),
        cluster_size_target=int(DEFAULTS["cluster_size_target"]),
        cluster_radius_min=float(DEFAULTS["cluster_radius_min"]),
        cluster_radius_max=float(DEFAULTS["cluster_radius_max"]),
        zonal_zone_count=int(DEFAULTS["zonal_zone_count"]),
        zonal_zone_radius=min(float(DEFAULTS["zonal_zone_radius"]), max(0.5, map_size_km / 4.0)),
        service_min=float(DEFAULTS["service_min"]),
    )
    clusters = select_cluster_buildings(buildings, clusters, rng, str(cfg["cluster_pattern"]).upper())
    if me_mode:
        clusters["building_type"] = clusters["anchor_frozen_building_type"].astype(str).str.upper()
        clusters["is_time_restricted"] = (
            1
            if v2_mode
            else (clusters["building_type"].astype(str).str.upper() != "RES").astype(int)
        )
        clusters["tw_scenario"] = "FIXED_TYPE_RULES" if v2_mode else TW_SCENARIO_LABEL
    nodes, tasks_raw = assign_task_buildings(
        buildings,
        clusters,
        rng,
        search_radius_m=float(cfg.get("building_search_radius_m", 250.0)),
        area_cap_m2=area_cap_m2,
        capacity_threshold_factor=float(cfg.get("capacity_threshold_factor", 1.0)),
    )
    nodes["city_id"] = str(cfg["city_id"]).upper()
    tasks_raw["city_id"] = str(cfg["city_id"]).upper()
    clusters["city_id"] = str(cfg["city_id"]).upper()

    # Re-localize x/y to the building candidate bounding square for nicer Excel values.
    nodes["x_km"] = (nodes["projected_x"] - x0) / 1000.0
    nodes["y_km"] = (nodes["projected_y"] - y0) / 1000.0
    tasks_raw = tasks_raw.drop(columns=["x_km", "y_km"], errors="ignore").merge(
        nodes[["node_id", "x_km", "y_km"]],
        on="node_id",
        how="left",
    )
    clusters["center_x_km"] = (clusters["center_projected_x"] - x0) / 1000.0
    clusters["center_y_km"] = (clusters["center_projected_y"] - y0) / 1000.0

    window_builder = (
        build_task_windows_v2
        if v2_mode
        else build_task_windows_tw100
        if tw100_mode
        else build_task_windows
    )
    tasks, windows = window_builder(
        tasks_df=tasks_raw,
        cycle_days=int(DEFAULTS["cycle_days"]),
        day1_weekday=int(DEFAULTS["day1_weekday"]),
        service_min=float(DEFAULTS["service_min"]),
        tw_policy=str(DEFAULTS["tw_policy"]),
    )
    estimated_pool, tech_stats = estimate_technician_pool(
        tasks_df=tasks,
        windows_df=windows,
        cycle_days=int(DEFAULTS["cycle_days"]),
        regular_work_min=int(DEFAULTS["regular_work_min"]),
        service_min=float(DEFAULTS["service_min"]),
        technician_pool_factor=float(DEFAULTS["technician_pool_factor"]),
        technician_pool_buffer=int(DEFAULTS["technician_pool_buffer"]),
    )
    if me_mode:
        pool_map = {
            int(key): int(value)
            for key, value in dict(
                cfg.get("candidate_pool_by_scale", V2_PILOT_CANDIDATE_POOL_BY_SCALE)
            ).items()
        }
        n_pool = int(pool_map[int(cfg["scale"])])
        tech_stats["estimated_candidate_pool_before_v2_override"] = int(estimated_pool)
        tech_stats["v2_pilot_candidate_pool"] = n_pool
    else:
        n_pool = estimated_pool
    techs = build_technicians(
        n_technicians_max=n_pool,
        station_id=str(DEFAULTS["station_id"]),
        speed_kmph=(
            float(cfg.get("fixed_speed_kmph", V2_FIXED_SPEED_KMPH))
            if me_mode
            else float(DEFAULTS["speed_kmph"])
        ),
        shift_start_min=int(DEFAULTS["shift_start_min"]),
        shift_end_min=int(DEFAULTS["shift_end_min"]),
        regular_work_min=int(DEFAULTS["regular_work_min"]),
        max_work_min=int(DEFAULTS["max_work_min"]),
    )

    road_matrix = build_road_matrix(nodes, G)
    if me_mode:
        fixed_speed = float(cfg.get("fixed_speed_kmph", V2_FIXED_SPEED_KMPH))
        road_matrix["road_time_sec"] = road_time_from_distance(
            road_matrix["road_distance_m"].to_numpy(float), fixed_speed
        )
        road_matrix["road_time_min"] = road_matrix["road_time_sec"] / 60.0
        road_matrix["engine"] = "osmnx_shortest_distance_fixed_speed"
    road_meta = build_road_network_metadata(G, cfg)
    buildings_used = build_used_buildings(nodes, tasks)
    validation = validate_instance(nodes, clusters, techs, tasks, windows, service_min=float(DEFAULTS["service_min"]))
    gis_validation = build_gis_validation(nodes, road_matrix, cfg, G)

    params = {
        "instance_name": name,
        "benchmark_stage": str(cfg.get("benchmark_stage", "GIS-B-v1")),
        "city_id": str(cfg["city_id"]).upper(),
        "city_name": str(cfg["city_name"]),
        "bbox_west_south_east_north": json.dumps(cfg["bbox"], ensure_ascii=False),
        "osm_data_date": str(date.today()),
        "network_type": str(cfg.get("network_type", "drive")),
        "routing_engine": "osmnx",
        "source_mode": "osm_building_anchor_controlled_type",
        "distance_metric": (
            "road_network_distance_fixed_speed_time" if me_mode else "road_network_time"
        ),
        "matrix_unit_distance": "meter",
        "matrix_unit_time": "second",
        "snap_method": "building_representative_point_to_nearest_node",
        "max_snap_distance_m": float(cfg.get("max_snap_distance_m", 150.0)),
        "min_building_area_m2": float(cfg.get("min_building_area_m2", 40.0)),
        "capacity_rule_version": RULE_VERSION,
        "capacity_area_winsor_quantile": AREA_WINSOR_QUANTILE,
        "capacity_area_cap_m2": area_cap_m2,
        "capacity_threshold_factor": float(
            cfg.get("capacity_threshold_factor", 1.0)
        ),
        "building_selection_mode": "seeded_uniform_without_replacement",
        "building_search_radius_multipliers": json.dumps(
            list(SEARCH_RADIUS_MULTIPLIERS)
        ),
        "n_building_candidates": int(len(buildings)),
        "map_size": float(map_size_km),
        "n_elevators": int(cfg["scale"]),
        "n_clusters": int(len(clusters)),
        "cluster_pattern": str(cfg["cluster_pattern"]).upper(),
        "tw_scenario": (
            "FIXED_TYPE_RULES"
            if v2_mode
            else TW_SCENARIO_LABEL
            if tw100_mode
            else str(cfg["tw_scenario"]).upper()
        ),
        "time_rule_mode": str(cfg.get("time_rule_mode", "legacy_tw_scenarios")),
        "seed": int(cfg["seed"]),
        "station_count": 1,
        "cycle_days": int(DEFAULTS["cycle_days"]),
        "day1_weekday": int(DEFAULTS["day1_weekday"]),
        "regular_work_min": int(DEFAULTS["regular_work_min"]),
        "max_work_min": int(DEFAULTS["max_work_min"]),
        "allow_overtime": bool(DEFAULTS["allow_overtime"]),
        "service_min": float(DEFAULTS["service_min"]),
        "building_type_assignment": "controlled_ratio_not_osm_label",
        "max_tasks_per_building": max(
            int(rule["max_count"]) for rule in BUILDING_CAPACITY_RULES.values()
        ),
        "n_used_buildings": int(len(buildings_used)),
        "mean_elevators_per_building": float(
            buildings_used["n_tasks_assigned"].mean()
        ),
        "building_type_ratios": (
            "RES:0.74,OFF:0.12,COM:0.08,SCH:0.06"
            if me_mode
            else str(DEFAULTS["building_type_ratios"])
        ),
        "building_type_assignment_scope": (
            "frozen_city_level_spatially_stratified" if me_mode else "cluster_level"
        ),
        "fixed_speed_kmph": (
            float(cfg.get("fixed_speed_kmph", V2_FIXED_SPEED_KMPH)) if me_mode else math.nan
        ),
        "candidate_pool_mode": ("fixed_pilot_5_10_15" if me_mode else "estimated"),
        "road_network_file": (
            str(cfg.get("shared_road_network_path"))
            if shared_assets
            else "road_network.graphml"
        ),
    }
    road_matrix_path = write_road_matrix(road_matrix, out_dir)
    params["road_matrix_file"] = road_matrix_path.name
    config_df = build_config(params, clusters, tasks, windows, tech_stats)
    config_df.loc[
        config_df["param"].astype(str) == "objective_2",
        "value",
    ] = "minimize_total_road_network_travel_time"
    if me_mode:
        overrides = {
            "tw_scope": (
                "all tasks inherit fixed service availability from frozen building type"
                if v2_mode
                else "fixed business windows by building type; no TW scenario dimension"
            ),
            "derived_restricted_non_res_clusters": int(
                (clusters["building_type"].astype(str).str.upper() != "RES").sum()
            ),
            "derived_restricted_tasks": int(tasks["is_time_restricted"].astype(int).sum()),
        }
        for param, value in overrides.items():
            mask = config_df["param"].astype(str) == param
            if mask.any():
                config_df.loc[mask, "value"] = value
            else:
                config_df = pd.concat(
                    [config_df, pd.DataFrame([{"param": param, "value": value}])],
                    ignore_index=True,
                )
    readme_df = pd.concat(
        [
            build_readme(),
            pd.DataFrame(
                [
                    {"sheet": "GIS_VALIDATION", "description": "GIS coordinate, building anchor, snapping, connectivity, and road matrix checks."},
                    {"sheet": "ROAD_NETWORK", "description": "Road network metadata for the OSMnx graph."},
                    {"sheet": "BUILDINGS", "description": "Used OSM building anchors linked to maintenance tasks."},
                    {"sheet": "BUILDING_STATS", "description": "Summary of filtered and used OSM building anchors."},
                    {"sheet": "CAPACITY_RULES", "description": "Formal area/level capacity thresholds used by the generator."},
                    {"sheet": "ELEVATOR_DISTRIBUTION", "description": "Realized elevators-per-building distribution by controlled type."},
                ]
            ),
        ],
        ignore_index=True,
    )
    building_summary = pd.DataFrame(
        [
            {"metric": "n_building_candidates", "value": int(len(buildings))},
            {"metric": "min_area_m2", "value": float(buildings["area_m2"].min())},
            {"metric": "mean_area_m2", "value": float(buildings["area_m2"].mean())},
            {"metric": "max_area_m2", "value": float(buildings["area_m2"].max())},
            {"metric": "max_snap_distance_m", "value": float(buildings["snap_distance_m"].max())},
            {"metric": "n_used_buildings", "value": int(len(buildings_used))},
            {"metric": "mean_elevators_per_building", "value": float(buildings_used["n_tasks_assigned"].mean())},
            {"metric": "median_elevators_per_building", "value": float(buildings_used["n_tasks_assigned"].median())},
            {"metric": "max_tasks_per_building_observed", "value": int(buildings_used["n_tasks_assigned"].max())},
            {"metric": "capacity_area_cap_m2", "value": area_cap_m2},
            {"metric": "capacity_levels_observed", "value": int((buildings_used["capacity_data_quality"] == "levels_observed").sum())},
            {"metric": "capacity_height_derived", "value": int((buildings_used["capacity_data_quality"] == "height_derived").sum())},
            {"metric": "capacity_area_only", "value": int((buildings_used["capacity_data_quality"] == "area_only").sum())},
        ]
    )
    capacity_rule_rows = []
    for building_type, rule in BUILDING_CAPACITY_RULES.items():
        capacity_rule_rows.append(
            {
                "building_type": building_type,
                "area_breaks_m2": json.dumps(list(rule["area_breaks_m2"])),
                "area_counts": json.dumps(list(rule["area_counts"])),
                "level_breaks": json.dumps(list(rule["level_breaks"])),
                "level_counts": json.dumps(list(rule["level_counts"])),
                "max_count": int(rule["max_count"]),
                "rule_version": RULE_VERSION,
            }
        )
    capacity_rules_df = pd.DataFrame(capacity_rule_rows)
    elevator_distribution = (
        buildings_used.groupby(
            ["assigned_building_type", "n_tasks_assigned"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "n_buildings"})
    )

    xlsx_path = out_dir / "instance.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        nodes.to_excel(writer, sheet_name="NODES", index=False)
        clusters.to_excel(writer, sheet_name="CLUSTERS", index=False)
        techs.to_excel(writer, sheet_name="TECHNICIANS", index=False)
        tasks.to_excel(writer, sheet_name="TASKS", index=False)
        buildings_used.to_excel(writer, sheet_name="BUILDINGS", index=False)
        windows.to_excel(writer, sheet_name="TASK_WINDOWS", index=False)
        config_df.to_excel(writer, sheet_name="CONFIG", index=False)
        validation.to_excel(writer, sheet_name="VALIDATION", index=False)
        gis_validation.to_excel(writer, sheet_name="GIS_VALIDATION", index=False)
        road_meta.to_excel(writer, sheet_name="ROAD_NETWORK", index=False)
        building_summary.to_excel(writer, sheet_name="BUILDING_STATS", index=False)
        capacity_rules_df.to_excel(writer, sheet_name="CAPACITY_RULES", index=False)
        elevator_distribution.to_excel(writer, sheet_name="ELEVATOR_DISTRIBUTION", index=False)
        readme_df.to_excel(writer, sheet_name="README", index=False)

    write_city_assets = bool(cfg.get("write_city_assets_per_instance", not shared_assets))
    if write_city_assets:
        ox.save_graphml(G, filepath=out_dir / "road_network.graphml")
    write_geo_outputs(
        out_dir,
        G,
        nodes,
        clusters,
        buildings,
        building_candidates_sample_size=int(cfg.get("building_candidates_sample_size", 1000)),
        write_city_assets=write_city_assets,
    )
    plot_preview(out_dir, G, nodes, clusters, buildings, name)
    config_snapshot = dict(cfg)
    config_snapshot.update(
        {
            "cycle_days": int(DEFAULTS["cycle_days"]),
            "day1_weekday": int(DEFAULTS["day1_weekday"]),
            "service_min": float(DEFAULTS["service_min"]),
            "regular_work_min": int(DEFAULTS["regular_work_min"]),
            "max_work_min": int(DEFAULTS["max_work_min"]),
            "capacity_rule_version": RULE_VERSION,
            "capacity_rules": jsonable_rules(),
            "capacity_area_cap_m2": area_cap_m2,
            "building_selection_mode": "seeded_uniform_without_replacement",
            "max_tasks_per_building": max(
                int(rule["max_count"]) for rule in BUILDING_CAPACITY_RULES.values()
            ),
            "n_used_buildings": int(len(buildings_used)),
            "mean_elevators_per_building": float(
                buildings_used["n_tasks_assigned"].mean()
            ),
        }
    )
    with (out_dir / "config.json").open("w", encoding="utf-8") as f:
        json.dump(config_snapshot, f, ensure_ascii=False, indent=2)
    write_gis_b_instance_readme(
        out_dir,
        name,
        road_matrix_path.name,
        shared_assets=shared_assets,
    )

    return {
        "instance_name": name,
        "out_dir": str(out_dir),
        "n_tasks": int(len(tasks)),
        "n_clusters": int(len(clusters)),
        "n_building_candidates": int(len(buildings)),
        "n_unique_task_buildings": int(tasks["building_anchor_id"].nunique()),
        "max_tasks_per_building_observed": int(buildings_used["n_tasks_assigned"].max()),
        "n_road_nodes": int(G.number_of_nodes()),
        "n_road_edges": int(G.number_of_edges()),
        "road_matrix_rows": int(len(road_matrix)),
        "max_snap_distance_m": float(nodes["snap_distance_m"].max()),
        "gis_validation_status": "PASS" if bool(gis_validation.iloc[-1]["passed"]) else "FAIL",
        "runtime_sec": round(time.time() - t0, 3),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one GIS-B EMD prototype instance.")
    parser.add_argument("--config", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    row = generate(load_config(Path(args.config)))
    print(json.dumps(row, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
