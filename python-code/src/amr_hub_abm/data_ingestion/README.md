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

Bed identifiers can be parsed with `extract_bed_location`; they require a
site-controlled room-code lookup table. Real source data and lookup tables must
remain in the TRE and must not be committed to this repository.
