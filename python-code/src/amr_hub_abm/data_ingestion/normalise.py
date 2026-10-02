"""Normalise extracted location fields into simulation event locations."""

import pandas as pd

from amr_hub_abm.data_ingestion.doors import extract_door_location_columns


def normalise_door_location_events(
    frame: pd.DataFrame,
    input_column: str = "input",
) -> pd.DataFrame:
    """
    Add AMR-Hub event locations parsed from door descriptions.

    The generated ``location`` field uses the existing simulation format
    ``Building:floor:room``. Rows without a complete parsed location receive a
    missing ``location`` value for review before simulation.

    Parameters
    ----------
    frame : pandas.DataFrame
        Source event data containing door descriptions.
    input_column : str, default="input"
        Name of the column containing door descriptions.

    Returns
    -------
    pandas.DataFrame
        Copy of ``frame`` with ``building``, ``floor``, ``room_code``, and
        ``location`` columns.

    """
    result = extract_door_location_columns(frame, input_column)
    complete_location = result[["building", "floor", "room_code"]].notna().all(axis=1)
    location = pd.Series(pd.NA, index=result.index, dtype="string")
    location.loc[complete_location] = (
        result.loc[complete_location, "building"].astype(str)
        + ":"
        + result.loc[complete_location, "floor"].astype(int).astype(str)
        + ":"
        + result.loc[complete_location, "room_code"].astype(str)
    )
    return result.assign(location=location)
