# GIS-B-ME: A Semi-Synthetic Benchmark for Elevator Preventive Maintenance Scheduling on Real-World Urban Road Networks

**Public dataset release v1.0: 135 instances and 72,000 tasks.** The frozen
instance design is internally identified as design v3 / assembly revision v3.1.0.

[中文说明](README.zh-CN.md) · [Data dictionary](DATA_DICTIONARY.md) · [Usage](USAGE.md) · [License](LICENSE.md)

## Download

- Official repository: `https://github.com/He-Junjie-92/GIS-B-ME`
- Official v1.0 release: `https://github.com/He-Junjie-92/GIS-B-ME/releases/tag/v1.0`
- Complete benchmark archive: `GIS-B-ME-v1.0.zip`
- Checksum: `GIS-B-ME-v1.0.zip.sha256`

GitHub automatically generated **Source code (zip)** and **Source code
(tar.gz)** files do **not** contain the complete benchmark. Download the
attached `GIS-B-ME-v1.0.zip` release asset for the 135 instances, OD matrices
and validated BKS schedules.

GIS-B-ME is a semi-synthetic benchmark. Real-world geographic information is
used as the spatial foundation, whereas maintenance tasks and associated
business attributes are generated according to controlled benchmark rules.
GIS-B-ME is not an elevator registry or an operational maintenance database.
The presence of a benchmark task at a geographic location does not verify the
existence, ownership, status, technical condition or maintenance history of an
actual elevator at that location. City labels indicate geographic study areas
only.

## Experimental design

| Factor | Levels |
|---|---|
| City | Beijing (BJS), Shanghai (SHA), Chongqing (CKG) |
| Tasks per instance | 100, 500, 1000 |
| Spatial pattern | CU: relatively uniform coverage; CH: heterogeneous cluster sizes; CZ: regional concentration |
| Instance seed | 12, 34, 56, 78, 90 |

There are five instances in each city × size × pattern cell. Each task size has
45 instances, contributing 4,500, 22,500 and 45,000 tasks respectively. Task count
means elevator PM tasks, not buildings. CU and CH primarily differ in cluster-size
heterogeneity; CZ does not guarantee three equally populated concentration zones.

| City | Study area (km²) | Road nodes | Directed edges | Frozen building candidates |
|---|---:|---:|---:|---:|
| Beijing | 205.10 | 10,193 | 22,733 | 1,000 |
| Shanghai | 202.82 | 7,687 | 18,283 | 1,000 |
| Chongqing | 193.35 | 8,134 | 15,805 | 1,000 |

The per-city candidate pools use an exact RES/OFF/COM/SCH allocation of
740/120/80/60 with 10×10 spatial strata. This is a candidate-building design ratio,
not a requirement that task proportions equal those values.

## Scheduling rules

- 15 days, with day 1 a Monday. Weekdays: 1–5, 8–12, 15. Weekends: 6, 7, 13, 14.
- One 30-minute service task per elevator. Each task must be completed exactly once.
- Homogeneous technicians; single depot; departure and return on the same day.
- Maximum daily duration 480 minutes, including service, travel and waiting. No overtime.
- Directed shortest-road-distance costs converted at a constant **15 km/h**.
- Same-building tasks share an access node. Revisiting a building is permitted.
- Personnel count has priority; travel is compared at the same personnel count.
- Candidate personnel pool sizes are 5/10/15 for 100/500/1000 tasks. They are upper
  limits on available staff, not required or proven optimal staff counts.

| Controlled building type | Available days | Service window (minutes) |
|---|---|---|
| RES | All 15 days | 0–480 |
| OFF | Weekdays | 120–360 |
| COM | Weekdays | 0–480 |
| SCH | Weekends | 0–480 |

Window upper bounds are **latest completion times**. All windows are hard.
There is no time-window scenario factor. Waiting time and workload statistics
must not be interpreted as separately proven global optima.

## Descriptive statistics and aggregation

