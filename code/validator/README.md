# Validation code

- `validate_release.py` audits the file inventory and all 135 frozen instances.
- `validate_solution.py` independently checks one schedule against an instance
  and its released OD matrix.
- `validate_all_solutions.py` validates all 135 published schedules, rebuilds the
  retained reports, verifies technician counts, reconstructs BKS travel and
  checks each solution SHA-256.

Copies are also kept in `scripts/` for short commands from the release root.
