# Floorplan extraction

The floorplan extractor converts labelled DXF geometry into the YAML room
format used by the simulation. It is intended for local Cartesian floorplans;
no coordinate reference system is required.

The extraction pipeline:

1. reads room boundary linework and polygonises it;
2. filters and attaches room labels for the configured floor;
3. applies configured polygon splits, additions, and merges;
4. normalises accepted adjacent wall faces to a shared midline;
5. projects CAD door symbols onto subsections of the final room boundaries;
6. serialises labelled rooms as wall and door line segments.

The resulting geometry represents walls and doors as zero-thickness lines.
Physical wall thickness can be applied when the YAML is loaded into another
model.

## Running the example

Run the example from the `python-code` directory:

```sh
uv run python ../examples/floorplan_extraction.py
```

The default paths are relative to the current directory:

- `floorplan.dxf`: source floorplan;
- `config.yaml`: extraction configuration;
- `output.yaml`: extracted simulation geometry;
- `output_diagnostic.png`: labelled room and door diagnostic.

Alternative paths can be supplied explicitly:

```sh
uv run python ../examples/floorplan_extraction.py \
  --dxf path/to/floorplan.dxf \
  --config path/to/config.yaml \
  --output path/to/output.yaml \
  --diagnostic path/to/output_diagnostic.png
```

The example writes parent directories for the output files when required.
Building name, address, and floor level are example constants in the script
and should be adapted for production use.

## Configuration

The configuration is a YAML mapping. The `polygons` block is required; all
other blocks are optional.

```yaml
polygons:
  polygon_layer_name: "ROOM_BOUNDARIES"
  label_layer_name: "ROOM_LABELS"
  polygon_label_column: "Text"
  polygon_label_target: "room_numbers"
  floor_filter: "E02"
  excluded_room_numbers: []

doors:
  layer_name: "Internal doors"
  entity_col: "EntityHandle"
  out_col: "doors"
  predicate: "intersects"

shared_walls:
  enabled: true
  min_gap: 50.0
  max_gap: 250.0
  angle_tolerance_degrees: 2.0
  min_overlap_ratio: 0.5
  min_overlap_length: 150.0
  canonical_line: "midline"
```

### Room polygons and labels

`polygon_layer_name` identifies the linework used to construct room polygons.
`label_layer_name` identifies the room-label geometries. Labels are normalised
to the line beginning with `floor_filter`, then excluded room numbers are
removed before spatial attachment.

Polygons with no label, ambiguous labels, no attached doors, or unresolved
shared-wall decisions are marked for review by the returned GeoDataFrame.

### Explicit polygon corrections

Floorplan-specific corrections are applied through three optional lists:

- `polygon_splits` divides a selected polygon with configured cut lines and
  assigns labels using seed points;
- `polygon_additions` creates a missing polygon from explicit coordinates;
- `polygon_merges` combines labelled source polygons into one target polygon.

Splits and additions occur before label attachment. Merges occur before
shared-wall and door normalisation.

### Shared walls

Source room polygons often follow opposite faces of the same physical wall.
Shared-wall normalisation detects plausible parallel overlaps and moves both
room boundaries to a common midline.

Candidates must satisfy the configured gap, angle, overlap length, and overlap
ratio thresholds. Candidates are rejected when another room occupies the strip
between the wall faces, when matches are ambiguous, or when applying the
midline would invalidate a room polygon.

Candidate selection uses a Shapely spatial index before the exact geometric
checks. Accepted candidates and rejection reasons that can require review are
the supported diagnostic contract. `gap_too_large` records for distant segment
pairs are broad-phase implementation details and are not guaranteed, because
those pairs may be excluded before exact evaluation.

The result includes:

- `shared_wall_count`;
- `shared_wall_review`;
- `shared_wall_rejections`;
- detailed detection records in
  `GeoDataFrame.attrs["shared_wall_detection"]`.

### Doors

