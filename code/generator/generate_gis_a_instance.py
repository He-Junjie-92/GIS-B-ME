# -*- coding: utf-8 -*-
"""Generate one GIS-A EMD benchmark prototype instance.

GIS-A keeps the controllable synthetic cluster/task/time-window logic from the
standard EMD generator, but maps the generated points onto a real OSM road
network and builds a road-network travel-time matrix.
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
if str(BENCHMARK_SRC) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_SRC))

from EMD_Benchmark_Generator_v3 import (  # noqa: E402
    DEFAULTS,
    build_config,
    build_readme,
    build_task_windows,
    build_technicians,
    estimate_technician_pool,
    generate_clusters,
    generate_nodes_and_tasks,
    validate_instance,
)


def load_config(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def bbox_tuple(cfg: Dict[str, object]) -> Tuple[float, float, float, float]:
    bbox = cfg["bbox"]
    return (
        float(bbox["west"]),
        float(bbox["south"]),
        float(bbox["east"]),
        float(bbox["north"]),
    )


def instance_name(cfg: Dict[str, object]) -> str:
    return "GISEMD-{city}-{pattern}-{scale}-{tw}-{seed:03d}".format(
        city=str(cfg["city_id"]).upper(),
        pattern=str(cfg["cluster_pattern"]).upper(),
        scale=int(cfg["scale"]),
        tw=str(cfg["tw_scenario"]).upper(),
        seed=int(cfg["seed"]),
    )


def graph_bounds_projected(G: nx.MultiDiGraph) -> Tuple[float, float, float, float]:
    xs = np.array([float(data["x"]) for _, data in G.nodes(data=True)])
    ys = np.array([float(data["y"]) for _, data in G.nodes(data=True)])
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def local_square(bounds: Tuple[float, float, float, float]) -> Tuple[float, float, float]:
    minx, miny, maxx, maxy = bounds
    width = maxx - minx
    height = maxy - miny
    side = min(width, height)
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    x0 = cx - side / 2.0
    y0 = cy - side / 2.0
    return x0, y0, side


def local_to_projected(x_km: float, y_km: float, x0: float, y0: float) -> Tuple[float, float]:
    return x0 + float(x_km) * 1000.0, y0 + float(y_km) * 1000.0


def projected_to_local(x: float, y: float, x0: float, y0: float) -> Tuple[float, float]:
    return (float(x) - x0) / 1000.0, (float(y) - y0) / 1000.0


HIGHWAY_PRIORITY = {
    "motorway": 0,
    "motorway_link": 1,
    "trunk": 2,
    "trunk_link": 3,
    "primary": 4,
    "primary_link": 5,
    "secondary": 6,
    "secondary_link": 7,
    "tertiary": 8,
    "tertiary_link": 9,
    "unclassified": 10,
    "residential": 11,
    "living_street": 12,
    "service": 13,
}


def canonicalize_highway_values(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Make simplified multi-value highway tags deterministic before speed imputation."""
    for _, _, _, data in G.edges(keys=True, data=True):
        highway = data.get("highway")
        if isinstance(highway, list):
            values = [str(value) for value in highway]
            data["highway"] = sorted(
                values,
                key=lambda value: (HIGHWAY_PRIORITY.get(value, 100), value),
            )
    return G


def prepare_graph(cfg: Dict[str, object]) -> nx.MultiDiGraph:
    ox.settings.use_cache = True
    ox.settings.log_console = False
    ox.settings.timeout = 180
    G = ox.graph_from_bbox(
        bbox_tuple(cfg),
        network_type=str(cfg.get("network_type", "drive")),
        simplify=True,
        retain_all=False,
        truncate_by_edge=True,
    )
    G = canonicalize_highway_values(G)
    G = ox.routing.add_edge_speeds(G, fallback=float(cfg.get("speed_fallback_kmph", 30.0)))
    G = ox.routing.add_edge_travel_times(G)
    if not nx.is_strongly_connected(G):
        largest_scc = max(nx.strongly_connected_components(G), key=len)
        G = G.subgraph(largest_scc).copy()
    return ox.project_graph(G)


