# Loading and checking GIS-B-ME

## 1. Clone the lightweight GitHub repository

```bash
git clone https://github.com/He-Junjie-92/GIS-B-ME.git
cd GIS-B-ME
```

The clone contains documentation, generation/validation source code, 135 frozen
configuration snapshots, environment files, the compact reference-results table
and public validation summaries. It does **not** contain the benchmark instances,
OD matrices, 135 BKS schedule files, the complete `scripts/` directory or the
full release ZIP.

Install the lightweight repository dependencies when needed with:

```bash
python -m pip install -r environment/requirements.txt
```

## 2. Download the complete benchmark

Open the official v1.0 Release:

`https://github.com/He-Junjie-92/GIS-B-ME/releases/tag/v1.0`

Download the attached `GIS-B-ME-v1.0.zip` asset and its
`GIS-B-ME-v1.0.zip.sha256` checksum sidecar. GitHub's automatically generated
**Source code (zip)** and **Source code (tar.gz)** files are only snapshots of
the lightweight repository and do not contain the complete benchmark.

Verify the archive on Windows PowerShell:

```powershell
Get-FileHash GIS-B-ME-v1.0.zip -Algorithm SHA256
```

On Linux or macOS:

```bash
sha256sum GIS-B-ME-v1.0.zip
```

Compare the reported digest with `GIS-B-ME-v1.0.zip.sha256`, then extract the
archive. All commands below that access instances, OD matrices, BKS solutions or
`scripts/` must be run **after downloading and extracting the complete release
archive**, from its root directory.

## 3. Read and validate the complete release

Use Python 3.10 or newer. From the extracted archive root:

```bash
python -m pip install -r requirements.txt
python scripts/read_instance.py --instance GISB-BJS-CH-100-S012
python scripts/validate_release.py
python scripts/validate_release.py --full
```

The default validation checks file hashes, index coverage, directories and paths.
`--full` additionally reads all 135 workbooks and OD matrices and validates fixed
business windows, identifiers, building capacity, shared access nodes and OD
completeness. It performs no network requests and does not solve the scheduling
problem.

Python example, again from the extracted complete release:

```python
from pathlib import Path
import pandas as pd

root = Path(".").resolve()
instance_id = "GISB-BJS-CH-100-S012"
p = root / "data" / "instances" / instance_id
tasks = pd.read_excel(p / "instance.xlsx", sheet_name="TASKS")
windows = pd.read_excel(p / "instance.xlsx", sheet_name="TASK_WINDOWS")
od = pd.read_parquet(p / "road_matrix.parquet")
task_windows = tasks.merge(windows, on="task_id", validate="one_to_many")
travel_minutes = od.pivot(index="from_node_id", columns="to_node_id",
                          values="road_time_min")
print(tasks.shape, windows.shape, travel_minutes.shape)
```

`task_id` joins TASKS to TASK_WINDOWS. Use `TASKS.node_id` to join to
`NODES.node_id` and the OD endpoint columns. Keep depot `S01` when constructing
route costs. Use `(instance_id, task_id)` across instances and
`(city_code, building_anchor_id)` for frozen candidate buildings.

## 4. Reference results and solution validation

The lightweight repository contains the compact
`reference_results/instance_reference_results.csv`. The 135 final BKS schedule
files are available only in the complete release archive under
`reference_results/solutions/`.

After extracting the complete release, validate one schedule with:

```bash
python scripts/validate_solution.py \
  --instance-dir data/instances/GISB-BJS-CH-100-S012 \
  --solution reference_results/solutions/GISB-BJS-CH-100-S012_solution.csv
```

Recompute the compact descriptive summary only after extracting the complete
release:

```bash
python code/statistics/summarize_release.py --output summary.json
```

## 5. Frozen-instance reproduction

Configuration snapshots alone are not generators. Full frozen-instance
reproduction uses `code/generator/`, `configs/`, the complete release's frozen
GIS inputs and the optional dependencies in
`environment/requirements-generator.txt`. Re-downloading live OpenStreetMap data
is not a reproduction of the frozen instances.

## 6. Optional map regeneration

Run this only from the extracted complete release:

```bash
python -m pip install geopandas matplotlib
python scripts/render_maps.py --instance GISB-BJS-CH-100-S012
```

Regenerating maps modifies `map_preview.png`; an altered release would require
new manifests and checksums.
