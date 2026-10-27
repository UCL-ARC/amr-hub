"""Tests for the extra-HCW location timeseries generator."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).parents[1] / "contact_analysis" / "generate_extra_hcws.py"
spec = importlib.util.spec_from_file_location("generate_extra_hcws", SCRIPT)
assert spec is not None
assert spec.loader is not None
generator = importlib.util.module_from_spec(spec)
sys.modules["generate_extra_hcws"] = generator
spec.loader.exec_module(generator)

WINDOW = (pd.Timestamp("2024-01-01 07:00"), pd.Timestamp("2024-01-01 18:55"))
PATIENTS = [1, 2, 3, 4]


def _schedule(seed: int, wc: float = 0.3, restaurant: float = 0.3) -> list:
    return generator.hcw_schedule(
        WINDOW, PATIENTS, (wc, restaurant), 20, np.random.default_rng(seed)
    )


def test_schedule_is_reproducible_and_within_window() -> None:
    """Same seed gives same events, ordered and inside the window."""
    first = _schedule(3)
    assert first == _schedule(3)
    assert first != _schedule(4)
    timestamps = [event[0] for event in first]
    assert timestamps == sorted(timestamps)
    assert WINDOW[0] <= timestamps[0]
    assert timestamps[-1] <= WINDOW[1]


def test_schedule_contains_all_activity_types() -> None:
    """Schedules round on all patients and visit WC and restaurant."""
    events = _schedule(1)
    attended = {e[3] for e in events if e[2] == "attend_patient"}
    locations = {e[1] for e in events}
    assert attended == set(PATIENTS)
    assert any(e[2] == "workstation" for e in events)
    assert generator.WC in locations
    assert generator.RESTAURANT in locations


def test_combine_assigns_unique_positive_sequences() -> None:
    """Merged events get unique sequence ids in time order."""
    extra = generator.to_frame([(3, e) for e in _schedule(2)])
    base = extra.assign(hcw_id=1)
    combined = generator.combine(base, extra)
    assert combined["event_sequence"].is_unique
    assert combined["event_sequence"].min() == 1
    assert combined["timestamp"].is_monotonic_increasing
