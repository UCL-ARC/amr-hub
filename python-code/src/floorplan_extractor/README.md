# Floorplan extractor

The `floorplan_extractor` package converts labelled DXF floorplans into the
room, wall, and door geometry consumed by the AMR Hub simulation.

The package is split into three modules:

- `dxf_polygon_extraction` reads configured DXF layers, constructs and labels
  room polygons, applies explicit geometry corrections, and attaches doors;
- `shared_walls` replaces accepted pairs of wall faces with a common midline;
- `yaml_construction` serialises the resulting room geometry to the simulation
  YAML schema.

Walls and doors use a centreline representation. Shared walls are normalised to
one common line, while doors are projected onto subsections of the final room
boundaries. Physical wall thickness can therefore be applied by downstream
consumers without preserving CAD wall-face or door-symbol thickness.

See the
[floorplan extraction guide](../../docs/floorplan_extraction.md)
for configuration, commands, diagnostics, and output details.
