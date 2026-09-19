# Change log

## v1.0

Initial public release of GIS-B-ME. No release date is stated before the GitHub
Release is published.

- Repository: `https://github.com/He-Junjie-92/GIS-B-ME`
- Release: `https://github.com/He-Junjie-92/GIS-B-ME/releases/tag/v1.0`
- Includes 135 benchmark instances and 72,000 preventive-maintenance task records.
- Covers BJS, SHA and CKG; task sizes 100, 500 and 1000; spatial patterns CU,
  CH and CZ; and five seeds per configuration.
- Uses the harmonized 2026-08-31 OSM geographic snapshot for all three study areas.
- Includes directed urban road-network travel matrices, validated reference
  results and one final feasible schedule per instance.
- Includes generation, validation and analysis code with user documentation.
- Independently validates all 135 final schedules; the verified workforce status
  is K-OPT=77, K-OPEN=58, Gap1=40 and Gap2=18.
- Excludes Pareto fronts, populations, candidate route pools, checkpoints and
  debugging logs because they are intermediate solver artifacts.
- Provides OSM provenance, CFF citation metadata, a data dictionary, file
  manifest and SHA-256 checksums.

## Release-preparation history

The labels below identify audited preparation stages and are not separate public
dataset versions.

### Final candidate (formerly `v1.0-rc2`)

- Harmonized the Shanghai OSM building and road sources to 2026-08-31.
- Rebuilt all 45 SHA instances and OD matrices without changing generation rules
  or seeds, then recomputed and independently validated all SHA reference results.
- Preserved BJS and CKG instance, OD and BKS scientific files.
- Revalidated the complete 135-instance release.

### Earlier assembly revisions

- Restored source OSM identifiers for frozen building candidates and replaced
  development-machine paths with package-relative paths.
- Standardized released map and OD road assets to the common 2026-08-31 source.
- Preserved task definitions, benchmark factors, service rules and random seeds.