def snap_dataframe(
    df: pd.DataFrame,
    G: nx.MultiDiGraph,
    transformer: Transformer,
    x0: float,
    y0: float,
    id_col: str,
    clusters: pd.DataFrame | None = None,
    rng: np.random.Generator | None = None,
    max_snap_distance_m: float = 150.0,
) -> pd.DataFrame:
    out = df.copy()
    road_node_ids = np.array([int(nid) for nid in G.nodes()], dtype=np.int64)
    road_xy = np.array([[float(G.nodes[int(nid)]["x"]), float(G.nodes[int(nid)]["y"])] for nid in road_node_ids], dtype=float)
    tree = cKDTree(road_xy)
    cluster_lookup = clusters.set_index("cluster_id").to_dict("index") if clusters is not None else {}
    rng = rng or np.random.default_rng(0)

    osm_ids: List[int] = []
    snap_distances: List[float] = []
    pre_resample_distances: List[float] = []
    resampled_flags: List[int] = []
    lons: List[float] = []
    lats: List[float] = []
    snapped_xs: List[float] = []
    snapped_ys: List[float] = []
    local_xs: List[float] = []
    local_ys: List[float] = []

    for _, row in out.iterrows():
        px, py = local_to_projected(float(row["x_km"]), float(row["y_km"]), x0, y0)
        osm_id, snap_dist = ox.distance.nearest_nodes(G, px, py, return_dist=True)
        osm_id = int(osm_id)
        selected_osm_id = osm_id
        selected_snap_dist = float(snap_dist)
        pre_resample_snap_dist = float(snap_dist)
        resampled = 0

        if float(snap_dist) > float(max_snap_distance_m):
            node_type = str(row.get("node_type", "")).upper()
            cid = str(row.get("cluster_id", ""))
            if node_type == "ELEVATOR" and cid in cluster_lookup:
                c = cluster_lookup[cid]
                center = np.array([float(c["center_projected_x"]), float(c["center_projected_y"])], dtype=float)
                radius = max(float(c.get("cluster_radius_km", 0.2)) * 1000.0 * 2.0, float(max_snap_distance_m))
                candidates = tree.query_ball_point(center, r=radius)
                while not candidates and radius < 1500.0:
                    radius *= 1.5
                    candidates = tree.query_ball_point(center, r=radius)
                if candidates:
                    # Pick the candidate closest to the synthetic point to keep
                    # the generated spatial pattern as much as possible.
                    cand_xy = road_xy[candidates]
                    nearest_idx = int(np.argmin(np.linalg.norm(cand_xy - np.array([px, py]), axis=1)))
                    selected_osm_id = int(road_node_ids[candidates[nearest_idx]])
                else:
                    selected_osm_id = osm_id
            else:
                selected_osm_id = osm_id
            selected_snap_dist = 0.0
            resampled = 1

        osm_id = selected_osm_id
        node = G.nodes[osm_id]
        sx = float(node["x"])
        sy = float(node["y"])
        lon, lat = transformer.transform(sx, sy)
        lx, ly = projected_to_local(sx, sy, x0, y0)
        osm_ids.append(osm_id)
        snap_distances.append(float(selected_snap_dist))
        lons.append(float(lon))
        lats.append(float(lat))
        snapped_xs.append(sx)
        snapped_ys.append(sy)
        local_xs.append(lx)
        local_ys.append(ly)
        pre_resample_distances.append(pre_resample_snap_dist)
        resampled_flags.append(resampled)

    out["x_km_original"] = out["x_km"].astype(float)
    out["y_km_original"] = out["y_km"].astype(float)
    out["x_km"] = local_xs
    out["y_km"] = local_ys
    out["lon"] = lons
    out["lat"] = lats
    out["osm_node_id"] = osm_ids
    out["snap_distance_m"] = snap_distances
    out["pre_resample_snap_distance_m"] = pre_resample_distances
    out["resampled_to_road_node"] = resampled_flags
    out["projected_x"] = snapped_xs
    out["projected_y"] = snapped_ys
    out["gis_source"] = "OSM"
    out["crs"] = "EPSG:4326"
    return out


