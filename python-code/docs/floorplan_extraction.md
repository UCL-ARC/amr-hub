# Floorplan extraction

The floorplan extractor converts labelled DXF room polygons into the YAML wall
format used by the simulation. Source polygons can follow opposite faces of the
same physical wall, leaving a wall-thickness gap between adjacent rooms.

Shared-wall normalisation detects plausible pairs of parallel wall faces and
moves accepted overlaps to a common midline. The example script writes:

- `output.yaml`, containing the resulting room geometry;
- `output_diagnostic.png`, showing the extraction and shared-wall decisions.

Run the example from `python-code`:

```sh
uv run python ../examples/floorplan_extraction.py
```

## Diagnostic classes

The coloured lines in `output_diagnostic.png` explain the outcome of
shared-wall processing. They are diagnostic overlays; the underlying polygon
geometry is already normalised before plotting.

### Green: accepted shared wall

A green solid line is an overlap that passed candidate detection and was
successfully applied to both room polygons. Both final polygon boundaries
contain the same midline coordinates.

These arise when the wall faces:

- are sufficiently parallel;
- have a gap within the configured range;
- have enough overlapping length or aggregate wall coverage;
- are not blocked by another room;
- do not conflict with a competing match; and
- can be applied while keeping both polygons valid.

### Yellow: rejected shared wall

A yellow dashed line is the actual overlap portion of a pair rejected during
candidate detection. It does not alter either polygon.

Common causes are:

- the overlap is shorter than `min_overlap_length`;
- the overlap ratio is below `min_overlap_ratio`;
- the gap is outside the configured range; or
- another room intersects the strip between the proposed wall faces.

Yellow can appear next to green when different intervals of the same original
wall segment receive different decisions.

### Purple: rejected because geometry would become invalid

A purple dotted line passed geometric candidate detection, but applying it
would make at least one room polygon invalid, for example by creating a
self-intersection. It is therefore excluded from the final geometry.

Candidates are attempted transactionally, longest overlap first. A candidate
is marked green only when both affected polygons remain valid; otherwise it is
recorded as `normalisation_invalid_geometry` and shown in purple.

### Red: ambiguous match

If present, a red dashed line indicates competing candidates that overlap on
the same source wall interval. The extractor cannot safely select one match, so
none of the competing overlaps are applied.

## Interpreting the image

The diagnostic should be read as follows:

- green confirms a shared boundary in the generated polygons;
- yellow indicates a threshold or obstruction decision to review;
- purple identifies a candidate that needs safer polygon-rewriting logic or
  source-geometry investigation;
- red identifies a matching ambiguity that requires disambiguation.

Removing the diagnostic overlay does not undo normalisation. It only removes
the coloured explanation of decisions from the plot.
