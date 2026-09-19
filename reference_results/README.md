# Reference results

This directory links the released GIS-B-ME instances to the final reference
results used for the benchmark. It contains one compact table and one feasible
schedule for each of the 135 instances.

## Contents

- `instance_reference_results.csv`: personnel bounds, workforce status, the
  best-known travel value, method provenance, validation status and the SHA-256
  digest of each published solution.
- `solutions/`: one final feasible schedule per instance.
- `SHA_SUPPLEMENTARY_SEARCH_RESULTS.csv`: schema-preserving empty table; no SHA 500-task instance was eligible for fixed-`K` supplementary search.
- `../reports/DATASET_STATISTICS.csv`: released descriptive statistics.
- `../reports/REFERENCE_SUMMARY.csv`: released reference-result summary.
- `../reports/TABLE11_ROUTE_POOL_SUMMARY.csv`: route-pool results for all 45 100-task instances.
- `../validation/reference_solutions_validation.csv`: independent validation
  summary for all schedules.
- `../validation/reference_solutions/`: one machine-readable validation report
  per schedule.

The published schedules preserve the selected technician count, service day and
task sequence from the recorded experiment. Their arrival, waiting, completion
and travel fields are evaluated against the OD matrices in this release. Every
published schedule was then independently checked for task coverage, duplicate
service, allowed days, hard time windows, service durations, OD travel times,
same-day depot return and the 480-minute daily limit.

## Status interpretation

`K-OPT` means that the validated technician upper bound equals a valid personnel
lower bound. It proves the minimum technician count for the stated model.
`K-OPEN` means that a personnel gap remains. The `gap` column is
`upper_bound - lower_bound`.

The travel value is best known at the published technician count. `K-OPT` does
not by itself prove global optimality of travel. For route-pool recombination,
optimality applies only to the finite route-template pool used by that run.

The verified workforce summary is:

| Result | Instances |
|---|---:|
| K-OPT | 77 |
| K-OPEN | 58 |
| Gap = 1 | 40 |
| Gap = 2 | 18 |

K-OPT counts by task scale are 45/45 for 100 tasks, 32/45 for 500 tasks and 0/45 for 1000 tasks.


## Route-pool summary and SHA supplementary-search eligibility

Table 11 uses all 45 100-task instances as its denominator. For `5IGA`, 32/45
instances improve, the mean improvement over the formal denominator is
1.6087200463650444%, and the cumulative saving is 397.97993220253124 min. For
`B0_5IGA`, the corresponding values are 32/45, 1.6401724268401403%, and
407.80231480379916 min. Solver optimality applies only to each finite candidate
route pool, not to the original scheduling problem.

All 15 SHA 500-task instances reached K-OPT in the basic search. Therefore none
was eligible for fixed-`K` supplementary search. The released SHA supplementary
table intentionally contains its header and no data rows; this means “no eligible
SHA instances,” rather than “supplementary search output missing.”

## Table fields

`instance_id` is the join key to `data/instances/`. `lower_bound`,
`upper_bound`, `gap` and `status` describe the personnel objective.
`bks_technicians` and `bks_travel_time_min` form the published BKS pair.
`method`, `run_seed`, `source_run_seeds`, `dataset_release` and
`source_reference_batch` record provenance. `dataset_release` is the public
dataset version; `source_reference_batch` preserves the internal, immutable
result batch from which the record was assembled. `solution_file`,
`solution_sha256` and `validator_status` make each result auditable.

## Method labels and seeds

- `IGA` identifies an independently validated Improved Genetic Algorithm run
  selected at the published workforce count. `run_seed` is that run's algorithm
  seed, and `source_run_seeds` repeats the single contributing seed.
- `IGA_fixed_K3_refinement_5x90s` identifies the fixed-workforce refinement used
  for selected 500-task cases. It ran five IGA starts, with seeds 101, 202, 303,
  404 and 505, for up to 90 seconds per start at `K=3`; the best independently
  validated feasible run supplies the published solution. `run_seed` identifies
  the selected run.
- `B0_5IGA_route_templates_plus_CPLEX_recombination` identifies the 100-task
  fixed-`K=1` refinement. Route templates were collected from the deterministic
  baseline (`B0`, seed 0) and five independently validated IGA runs (seeds 101,
  202, 303, 404 and 505). CPLEX then solved the finite route-template selection
  model exactly. This proves optimality only inside that finite pool. Because the
  output combines multiple runs, `run_seed` is empty and `source_run_seeds`
  lists all six contributing seeds.

## Schedule rows and depot return

`travel_time_from_prev` records travel from the depot or the preceding task to
the current task. The final return trip from the last task to the depot is not
represented as a separate task row, but it is included in `route_travel_time`
and `route_duration`. Consequently, summing only `travel_time_from_prev` within
a route omits the final return leg.

## Intentionally excluded artifacts

The core release does not include Pareto-front points, complete GA/IGA
populations, generation histories, intermediate nondominated solutions, every
seed's candidate solutions, candidate route pools, solver checkpoints,
debugging logs or temporary solver files. These are solver-generated
intermediate artifacts rather than benchmark inputs or final reference results.