def snap_clusters(
    clusters: pd.DataFrame,
    G: nx.MultiDiGraph,
    transformer: Transformer,
    x0: float,
    y0: float,
) -> pd.DataFrame:
    out = clusters.copy()
    rows = []
    for _, row in out.iterrows():
        px, py = local_to_projected(float(row["center_x_km"]), float(row["center_y_km"]), x0, y0)
        osm_id, snap_dist = ox.distance.nearest_nodes(G, px, py, return_dist=True)
        osm_id = int(osm_id)
        node = G.nodes[osm_id]
        sx = float(node["x"])
        sy = float(node["y"])
        lon, lat = transformer.transform(sx, sy)
        lx, ly = projected_to_local(sx, sy, x0, y0)
        rows.append((osm_id, snap_dist, lon, lat, sx, sy, lx, ly))

    out["center_x_km_original"] = out["center_x_km"].astype(float)
    out["center_y_km_original"] = out["center_y_km"].astype(float)
    out["center_osm_node_id"] = [r[0] for r in rows]
    out["center_snap_distance_m"] = [float(r[1]) for r in rows]
    out["center_lon"] = [float(r[2]) for r in rows]
    out["center_lat"] = [float(r[3]) for r in rows]
    out["center_projected_x"] = [float(r[4]) for r in rows]
    out["center_projected_y"] = [float(r[5]) for r in rows]
    out["center_x_km"] = [float(r[6]) for r in rows]
    out["center_y_km"] = [float(r[7]) for r in rows]
    out["source_mode"] = "synthetic_on_gis"
    out["urban_zone"] = out.get("zone_id", 0)
    return out


def build_road_network_metadata(G: nx.MultiDiGraph, cfg: Dict[str, object]) -> pd.DataFrame:
    edge_lengths = [float(data.get("length", 0.0)) for _, _, _, data in G.edges(keys=True, data=True)]
    edge_speeds = [float(data.get("speed_kph", 0.0)) for _, _, _, data in G.edges(keys=True, data=True)]
    rows = [
        {"metric": "n_road_nodes", "value": int(G.number_of_nodes())},
        {"metric": "n_road_edges", "value": int(G.number_of_edges())},
        {"metric": "total_edge_length_km", "value": float(sum(edge_lengths) / 1000.0)},
        {"metric": "avg_edge_speed_kmph", "value": float(np.mean(edge_speeds)) if edge_speeds else 0.0},
        {"metric": "connected_component", "value": "largest_component_retained"},
        {"metric": "network_type", "value": str(cfg.get("network_type", "drive"))},
        {"metric": "routing_engine", "value": str(cfg.get("routing_engine", "osmnx"))},
    ]
    return pd.DataFrame(rows)


