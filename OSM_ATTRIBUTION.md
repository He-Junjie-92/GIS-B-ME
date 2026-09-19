# OpenStreetMap attribution and source provenance

GIS-B-ME contains road-network and building information derived from
OpenStreetMap.

**© OpenStreetMap contributors**

- Copyright and attribution: https://www.openstreetmap.org/copyright
- Open Database License 1.0: https://opendatacommons.org/licenses/odbl/1-0/

Users who redistribute the database or produce a derived database must retain
OpenStreetMap attribution and comply with the ODbL. Maps made from these data
must visibly credit OpenStreetMap contributors.

## Frozen source scope

All released road graphs, road-node mappings, map road layers and OD matrices
use road data with a 2026-08-31 historical cutoff. Beijing and Chongqing
building candidates also use their recorded 2026-08-31 OSM source snapshots.

The released Shanghai building candidates and road graph were reconstructed
under the harmonized 2026-08-31 snapshot policy. The Shanghai historical query
used the cutoff `2026-08-31T23:59:59Z`; the calendar date is the normative
cross-city snapshot label. The 45 Shanghai instances and their OD matrices were
regenerated from these assets, and all Shanghai reference schedules were then
rebuilt and independently validated. Released-asset and source-query hashes are
recorded in `metadata/source_provenance.json`.

Exact source cache identifiers, SHA-256 digests, retrieval timestamps, bounding
boxes and matching evidence are recorded in `metadata/source_provenance.json`
and the per-city `data/shared/cities/<CITY>/metadata.json` files. Live OSM data
must not be substituted when reproducing this frozen release.
