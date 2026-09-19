# GIS-B-ME data dictionary

This dictionary describes public join keys, units and reference-result fields.
The complete workbook and OD schema is documented in `DATA_SCHEMA.md`.

## Dataset-level identifiers

| Field | Meaning |
|---|---|
| `instance_id` / `instance_name` | Unique family-city-pattern-scale-seed identifier |
| `city_id` / `city_code` | `BJS`, `SHA` or `CKG` |
| `cluster_pattern` | `CU` relatively uniform, `CH` heterogeneous cluster sizes, `CZ` regionally concentrated |
| `scale` | Number of PM tasks: 100, 500 or 1000 |
| `seed` / `instance_seed` | Instance seed: 12, 34, 56, 78 or 90 |
| `task_id` | Task identifier unique within one instance |
| `node_id` | Instance-local task/depot node; depot is `S01` |
| `building_anchor_id` | Frozen candidate-building identifier unique within a city |
| `building_osm_id` | Original OSM `element_type/id` |

Use `(instance_id, task_id)` across instances and
`(city_id, building_anchor_id)` across cities.

## Tasks and calendars

| Field | Unit/type | Meaning |
|---|---|---|
| `service_min` | minutes | On-site service; fixed at 30 |
| `building_type` | category | Controlled `RES`, `OFF`, `COM` or `SCH` label |
| `day` | integer | Allowed service day, 1–15; day 1 is Monday |
| `ready_time_min` | minutes | Earliest service start |
| `due_time_min` | minutes | Latest service completion |
| `latest_start_time_min` | minutes | `due_time_min - service_min` |
| `window_count` | count | Number of allowed service days |
| `estimated_elevator_capacity` | count | Controlled building capacity upper bound |
| `n_tasks_assigned` | count | Tasks assigned to the building in this instance |

## Directed OD matrix

| Field | Unit/type | Meaning |
|---|---|---|
| `from_node_id`, `to_node_id` | string | Directed instance-node pair, including depot |
| `from_osm_node_id`, `to_osm_node_id` | integer | Road access-node identifiers |
| `road_distance_m` | metres | Directed shortest-road distance |
| `road_time_sec` | seconds | Distance converted at 15 km/h |
| `road_time_min` | minutes | `road_distance_m / 250` |
| `routing_status` | string | Route-computation status |
| `engine` | string | Matrix-generation method label |

## Reference-results table

| Field | Meaning |
|---|---|
| `lower_bound` | Valid lower bound on minimum technician count |
| `upper_bound` | Technician count of a validated feasible solution |
| `gap` | `upper_bound - lower_bound` |
| `status` | `K-OPT` when gap is zero; otherwise `K-OPEN` |
| `bks_technicians` | Technician component of the BKS pair; equals upper bound |
| `bks_travel_time_min` | Best-known travel at that workforce, using the released OD matrix |
| `bks_waiting_time_min` | Total waiting in the published schedule |
| `method` | Method label explained in `reference_results/README.md` |
| `run_seed` | Selected algorithm seed; empty for multi-source recombination |
| `source_run_seeds` | All contributing run seeds |
| `validator_status` | Independent feasibility result |
| `solution_file` | Path relative to `reference_results/` |
| `solution_sha256` | SHA-256 of the solution CSV |
| `dataset_release` | Public release identifier |
| `source_reference_batch` | Preserved internal source-batch identifier |

## Solution files

| Field | Unit/type | Meaning |
|---|---|---|
| `technician_id` | string | Assigned technician |
| `day` | integer | Service day |
| `route_order` | integer | Consecutive order within a technician-day route |
| `task_id` | string | Served task |
| `arrival_time` | minutes | Arrival from day start |
| `start_time` | minutes | Service start |
| `finish_time` | minutes | Service completion |
| `travel_time_from_prev` | minutes | Depot/previous-task travel to current task |
| `waiting_time` | minutes | `start_time - arrival_time` |
| `service_time` | minutes | Task service time |
| `route_travel_time` | minutes | Complete travel including final depot return |
| `route_duration` | minutes | Complete depot-to-depot daily duration |

The final return-to-depot leg has no separate task row. It is included in
`route_travel_time` and `route_duration`.
