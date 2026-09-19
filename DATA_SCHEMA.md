# GIS-B-ME data schema

[中文说明](DATA_SCHEMA.zh-CN.md)

## Instance files

| File | Meaning |
|---|---|
| instance.xlsx | Fourteen tables listed below |
| road_matrix.parquet | Complete directed node-to-node distance and time records |
| config.json | Resolved rules and instance statistics; shared paths relative to dataset root |
| README.md | Instance introduction |
| map_preview.png | Frozen road network and task locations, with OSM attribution |
| task_points.geojson | Elevator points **and depot**; filter node_type=ELEVATOR for tasks |
| clusters.geojson | Cluster geometries and attributes |
| used_buildings.geojson | Used building polygons |
| used_building_anchors.geojson | Used building representative points |

## Workbook tables

| Sheet | Unit of observation and content |
|---|---|
| NODES | One depot or elevator node; spatial coordinates and building attributes |
| CLUSTERS | One task cluster; center, size, spatial pattern and anchor |
| TECHNICIANS | One available technician, shift and capacity settings |
| TASKS | One 30-minute PM task; node and building references, business labels |
| BUILDINGS | One used building; capacity, assigned count, geometry-derived attributes |
| TASK_WINDOWS | One allowed task/day window |
| CONFIG | Key/value rules, paths and instance summaries |
| VALIDATION | Original generator checks |
| GIS_VALIDATION | Original GIS checks |
| ROAD_NETWORK | Shared network summary |
| BUILDING_STATS | Candidate building summary |
| CAPACITY_RULES | Controlled capacity estimation rules |
| ELEVATOR_DISTRIBUTION | Task allocation by building type |
| README | Workbook table descriptions |

## Keys and joins

- `task_id`: unique **within** an instance; repeated across instances. Cross-instance
  key: `(instance_id, task_id)`.
- `TASKS.task_id` → `TASK_WINDOWS.task_id` is one-to-many.
- `TASKS.node_id` → `NODES.node_id`; use node IDs in OD lookups. Depot ID is `S01`.
- `building_anchor_id`: frozen candidate ID, unique within a city. Use
  `(city_code, building_anchor_id)` across cities.
- `building_osm_id`: original `element_type/id` recovered from the frozen OSM cache.
  Use the identifier crosswalk for records produced before internal assembly revision v3.0.1.
- Same-building tasks share `osm_node_id` and access cost, but retain independent
  30-minute service requirements. Different buildings may share an access node.
- `building_type`/`assigned_building_type`: controlled benchmark labels.
  `osm_building_tag`: an OSM source attribute, not the controlled business label.
- `estimated_elevator_capacity` is a controlled upper bound; `n_tasks_assigned`
  is the realized allocation. Missing floor or height data are valid, with the
  fallback basis recorded by `capacity_data_quality`.

## Time and OD costs

`service_min` is 30. `day` is 1-based. `ready_time_min` is earliest start,
`due_time_min` is latest completion, and `latest_start_time_min=due_time_min-30`.
`window_count` counts available days, not independent tasks. All windows are hard.

| Parquet column | Type and meaning |
|---|---|
| from_node_id, to_node_id | String IDs from NODES, including depot |
| from_osm_node_id, to_osm_node_id | Integer road access node IDs |
| road_distance_m | Directed shortest-path distance in metres |
| road_time_sec | `road_distance_m / 250 * 60` |
| road_time_min | `road_distance_m / 250` (15 km/h) |
| routing_status | Route computation status |
| engine | Routing engine label |

Each matrix has `(N+1)^2` records, including diagonal zero-cost pairs. Do not
assume symmetry. Use explicit IDs to reshape rather than relying on row order.
GraphML `speed_kph`/`travel_time` are source-processing attributes; they are not
the standardized benchmark travel costs. Use Parquet `road_time_min` for experiments.
The config `speed_fallback_kmph` likewise is not the benchmark's fixed speed.

## Coordinates

GeoJSON geometry and `lon/lat` use longitude/latitude degrees in EPSG:4326.
`projected_x/projected_y` use metres: Beijing EPSG:32650, Shanghai EPSG:32651,
Chongqing EPSG:32648. GraphML uses its own recorded projected CRS.
`x_km/y_km` are local coordinates in kilometres:

```text
x_km = (projected_x - origin_easting_m) / 1000
y_km = (projected_y - origin_northing_m) / 1000
```

City-specific origins are recorded in `metadata/coordinate_systems.json`.
A row's `crs=EPSG:4326` describes geographic coordinates, not every numeric
coordinate column. Network node geometry, building representative points and
building access nodes serve different roles and need not coincide.

## Metadata and configuration scope

- `instance_manifest.csv`: 135 rows in Beijing, Shanghai, Chongqing order.
- `generation_configs/`: generation-input snapshots. `config.json` has the same
  shared fields plus 16 resolved-rule or statistical fields; the files are not
  intended to be identical schema copies.
- `frozen_parameters.json`: internal design v3 and assembly revision v3.1.0.
- `building_id_mapping.csv`: city, candidate anchor, legacy identifier and true OSM ID.
- `source_provenance.json`: frozen source timestamps and hashes, identity-match evidence.
- `MANIFEST.csv`: file inventory, byte size and package category.
- `CHECKSUMS.sha256`: standard SHA-256 list suitable for command-line tools.
- `checksums_sha256.csv`: the same checked file set with explicit byte sizes.
  The two checksum files exclude themselves to avoid circular digests.

Paths in JSON `output_root`, `shared_road_network_path`,
`shared_building_candidates_path` and workbook `CONFIG.road_network_file` resolve
from the dataset root. `CONFIG.road_matrix_file` resolves within the instance.

The package includes the generator source, frozen inputs, configuration
snapshots and canonical comparison tool under `code/generator/`. The retained
full audit in `validation/generator_reproducibility/` reports 135/135 canonical
reproductions passed. Container timestamps, regenerated PNG bytes and
release-authored README text are excluded from canonical data comparison.