Door entities in architectural DXF files may contain leaf edges, frames, swing
arcs, and other symbol geometry. The extractor groups geometry by
`entity_col`, then projects each door onto a matching final room-boundary
segment.

The output door is therefore a canonical line:

- it lies on a room wall;
- its length represents the detected opening along that wall;
- the same coordinates are attached to both connected rooms where possible;
- CAD swing and leaf geometry is not written to the simulation YAML.

Attachment diagnostics are stored in
`GeoDataFrame.attrs["door_attachment_report"]`. A warning is recorded when a
door cannot be projected onto any room or is attached to more rooms than the
configured maximum.

## Output YAML

Each room contains a name, ordered wall segments, and door segments:

```yaml
rooms:
  - name: E02NN012
    walls:
      - [x1, y1, x2, y2]
    doors:
      - [x1, y1, x2, y2]
```

Door coordinates overlay subsections of the corresponding wall boundaries.
Shared doors are repeated in each connected room because room construction
uses those coordinates to identify connectivity.

## Diagnostic image

The example plots:

- room polygons in pale blue;
- final room boundaries in grey;
- room labels at representative interior points;
- canonical door openings as solid red overlays on the wall boundaries.

A white underlay makes door segments visible against the room boundary.
Shared doors are deduplicated for plotting, so each physical opening appears
once even though it is present in both room records.

The example also contains an optional shared-wall diagnostic helper. When
enabled, it can display accepted midlines and rejected candidate overlaps.
This overlay is intended for extraction review rather than production output.

## Shared-wall performance baseline

Shared-wall candidate detection can be measured independently of the unit-test
suite using synthetic square-room grids:

```sh
uv run python benchmarks/shared_wall_detection.py
```

The script reports room and wall-segment counts, indexed and exhaustive median
timings, speed-up, and material result counts for three input sizes. Use
`--grid-sizes`, `--repeat`, and `--warmup` to control a run. It uses generated
local Cartesian geometry only; no real or sensitive floorplan data is loaded.

The baseline recorded on 20 June 2026 for the exhaustive implementation is:

<!-- shared-wall-baseline-start -->

Environment: Python 3.13.11, Shapely 2.1.2,
Linux 7.0.10-1-MANJARO x86-64. Each size used one warm-up and three measured
runs.

|  Grid | Rooms | Segments | Median (s) | Best (s) | Accepted | Rejected |
| ----: | ----: | -------: | ---------: | -------: | -------: | -------: |
|   4x4 |    16 |       64 |   0.013184 | 0.012707 |       24 |      768 |
|   8x8 |    64 |      256 |   0.162462 | 0.155485 |      112 |   14,336 |
| 12x12 |   144 |      576 |   0.793025 | 0.786961 |      264 |   76,032 |

<!-- shared-wall-baseline-end -->

The indexed implementation was compared with the retained exhaustive reference
on the same environment and benchmark settings:

|  Grid | Rooms | Segments | Indexed median (s) | Exhaustive median (s) | Speed-up |
| ----: | ----: | -------: | -----------------: | --------------------: | -------: |
|   4x4 |    16 |       64 |           0.011804 |              0.011553 |    0.98x |
|   8x8 |    64 |      256 |           0.048875 |              0.095364 |    1.95x |
| 12x12 |   144 |      576 |           0.110366 |              0.383982 |    3.48x |

All three comparisons produced the same accepted and material rejection counts.
The small layout is effectively unchanged, while the benefit increases with
the number of wall segments. At 12x12, the indexed result is about 7.2 times
faster than the original task-1 exhaustive baseline of 0.793025 seconds; part
of that additional gain comes from indexing third-room obstruction queries.

Timings are descriptive rather than test thresholds because they depend on the
machine and runtime environment. Candidate and rejection counts provide a
deterministic correctness check alongside the regression tests.

## API reference

The generated API documentation covers:

- [DXF extraction](api/floorplan_dxf_extraction.md);
- [shared-wall normalisation](api/floorplan_shared_walls.md);
- [YAML construction](api/floorplan_yaml_construction.md).