Across 135 equally weighted instances, the mean task proportions for
RES/OFF/COM/SCH are 72.6756/13.1830/8.6807/5.4607%. The mean number of tasks per
used building is 2.3631; the mean share of multi-task buildings is 73.5631%.

Pooling all records instead gives 52,517/9,302/6,228/3,953 tasks by type, or
72.9403/12.9194/8.6500/5.4903%. There are 30,599 instance-level used-building records,
of which 22,364 contain multiple tasks (73.0874%). The pooled average is 2.3530
tasks per building record. Buildings shared across instances are counted repeatedly.

## Reference results

The release reports K-OPT = 77, K-OPEN = 58, Gap1 = 40 and Gap2 = 18. `K-OPT`
means that the validated technician upper bound equals a valid personnel lower
bound; `K-OPEN` means that a personnel gap remains. A BKS is the best-known
reference result at its published technician count and does not imply global
optimality unless explicitly proved. Route-pool recombination results are
optimal within the finite candidate route pool, not global optima of the
original scheduling problem.

## GitHub Repository Layout

```text
GIS-B-ME/
├── .gitignore
├── README.md
├── README.zh-CN.md
├── LICENSE.md
├── OSM_ATTRIBUTION.md
├── CITATION.cff
├── CITATION.md
├── DATA_SCHEMA.md
├── DATA_SCHEMA.zh-CN.md
├── DATA_DICTIONARY.md
├── USAGE.md
├── LIMITATIONS.md
├── CHANGELOG.md
├── code/
├── configs/
├── environment/
├── metadata/
├── reference_results/
└── validation/
```

This is the lightweight repository obtained by `git clone`. It contains code,
configurations, documentation and compact validation/reference summaries. It
does not contain the benchmark instances, OD matrices or BKS schedule files.

## Complete Release Archive Layout

The following structure refers to the complete `GIS-B-ME-v1.0.zip` distributed
as an asset of the official GitHub v1.0 Release.

```text
GIS-B-ME-v1.0/
├── README.md, README.zh-CN.md, DATA_SCHEMA.md, DATA_DICTIONARY.md
├── USAGE.md, LIMITATIONS.md, LICENSE.md, OSM_ATTRIBUTION.md
├── CITATION.md, CITATION.cff, CHANGELOG.md
├── MANIFEST.csv, CHECKSUMS.sha256
├── requirements.txt, requirements-generator.txt
├── code/
├── configs/
├── data/
│   ├── instances/              135 complete instance directories
│   └── shared/cities/          frozen GIS assets
├── environment/
├── metadata/
├── reference_results/
│   └── solutions/              135 validated BKS schedules
├── reports/
├── scripts/
├── travel_matrices/            index to OD matrices stored in each instance
└── validation/
```

After downloading and extracting the complete archive, start with
`python scripts/read_instance.py` and `python scripts/validate_release.py --full`.
The release excludes Pareto fronts, populations, candidate route pools,
checkpoints and debugging files. See `USAGE.md` for command scope.

## Source provenance and revision

The released geographic assets for Beijing, Shanghai, and Chongqing use the
harmonized snapshot date 2026-08-31. The 45 Shanghai instances, their OD
matrices, and their reference schedules were rebuilt from the harmonized
Shanghai source; the earlier Shanghai task locations were not relabeled or
reused. Exact source evidence and released-asset hashes are recorded in
`metadata/source_provenance.json` and `OSM_ATTRIBUTION.md`.

The public version is v1.0. Earlier identifiers v3.0.1 and v3.1.0 describe
internal assembly work only; they are not public dataset versions. The internal
history and the identifier crosswalk are documented in `CHANGELOG.md` and
`metadata/building_id_mapping.csv`.

Map data **© OpenStreetMap contributors**, available under the
[ODbL](https://opendatacommons.org/licenses/odbl/1-0/).
See [OSM attribution](https://www.openstreetmap.org/copyright), LICENSE.md and CITATION.md.