def build_road_matrix(nodes_df: pd.DataFrame, G: nx.MultiDiGraph) -> pd.DataFrame:
    nodes = nodes_df[["node_id", "osm_node_id"]].copy()
    nodes["node_id"] = nodes["node_id"].astype(str)
    nodes["osm_node_id"] = nodes["osm_node_id"].astype(int)
    unique_osm = sorted(nodes["osm_node_id"].unique().tolist())

    time_lengths: Dict[int, Dict[int, float]] = {}
    dist_lengths: Dict[int, Dict[int, float]] = {}
    for source in unique_osm:
        time_lengths[source] = nx.single_source_dijkstra_path_length(G, source, weight="travel_time")
        dist_lengths[source] = nx.single_source_dijkstra_path_length(G, source, weight="length")

    rows: List[dict] = []
    records = nodes.to_dict("records")
    for a in records:
        source_osm = int(a["osm_node_id"])
        for b in records:
            target_osm = int(b["osm_node_id"])
            if target_osm in time_lengths[source_osm] and target_osm in dist_lengths[source_osm]:
                rows.append(
                    {
                        "from_node_id": str(a["node_id"]),
                        "to_node_id": str(b["node_id"]),
                        "from_osm_node_id": source_osm,
                        "to_osm_node_id": target_osm,
                        "road_distance_m": float(dist_lengths[source_osm][target_osm]),
                        "road_time_sec": float(time_lengths[source_osm][target_osm]),
                        "road_time_min": float(time_lengths[source_osm][target_osm] / 60.0),
                        "routing_status": "ok",
                        "engine": "osmnx",
                    }
                )
            else:
                rows.append(
                    {
                        "from_node_id": str(a["node_id"]),
                        "to_node_id": str(b["node_id"]),
                        "from_osm_node_id": source_osm,
                        "to_osm_node_id": target_osm,
                        "road_distance_m": math.nan,
                        "road_time_sec": math.nan,
                        "road_time_min": math.nan,
                        "routing_status": "no_path",
                        "engine": "osmnx",
                    }
                )
    return pd.DataFrame(rows)


def build_gis_validation(
    nodes: pd.DataFrame,
    road_matrix: pd.DataFrame,
    cfg: Dict[str, object],
    G: nx.MultiDiGraph,
) -> pd.DataFrame:
    checks: List[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    west, south, east, north = bbox_tuple(cfg)
    tol = float(cfg.get("bbox_tolerance_deg", 0.001))
    add("lon_within_bbox", bool(nodes["lon"].between(west - tol, east + tol).all()), f"tolerance_deg={tol}")
    add("lat_within_bbox", bool(nodes["lat"].between(south - tol, north + tol).all()), f"tolerance_deg={tol}")
    add("all_nodes_snapped", bool(nodes["osm_node_id"].notna().all()), "")
    max_snap = float(nodes["snap_distance_m"].max()) if len(nodes) else 0.0
    threshold = float(cfg.get("max_snap_distance_m", 150.0))
    add("snap_distance_within_threshold", max_snap <= threshold, f"max_snap_distance_m={max_snap:.3f}, threshold={threshold:.3f}")
    add("road_graph_nonempty", G.number_of_nodes() > 0 and G.number_of_edges() > 0, f"nodes={G.number_of_nodes()}, edges={G.number_of_edges()}")
    add("matrix_size", len(road_matrix) == len(nodes) * len(nodes), f"expected={len(nodes) * len(nodes)}, actual={len(road_matrix)}")
    add("matrix_no_path_absent", bool((road_matrix["routing_status"] == "ok").all()), "")
    add("matrix_time_nonnegative", bool((road_matrix["road_time_sec"].dropna() >= 0).all()), "")
    add("matrix_distance_nonnegative", bool((road_matrix["road_distance_m"].dropna() >= 0).all()), "")
    self_rows = road_matrix[road_matrix["from_node_id"] == road_matrix["to_node_id"]]
    add("matrix_diagonal_zero", bool((self_rows["road_time_sec"].abs() <= 1e-9).all() and (self_rows["road_distance_m"].abs() <= 1e-9).all()), "")
    status = all(row["passed"] for row in checks)
    checks.append({"check": "gis_overall_status", "passed": status, "detail": "PASS" if status else "FAIL"})
    return pd.DataFrame(checks)


def write_geo_outputs(
    out_dir: Path,
    G: nx.MultiDiGraph,
    nodes: pd.DataFrame,
    clusters: pd.DataFrame,
) -> None:
    road_nodes, road_edges = ox.graph_to_gdfs(G, nodes=True, edges=True)
    road_nodes.to_crs("EPSG:4326").to_file(out_dir / "road_nodes.geojson", driver="GeoJSON")
    road_edges.to_crs("EPSG:4326").to_file(out_dir / "road_edges.geojson", driver="GeoJSON")

    task_gdf = gpd.GeoDataFrame(
        nodes.copy(),
        geometry=[Point(xy) for xy in zip(nodes["lon"], nodes["lat"])],
        crs="EPSG:4326",
    )
    task_gdf.to_file(out_dir / "task_points.geojson", driver="GeoJSON")

    cluster_gdf = gpd.GeoDataFrame(
        clusters.copy(),
        geometry=[Point(xy) for xy in zip(clusters["center_lon"], clusters["center_lat"])],
        crs="EPSG:4326",
    )
    cluster_gdf.to_file(out_dir / "clusters.geojson", driver="GeoJSON")


def plot_preview(out_dir: Path, G: nx.MultiDiGraph, nodes: pd.DataFrame, clusters: pd.DataFrame, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _, ax = ox.plot_graph(
        G,
        show=False,
        close=False,
        node_size=0,
        edge_color="#bbbbbb",
        edge_linewidth=0.45,
        bgcolor="white",
    )
    elev = nodes[nodes["node_type"].astype(str).str.upper() == "ELEVATOR"]
    station = nodes[nodes["node_type"].astype(str).str.upper() == "STATION"]
    colors = {"RES": "#4C78A8", "OFF": "#F58518", "COM": "#54A24B", "SCH": "#B279A2"}
    for btype, sub in elev.groupby("building_type"):
        ax.scatter(sub["projected_x"], sub["projected_y"], s=8, label=str(btype), color=colors.get(str(btype), "#777777"), alpha=0.75)
    ax.scatter(station["projected_x"], station["projected_y"], s=90, marker="X", label="STATION", color="#D62728")
    restricted = clusters[clusters["is_time_restricted"].astype(int) == 1]
    if len(restricted):
        ax.scatter(restricted["center_projected_x"], restricted["center_projected_y"], s=35, marker="+", label="restricted cluster", color="#7F3C8D")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=7)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_dir / "map_preview.png", dpi=220)
    plt.close()


