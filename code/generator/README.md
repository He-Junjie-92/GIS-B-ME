# Generator code snapshot

This directory contains the generator modules used by the GIS-B-ME design. The
135 release configurations are under `metadata/generation_configs/`, and the
frozen city inputs are under `data/shared/cities/`.

`generate_gis_b_instance.py` is the single-instance entry point. Its supporting
modules preserve the building-capacity, spatial clustering, fixed-speed OD and
fixed business-window rules used by the released design. Use a separate output
directory when regenerating an instance; generation is not required to read or
validate the frozen release.

Example (after adapting output paths in a copied configuration):

```text
python code/generator/generate_gis_b_instance.py --config copied_config.json
```

The recommended release-level command resolves the packaged paths, regenerates
one instance and performs the same canonical comparison used by the full audit:

```text
python code/generator/reproduce_instance.py \
  --instance-id GISB-BJS-CH-100-S012 \
  --output-root reproduced
```

The generator requires the packages in `requirements-generator.txt`. It reads
only the supplied frozen GIS inputs during normal reproduction; live OSM data
should not be substituted for the release assets.

The full retained audit passed all 135 instances. Its evidence and the precise
normalization scope are in `validation/generator_reproducibility/README.md`.
