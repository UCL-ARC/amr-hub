# Floorplan extractor

The `floorplan_extractor` package converts labelled DXF floorplans into the
room, wall, and door geometry consumed by the AMR Hub simulation.

The package is split into four modules:

- `dxf_polygon_extraction` reads configured DXF layers, constructs and labels
  room polygons, applies explicit geometry corrections, and attaches doors;
- `shared_walls` replaces accepted pairs of wall faces with a common midline;
- `yaml_construction` serialises the resulting room geometry to the simulation
  YAML schema;
- `spatial_units` validates the explicit source-coordinate conversion used to
  produce canonical metre geometry.

Walls and doors use a centreline representation. Shared walls are normalised to
one common line, while doors are projected onto subsections of the final room
boundaries. Extraction operates in configured source units and YAML
construction converts every spatial value to metres. The runtime then applies
physical wall thickness without preserving CAD wall-face or door-symbol
thickness.

See the
[floorplan extraction guide](../../docs/floorplan_extraction.md)
for configuration, commands, diagnostics, and output details.
