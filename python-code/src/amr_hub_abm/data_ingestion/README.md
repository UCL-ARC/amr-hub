# Data Ingestion

`amr_hub_abm.data_ingestion` prepares source healthcare location fields for
the existing AMR-Hub event-table format. It is intentionally a preprocessing
module: it does not read floorplans, validate room codes against YAML, or alter
simulation creation.

## Location Contract

A door description such as:

```text
GFA 2ND FLR DINING MM002 DOOR
```

produces:

```text
building: GFA
floor: 2
room_code: G02MM002
location: GFA:2:G02MM002
```

`GFA` is the building name. Its first initial, `G`, is intentionally used when
expanding a short source room code into the canonical room code. The full
canonical room code is expected to match the floorplan YAML room `name`.

## Use

```python
import pandas as pd

from amr_hub_abm.data_ingestion import normalise_door_location_events

events = pd.DataFrame(
    {"door_description": ["GFA 2ND FLR DINING MM002 DOOR"]}
)
normalised = normalise_door_location_events(events, "door_description")
```

Rows whose source description lacks a complete location retain missing values
in `location`, allowing them to be reviewed before being supplied to the
simulation.

## Prepared Events and Audit

`prepare_location_events` prepares one mixed source-event table for the
simulator input contract. Source events must retain their own unique identifier
and use the event fields `hcw_id`, `timestamp`, `event_type`, `patient_id`,
`door_id`, and `content_type`. The caller supplies the source location key and
TRE-side bed and door reference tables separately.

The preparer currently supports `attend_patient` and `door_access` events. It
returns two DataFrames:

- `location_timeseries` contains only resolved events. It uses the fixed
  `event_sequence`, `hcw_id`, `timestamp`, `location`, `event_type`,
  `patient_id`, `door_id`, and `content_type` columns expected by the validated
  location-event input. Event sequences preserve source row order, and resolved
  door events use the model door identifier.
- `audit` contains every source event, including its source identifier, assigned
  event sequence, resolution status, and available model mapping details. Filter
  this table to statuses other than `resolved` to obtain the reconciliation
  report.

Events are never assigned a guessed location. Unsupported interaction types are
retained in the audit with `unsupported_interaction_type` until they have an
explicit mapping rule.

## Location Event Data Contract

The simulator reads a versioned DuckDB `location_timeseries` table or trusted
view. `amr_hub_schema` must register the `location_timeseries` component at the
configured schema version. All timestamps are normalised to UTC before storage
in the timezone-naive DuckDB `TIMESTAMP` column.

| Column           | DuckDB type | Meaning and validation                                                                                                                                                                      |
| ---------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `event_sequence` | `BIGINT`    | Positive unique sequence preserving the deterministic source-event order. Events sharing a timestamp are ordered by their generated source-event key.                                       |
| `hcw_id`         | `INTEGER`   | Positive pseudonymised healthcare-worker key, stable across approved TRE database tables and available for later linkage to a model digital twin.                                           |
| `timestamp`      | `TIMESTAMP` | Observed event time, normalised to UTC. It must fall within the configured simulation window.                                                                                               |
| `location`       | `VARCHAR`   | Canonical model room identity: `building:floor:room_code`. It is room-level currently, not an observed coordinate. Finer placement may be added when model content and evidence support it. |
| `event_type`     | `VARCHAR`   | Currently `attend_patient` or `door_access`.                                                                                                                                                |
| `patient_id`     | `INTEGER`   | Positive pseudonymised patient key, stable across approved TRE database tables. Required for `attend_patient`; null for `door_access`.                                                      |
| `door_id`        | `INTEGER`   | Non-sensitive ID assigned by the loaded floorplan model after reconciliation. Required for `door_access`; null for `attend_patient`. Source door identifiers remain in the TRE only.        |
| `content_type`   | `INTEGER`   | Reserved for future content and workstation tasks. It is null for the currently supported event types.                                                                                      |

The source event categories currently have the following treatment:

- Flowsheet records are reconciled to `attend_patient` events.
- Door-message records are reconciled to `door_access` events.
- Roster records determine HCW shift eligibility and are not simulation events.
- Workstation records are retained as `workstation_deferred` in the audit until
  their mapping is implemented.

The TRE-only `location_reconciliation_audit` relation records source-event
provenance, reconciliation outcomes, model mapping details, and collapsed
duplicate counts. It may contain pseudonymised identifiers and must not be
committed to the repository or exported outside the TRE.

Source tables are not required to provide an event ID. Ingestion creates a
deterministic provenance key from event category, pseudonymised HCW key,
UTC-normalised timestamp, source location key, patient key, door key, and
content type. Exact duplicate composite records are treated as duplicate source
events: one is prepared and the audit retains the number collapsed.

## Reconciliation Statuses

The audit distinguishes missing or duplicate references
(`reference_not_found`, `ambiguous_reference`), unparsable locations
(`unparseable_location`), missing room-code mappings (`room_code_not_found`),
and rooms that do not exist in the model (`room_not_in_model`). It also records
missing room or door geometry, rooms without doors, and ambiguous door mappings
(`room_has_no_spatial_geometry`, `door_has_no_spatial_geometry`,
`room_has_no_doors`, and `ambiguous_doors`). Ambiguous door records include the
number of candidate model doors and are excluded rather than selected
arbitrarily.

## Spatial Placement

This package resolves source descriptions to canonical room identities; it does
not assign coordinates. `amr_hub_abm.location_resolution` resolves those
identities against the loaded model. Its temporary deterministic rule uses the
room polygon centroid, with an interior fallback for concave rooms. Door events
use the midpoint of a model door only when the resolved room has exactly one
candidate door. These are modelling assumptions rather than observed positions.

Bed identifiers can be parsed with `extract_bed_location`; they require a
site-controlled room-code lookup table. Real source data and lookup tables must
remain in the TRE and must not be committed to this repository.