def write_instance_readme(out_dir: Path, name: str, matrix_filename: str) -> None:
    text = f"""# {name}

GIS-A prototype instance.

Files:

- `instance.xlsx`: EMD instance tables with GIS fields.
- `{matrix_filename}`: full road-network OD matrix.
- `road_network.graphml`: projected OSM road graph.
- `road_nodes.geojson`, `road_edges.geojson`: road network layers.
- `task_points.geojson`: station and elevator task points.
- `clusters.geojson`: synthetic building cluster centers on GIS network.
- `map_preview.png`: road network and task preview.
- `config.json`: generation config snapshot.

The travel-time matrix uses OSMnx/NetworkX shortest paths over edge
`travel_time` in seconds.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def generate(cfg: Dict[str, object]) -> Dict[str, object]:
    t0 = time.time()
    name = instance_name(cfg)
    out_root = Path(str(cfg["output_root"]))
    out_dir = out_root / name
    out_dir.mkdir(parents=True, exist_ok=True)

    G = prepare_graph(cfg)
    bounds = graph_bounds_projected(G)
    x0, y0, side_m = local_square(bounds)
    map_size_km = side_m / 1000.0
    transformer = Transformer.from_crs(G.graph["crs"], "EPSG:4326", always_xy=True)

    rng = np.random.default_rng(int(cfg["seed"]))
    clusters = generate_clusters(
        rng=rng,
        n_elevators=int(cfg["scale"]),
        n_clusters=None,
        cluster_pattern=str(cfg["cluster_pattern"]).upper(),
        tw_scenario=str(cfg["tw_scenario"]).upper(),
        map_size=float(map_size_km),
        building_type_ratios=str(DEFAULTS["building_type_ratios"]),
        cluster_size_min=int(DEFAULTS["cluster_size_min"]),
        cluster_size_max=int(DEFAULTS["cluster_size_max"]),
        cluster_size_target=int(DEFAULTS["cluster_size_target"]),
        cluster_radius_min=float(DEFAULTS["cluster_radius_min"]),
        cluster_radius_max=float(DEFAULTS["cluster_radius_max"]),
        zonal_zone_count=int(DEFAULTS["zonal_zone_count"]),
        zonal_zone_radius=min(float(DEFAULTS["zonal_zone_radius"]), max(0.5, map_size_km / 4.0)),
        service_min=float(DEFAULTS["service_min"]),
    )
    clusters = snap_clusters(clusters, G, transformer, x0, y0)
    nodes, tasks_raw = generate_nodes_and_tasks(
        rng=rng,
        clusters_df=clusters,
        station_id=str(DEFAULTS["station_id"]),
        map_size=float(map_size_km),
        service_min=float(DEFAULTS["service_min"]),
    )

    nodes = snap_dataframe(
        nodes,
        G,
        transformer,
        x0,
        y0,
        id_col="node_id",
        clusters=clusters,
        rng=rng,
        max_snap_distance_m=float(cfg.get("max_snap_distance_m", 150.0)),
    )
    tasks_raw = tasks_raw.drop(columns=["x_km", "y_km"], errors="ignore").merge(
        nodes[["node_id", "x_km", "y_km", "lon", "lat", "osm_node_id", "snap_distance_m", "projected_x", "projected_y"]],
        on="node_id",
        how="left",
    )
    nodes["city_id"] = str(cfg["city_id"]).upper()
    tasks_raw["city_id"] = str(cfg["city_id"]).upper()
    clusters["city_id"] = str(cfg["city_id"]).upper()

    tasks, windows = build_task_windows(
        tasks_df=tasks_raw,
        cycle_days=int(DEFAULTS["cycle_days"]),
        day1_weekday=int(DEFAULTS["day1_weekday"]),
        service_min=float(DEFAULTS["service_min"]),
        tw_policy=str(DEFAULTS["tw_policy"]),
    )
    n_pool, tech_stats = estimate_technician_pool(
        tasks_df=tasks,
        windows_df=windows,
        cycle_days=int(DEFAULTS["cycle_days"]),
        regular_work_min=int(DEFAULTS["regular_work_min"]),
        service_min=float(DEFAULTS["service_min"]),
        technician_pool_factor=float(DEFAULTS["technician_pool_factor"]),
        technician_pool_buffer=int(DEFAULTS["technician_pool_buffer"]),
    )
    techs = build_technicians(
        n_technicians_max=n_pool,
        station_id=str(DEFAULTS["station_id"]),
        speed_kmph=float(DEFAULTS["speed_kmph"]),
        shift_start_min=int(DEFAULTS["shift_start_min"]),
        shift_end_min=int(DEFAULTS["shift_end_min"]),
        regular_work_min=int(DEFAULTS["regular_work_min"]),
        max_work_min=int(DEFAULTS["max_work_min"]),
    )

    road_matrix = build_road_matrix(nodes, G)
    road_meta = build_road_network_metadata(G, cfg)
    validation = validate_instance(nodes, clusters, techs, tasks, windows, service_min=float(DEFAULTS["service_min"]))
    gis_validation = build_gis_validation(nodes, road_matrix, cfg, G)

    params = {
        "instance_name": name,
        "benchmark_stage": "GIS-A",
        "city_id": str(cfg["city_id"]).upper(),
        "city_name": str(cfg["city_name"]),
        "bbox_west_south_east_north": json.dumps(cfg["bbox"], ensure_ascii=False),
        "osm_data_date": str(date.today()),
        "network_type": str(cfg.get("network_type", "drive")),
        "routing_engine": "osmnx",
        "source_mode": "synthetic_on_gis",
        "distance_metric": "road_network_time",
        "matrix_unit_distance": "meter",
        "matrix_unit_time": "second",
        "snap_method": "nearest_node",
        "max_snap_distance_m": float(cfg.get("max_snap_distance_m", 150.0)),
        "map_size": float(map_size_km),
        "n_elevators": int(cfg["scale"]),
        "n_clusters": int(len(clusters)),
        "cluster_pattern": str(cfg["cluster_pattern"]).upper(),
        "tw_scenario": str(cfg["tw_scenario"]).upper(),
        "seed": int(cfg["seed"]),
        "station_count": 1,
        "station_location": "snapped_city_center",
        "cycle_days": int(DEFAULTS["cycle_days"]),
        "day1_weekday": int(DEFAULTS["day1_weekday"]),
        "shift_start_min": int(DEFAULTS["shift_start_min"]),
        "shift_end_min": int(DEFAULTS["shift_end_min"]),
        "regular_work_min": int(DEFAULTS["regular_work_min"]),
        "max_work_min": int(DEFAULTS["max_work_min"]),
        "allow_overtime": bool(DEFAULTS["allow_overtime"]),
        "service_min": float(DEFAULTS["service_min"]),
        "speed_kmph": float(DEFAULTS["speed_kmph"]),
        "building_type_ratios": str(DEFAULTS["building_type_ratios"]),
        "technician_mode": "candidate_pool_minimize_used_technicians",
        "road_network_file": "road_network.graphml",
    }
    road_matrix_path = write_road_matrix(road_matrix, out_dir)
    params["road_matrix_file"] = road_matrix_path.name
    config_df = build_config(params, clusters, tasks, windows, tech_stats)
    readme_df = build_readme()
    readme_df = pd.concat(
        [
            readme_df,
            pd.DataFrame(
                [
                    {"sheet": "GIS_VALIDATION", "description": "GIS coordinate, snapping, connectivity, and road matrix checks."},
                    {"sheet": "ROAD_NETWORK", "description": "Road network metadata for the OSMnx graph."},
                ]
            ),
        ],
        ignore_index=True,
    )

    xlsx_path = out_dir / "instance.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        nodes.to_excel(writer, sheet_name="NODES", index=False)
        clusters.to_excel(writer, sheet_name="CLUSTERS", index=False)
        techs.to_excel(writer, sheet_name="TECHNICIANS", index=False)
        tasks.to_excel(writer, sheet_name="TASKS", index=False)
        windows.to_excel(writer, sheet_name="TASK_WINDOWS", index=False)
        config_df.to_excel(writer, sheet_name="CONFIG", index=False)
        validation.to_excel(writer, sheet_name="VALIDATION", index=False)
        gis_validation.to_excel(writer, sheet_name="GIS_VALIDATION", index=False)
        road_meta.to_excel(writer, sheet_name="ROAD_NETWORK", index=False)
        readme_df.to_excel(writer, sheet_name="README", index=False)

    ox.save_graphml(G, filepath=out_dir / "road_network.graphml")
    write_geo_outputs(out_dir, G, nodes, clusters)
    plot_preview(out_dir, G, nodes, clusters, title=name)
    with (out_dir / "config.json").open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    write_instance_readme(out_dir, name, road_matrix_path.name)

    return {
        "instance_name": name,
        "out_dir": str(out_dir),
        "n_tasks": int(len(tasks)),
        "n_nodes": int(len(nodes)),
        "n_road_nodes": int(G.number_of_nodes()),
        "n_road_edges": int(G.number_of_edges()),
        "road_matrix_rows": int(len(road_matrix)),
        "max_snap_distance_m": float(nodes["snap_distance_m"].max()),
        "gis_validation_status": "PASS" if bool(gis_validation.iloc[-1]["passed"]) else "FAIL",
        "runtime_sec": round(time.time() - t0, 3),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one GIS-A EMD prototype instance.")
    parser.add_argument("--config", required=True, help="Path to GIS-A JSON config.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))
    row = generate(cfg)
    print(json.dumps(row, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
