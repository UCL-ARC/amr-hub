# Spatial units

AMR-Hub spatial input uses metres as its canonical linear unit. Building YAML
must declare the current schema and unit at the document root:

```yaml
schema_version: 1
coordinate_unit: m
building:
  # ...
```

All wall, door, opening, content, and agent coordinates are metres. Distances,
radii, clearances, offsets, wall thicknesses, and content dimensions are also
metres. Topological room areas are square metres.

`SpaceInputReader` rejects unitless input and units other than `m`. It does not
infer units from coordinate magnitudes and does not convert non-canonical
building YAML at runtime.

## Floorplan conversion

CAD files can use arbitrary or undeclared local units. Floorplan extraction
configuration must therefore define the source conversion explicitly:

```yaml
spatial_units:
  source_unit: millimetres
  units_per_metre: 1000.0
```

Extraction, correction rules, tolerances, and diagnostics remain in these
source units. The YAML construction stage converts walls, doors, openings,
content positions, and areas to metres and records the conversion provenance:

```yaml
schema_version: 1
coordinate_unit: m
coordinate_provenance:
  source_unit: millimetres
  units_per_metre: 1000.0
```

The source-unit name is descriptive. `units_per_metre` is the authoritative
positive conversion factor. Units must never be inferred from the descriptive
name or from the apparent size of the floorplan.

## Time and movement

`length_of_timestep_in_seconds` defines the number of seconds represented by
one simulation timestep. Under the current movement implementation:

- `agent_movement_speed` is metres per simulation timestep, not metres per
  second;
- `agent_interaction_radius` is metres;
- task durations are integer simulation timesteps;
- changing timestep length requires corresponding review of movement speed and
  task-duration values.

This documents current behaviour. A future change to metres per second would
require movement and travel-time calculations to apply timestep duration.

## Migrating existing YAML

For hand-authored synthetic YAML already expressed in metres, add
`schema_version: 1` and `coordinate_unit: m` without changing coordinates.

Do not label legacy CAD-derived coordinates as metres without conversion.
Instead, add `spatial_units` to the extraction configuration and regenerate the
YAML. Real floorplans, extraction configuration, and generated outputs must
remain inside the TRE or local ignored workspace and must not be committed.
