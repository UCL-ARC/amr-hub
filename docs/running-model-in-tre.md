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

The configuration is specific to a floorplan. Start from the shareable
[`floorplan-extraction.example.yml`](../config/floorplan-extraction.example.yml)
template; layer names, labels, coordinate corrections, and thresholds must be
established from the actual DXF inside the TRE.

Validate the generated YAML before preparing event data:

- It loads successfully through `SpaceInputReader`.
- It declares the current spatial schema version and `coordinate_unit: m`.
- Rooms have valid geometry and expected building, floor, and room identifiers.
- Each physical door connects exactly two rooms.
- Overall dimensions and door widths are plausible in metres.
- Disconnected room groups and rooms without usable doors are identified.

The generated YAML is the spatial-model input for event reconciliation and the
simulation. It remains in the TRE under `derived/`.

## Configure The Simulation

Create a TRE-side simulation configuration after validating the metre-based
floorplan. This configuration defines the simulation window and movement
assumptions, and identifies the derived event database created in the next
step.

Start from the shareable
[`simulation.example.yml`](../config/simulation.example.yml) template. It keeps
fixed simulator format settings while leaving TRE paths and study-specific
assumptions blank.

`buildings_path` must reference the validated generated floorplan YAML. Its
`coordinate_unit` must be `m`; movement speed and interaction radius are
therefore specified in metres.

`location_data.path` is the intended destination of the simulator-ready
DuckDB database. It does not need to exist when this configuration is created;
the location-event preparation step creates it later in the TRE.

Use UTC for `start_time` and `end_time`. The location-event preparation step
excludes source records outside this window.

The one-second timestep shown above resolves movement at room and door scale.
With this timestep, `agent_movement_speed: 1.2` represents an initial walking
speed assumption of 1.2 metres per second. A 60-second timestep would require
an approximately 72-metre movement step to represent the same walking speed,
which is not suitable for indoor movement or door traversal.

Task durations are specified as timestep counts. The example represents 15
minutes for patient attendance and 30 minutes for workstation use. These,
along with walking speed, interaction radius, and the simulation window, are
explicit modelling assumptions that must be calibrated and recorded in the TRE
study documentation before analysis.

## Prepare Location Event Data

Prepare a separate simulator-ready DuckDB database from approved TRE source
views. The raw source DuckDB remains unchanged. The derived database is written
to the `location_data.path` configured in the previous section.

Create TRE-only DataFrames or views for the following inputs:

| Input              | Required fields                                                                            | Purpose                                                     |
| ------------------ | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| Interaction events | `locationID`, `hcw_id`, `timestamp`, `event_type`, `patient_id`, `door_id`, `content_type` | Source observations to reconcile against the model.         |
| Roster             | `hcw_id`, `shift_start`, `shift_end`                                                       | Retains only events occurring during an eligible HCW shift. |
| Bed references     | `locationID`, `bedName`                                                                    | Resolves patient-attendance event locations.                |
| Room-code mappings | `roomCode`, `roomName`, `bedName`                                                          | Maps source bed references to floorplan room names.         |
| Door references    | `locationID`, `descriptiveDoorName`                                                        | Resolves door-access event locations.                       |

Use stable pseudonymised identifiers for `hcw_id` and `patient_id`. Source
timestamps may include timezone information; the preparation pipeline
normalises them to UTC before writing the derived DuckDB database.

Set `event_type` as follows:

- `attend_patient` for flowsheet or patient-attendance records.
- `door_access` for door-message records.
- `workstation` for workstation records. These are retained in the audit as
  `workstation_deferred` and are not yet supplied to the simulation.

Use the existing Python API from an approved TRE-side analysis script or
notebook. Loading the source tables into the input DataFrames is
site-specific; pass the resulting DataFrames to
`build_simulation_location_database()`.

```python
from pathlib import Path

import numpy as np

from amr_hub_abm.config import SimulationConfig
from amr_hub_abm.data_ingestion.pipeline import (
    build_simulation_location_database,
)

report = build_simulation_location_database(
    events=events,
    bed_references=bed_references,
    room_code_mappings=room_code_mappings,
    door_references=door_references,
    roster=roster,
    config=SimulationConfig.from_file(Path("/project/config/simulation.yml")),
    output_path=Path("/project/derived/location-events.duckdb"),
    patient_building="MODEL_BUILDING_NAME",
    patient_floor=2,
    rng_generator=np.random.default_rng(0),
)
```

`output_path` must be a new file. The function writes:

```text
/project/derived/location-events.duckdb
  location_timeseries
  amr_hub_schema
  location_reconciliation_audit
```

`location_timeseries` contains only resolved, rostered events within the
configured simulation window. It is the only relation read by the simulator.

`location_reconciliation_audit` contains every source event and its outcome.
It remains in the TRE and must not be exported. Review all statuses other than
`resolved`, including `reference_not_found`, `ambiguous_reference`,
`unparseable_location`, `room_code_not_found`, `room_not_in_model`,
`room_has_no_doors`, `ambiguous_doors`, `hcw_not_rostered`,
`outside_rostered_shift`, `outside_simulation_window`, and
`workstation_deferred`.

Do not guess a room or door for unresolved records. Correct the TRE-side
reference mappings or floorplan configuration, then rerun preparation.

Before running the simulation, confirm that:

- The derived database was written to the configured `location_data.path`.
- `location_timeseries` is non-empty and passes schema validation.
- All retained events fall within the configured UTC simulation window.
- The reconciliation audit has been reviewed and retained in the TRE.
