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
