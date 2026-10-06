# Running The Model In The TRE

## Prepare The TRE Workspace

AMR-Hub runs inside the TRE using the versioned model code, the raw source
DuckDB database, and the raw DWG floorplan held in approved TRE storage. The
floorplan extractor consumes DXF, so a DWG must first be converted using an
approved TRE-side CAD conversion process. Raw inputs, generated floorplans,
generated event data, reconciliation audits, and simulation outputs should not
be exported from the TRE.

The source DuckDB is the starting operational-data input. It is not yet the
simulator's `location_timeseries` relation. The ingestion pipeline later derives
a separate simulator-ready DuckDB database from approved source views.

The DWG is the starting floorplan input. The floorplan-extraction pipeline later
derives a metre-based spatial YAML file from it. That YAML is then loaded by
`SpaceInputReader` and used by the simulator.

A typical TRE workspace layout is:

```text
amr-hub-code/              versioned model code or approved container
input/raw-events.duckdb    raw source database
input/floorplan.dwg        raw floorplan
config/                    TRE-side extraction and simulation configuration
derived/                   generated floorplan and simulator event data
audit/                     reconciliation reports
output/                    simulation outputs
```

The `input/`, `derived/`, `audit/`, and `output/` directories remain within the
TRE.

## Prepare The Floorplan

Convert the source DWG to DXF if necessary. The floorplan extractor converts
the DXF into the spatial YAML format consumed by `SpaceInputReader`.

Before extraction, establish the DXF coordinate unit and the number of source
units per metre. The required `spatial_units` configuration converts all output
geometry to metres. Coordinates and geometric thresholds in the extraction
configuration remain in the DXF source unit. Create a TRE-side extraction
configuration, then run the extractor with explicit input and output paths.

```sh
uv run python ../examples/floorplan_extraction.py \
  --dxf /project/input/floorplan.dxf \
  --config /project/config/floorplan-extraction.yml \
  --output /project/derived/building.yml \
  --diagnostic /project/audit/floorplan-diagnostic.png \
  --building-name "Configured building name" \
  --building-address "TRE-held address" \
  --floor-level 2
```

The configuration is specific to a floorplan. The following is a non-sensitive
template; layer names, labels, coordinate corrections, and thresholds must be
established from the actual DXF inside the TRE.

```yaml
spatial_units:
  source_unit: millimetres
  units_per_metre: 1000.0

polygons:
  polygon_layer_name: "ROOM_BOUNDARIES"
  label_layer_name: "ROOM_LABELS"
  polygon_label_column: "Text"
  polygon_label_target: "room_numbers"
  floor_filter: "FLOOR_CODE"
  excluded_room_numbers: []

doors:
  layer_name: "INTERNAL_DOORS"
  entity_col: "EntityHandle"
  x_col: "x"
  y_col: "y"
  out_col: "doors"
  predicate: "intersects"
  excluded_entity_handles: []

shared_walls:
  enabled: true
  min_gap: 50.0
  max_gap: 250.0
  angle_tolerance_degrees: 2.0
  min_overlap_ratio: 0.5
  min_overlap_length: 150.0
  canonical_line: "midline"

open_boundaries:
  pairs: []

polygon_splits: []
polygon_additions: []
polygon_merges: []
```

Validate the generated YAML before preparing event data:

- It loads successfully through `SpaceInputReader`.
- It declares the current spatial schema version and `coordinate_unit: m`.
- Rooms have valid geometry and expected building, floor, and room identifiers.
- Each physical door connects exactly two rooms.
- Overall dimensions and door widths are plausible in metres.
- Disconnected room groups and rooms without usable doors are identified.

The generated YAML is the spatial-model input for event reconciliation and the
simulation. It remains in the TRE under `derived/`.
