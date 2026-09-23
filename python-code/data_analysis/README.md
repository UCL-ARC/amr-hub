# AMR-HUB: IRL Feasibility Analysis

## Quick Start

Opt Step 1 runs from the repo root (`python-code/`); everything after that runs
from inside `data_analysis/` — the scripts use flat `from data_wrangler
import ...`-style imports and default file paths (`synthetic_amr.duckdb`,
`trajectories.pkl`) relative to that folder.

```sh
# 1. OPt Repo root: install the data-analysis extra (duckdb) into the venv, once.
cd python-code
uv sync --extra data-analysis          # or: pip install -e ".[data-analysis]"

# 2. Move into data_analysis/ -- every command below runs from here.
cd data_analysis

# 3. Create a synthetic DuckDB file (we include synthetic_amr.duckdb in the repo).
python make_synthetic_db.py --out synthetic_amr.duckdb \
    --seed 0 --n-staff 18 --n-days 14 --noisy-fraction 0.3

# 4. data_wrangler.py report: sanity-check the DB before trusting it.
#    Writes ./simulation_outputs/duckdb_analysis.log plus 3 plots, as well
#    as printing here.
python data_wrangler.py --db synthetic_amr.duckdb report

# 5. data_wrangler.py extract (Phase 1): raw event log -> per-shift trajectories.
python data_wrangler.py --db synthetic_amr.duckdb extract --out trajectories.pkl

# 6. markov_analyzer.py (Phase 2): is the result learnable enough for IRL?
python markov_analyzer.py --data trajectories.pkl learnability-stats
python markov_analyzer.py --data trajectories.pkl irl-feasibility
python markov_analyzer.py --data trajectories.pkl compare-state-variants
```

See [Usage](#usage) below for the full
workflow (including `place-workstations`, `report` diagnostics
command), and [Requirements](#requirements).

Based on the info in Idil's issue [#174](https://github.com/UCL-ARC/amr-hub/issues/174).

Before spending time on inverse reinforcement learning (IRL) to derive a
reward function from real staff movement logs, we need to know whether
those logs actually contain learnable structure.

This is a testing/prototyping pipeline for pre TRE-deployment validation of
the approach in issue #174. The goal is a working pipeline that demonstrates
the method end-to-end, not a comprehensive production test suite.

The pipeline runs in two phases, handed off via a pickle file. A synthetic
DB generator (`make_synthetic_db.py`) stands in for the TRE database.

1. **Synthetic data generator** (`make_synthetic_db.py`) creates a raw
   staff-location event log matching the real data schema.

2. **`data_wrangler.py`** turns the raw event log into per-shift movement
   sequences, on the premise that we analyze one staff member's trajectory
   per shift.

3. **`markov_analyzer.py`** runs a Markov-chain analysis reporting how
   predictable staff movement is, per shift trajectory.

```text
Real/synthetic DuckDB --[data_wrangler.py]--> trajectories.pkl --[markov_analyzer.py]--> stats
```

## Scripts

| Script                 | Purpose                                                                                                                                                                                                               |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make_synthetic_db.py` | Generates a fake DuckDB file with the same schema, for testing without real data.                                                                                                                                     |
| `data_wrangler.py`     | Phase 1: extracts/cleans DB events into `Shift`/`Step` trajectories (`extract`), infers workstation rooms (`place-workstations`), and writes data-quality diagnostics plus plots to `simulation_outputs/` (`report`). |
| `markov_analyzer.py`   | Phase 2: runs the statistical commands (`learnability-stats`, `irl-feasibility`, `compare-state-variants`) against `data_wrangler.py`'s pickled output.                                                               |

Unit tests live in [`../tests/data_analysis/`](../tests/data_analysis/)
(`test_data_wrangler.py`, `test_markov_analyzer.py`) — see [Tests](#tests).

## Synthetic Data

`make_synthetic_db.py` builds a fake DuckDB file with the same schema as the
real database (`Data.StaffLocationEvent` + `Ref.Door/Workstation/Roster/
Department/Staff/InteractionType`): a ward (3 bays + triage, 14 beds), 6
doors, 3 workstations (2 fixed, 1 deliberately mobile "WOW" cart), staff
split between a fixed room-visit rotation ("routine") and randomized
order timing ("noisy") plus a few roster start events left without a
matching end. TODO: Use actual floor plan

```sh
python make_synthetic_db.py --out synthetic_amr.duckdb \
    --seed 0 --n-staff 18 --n-days 14 --noisy-fraction 0.3
```

| Flag                    | Effect                                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------- |
| `--seed`                | RNG seed                                                                                  |
| `--n-staff`, `--n-days` | scale                                                                                     |
| `--noisy-fraction`      | fraction of staff with random-order timed visits (0.0 = fully routine, 1.0 = fully noisy) |

`synthetic_amr.duckdb` (the default mix, 30% noisy) is included as test input.
Other useful scenarios can be generated as below:

| Scenario                         | Command                                                     | What it demonstrates                                                                                                        |
| -------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| All routine staff                | `--out synthetic_amr_clean.duckdb --noisy-fraction 0.0`     | `irl-feasibility` accuracy ~0.77 — high learnability                                                                        |
| All noisy staff                  | `--out synthetic_amr_noisy.duckdb --noisy-fraction 1.0`     | accuracy ~0.67, visibly lower lift over Markov checks the pipeline differentiates data quality, not just "runs on anything" |
| 60 staff x 30 days (~98K events) | `--out synthetic_amr_large.duckdb --n-staff 60 --n-days 30` | scale/performance check (runs in well under a second)                                                                       |

The source data is a single event log, `Data.StaffLocationEvent`, where
every row is one touchpoint: a staff member, a timestamp, and a
`SourceKey`. The complication is that `SourceKey` means something different
depending on which of four `InteractionTypeClass` values the row has (Door
Message, Workstation, Flowsheet/nursing charting, or Roster) each with
its own reference table and its own key space, so a Door `SourceKey=5` and
a Workstation `SourceKey=5` are unrelated. Doors and workstations also
carry no location column at all; only `Ref.Department` (nursing bed/room
data) is spatial.

- **`place-workstations`**: TODO: If the data is somewhere then this can be replaced.
  Workstations have no location column, so their room is inferred by nearest-anchor position interpolation.
  Each login votes for the room of that same staff member's single closest time
  Flowsheet entry (a login whose nearest entry is more than
  `WORKSTATION_MAX_ANCHOR_GAP_MINUTES` away casts no vote). A room is only
  assigned if it wins a clear majority of votes over enough logins
  (`WORKSTATION_MIN_SHARE` / `WORKSTATION_MIN_SUPPORT`); otherwise the row
  is left blank rather than guessed.

`data_wrangler.py` resolves all four interaction classes into one shared
vocabulary of room symbols (`room:<code>`) and door-edge symbols
(`door:A|B`) before any analysis happens, trying each of the following in
order until one resolves a given key:

1. a `place-workstations`-generated room-mapping CSV (`--room-mapping`),
2. a direct ref-table join (currently only available for Flowsheet, via
   `Ref.Department`),
3. a door-name-edge pair (parsed from `Ref.Door.DoorName`).

If none of those resolve a key, a namespaced fallback (`ws:<name>`,
`fs:<name>`, `roster:<name>`, or `x:na`) keeps unmapped keys distinct
rather than colliding them — see `run_report`'s `[mapping-coverage]`
section for how much of the data actually resolves to real spatial
symbols versus this fallback.

Shifts are windowed by matched Roster Start / Roster End pairs (`LinkKey`),
not a time-gap heuristic — everything outside a rostered interval is
dropped by default (`KEEP_UNROSTERED = False`).

## Usage

```sh
python data_wrangler.py --db <file.duckdb> place-workstations --out workstation_room_mapping.csv
# review/edit workstation_room_mapping.csv (blank rooms are skipped)
python data_wrangler.py --db <file.duckdb> extract --room-mapping workstation_room_mapping.csv --out trajectories.pkl

python markov_analyzer.py --data trajectories.pkl learnability-stats
python markov_analyzer.py --data trajectories.pkl irl-feasibility
python markov_analyzer.py --data trajectories.pkl compare-state-variants
```

`data_wrangler.py --db <file.duckdb> report` runs before `extract`, as a
sanity check that a database is worth analysing at all before spending
time on the rest of the pipeline. It prints four stats sections to the
terminal, writes an identical copy to `<out-dir>/duckdb_analysis.log`
(default `out-dir` is `./simulation_outputs`, override with `--out-dir`
-- **not** `--out`, which `report` ignores; `--out` only feeds
`extract`/`place-workstations`'s output _file_, `--out-dir` is `report`'s
output _directory_), and saves three plots alongside it:

```sh
python data_wrangler.py --db synthetic_amr.duckdb report --seed 0

# or elsewhere, e.g. alongside data_analysis/'s own output/ directory:
python data_wrangler.py --db synthetic_amr.duckdb report --out-dir output
```

| Stat / plot                                   | Shows                                                                                                                                                                                                                                                                   | Why it's useful                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[summary]`                                   | Total events, distinct staff, valid roster intervals, distinct rostered units, and shifts kept after the `MIN_SHIFT_EVENTS` filter.                                                                                                                                     | The first thing to check against a new file: zero events or zero valid roster intervals means extraction has nothing to work with, before spending time on anything downstream.                                                                                                                                                                                      |
| `[mapping-coverage]` + `mapping_coverage.png` | Resolved vs unresolved source keys per interaction class (Door Message / Flowsheet / Workstation), plus a TOTAL row and bar.                                                                                                                                            | Every `STATE_VARIANTS` entry depends on `location` being a genuine `room:`/`door:` symbol, not a fallback code. This is the sanity check the rest of the pipeline's numbers are conditional on. `Workstation` reading 0% is expected before running `place-workstations`; any _other_ class at 0% is a real mapping bug worth chasing before trusting anything else. |
| `[door-usage]` + `door_usage.png`             | Per-door badge-in/out counts, distinct staff, and a `boundary%` — how often that door was the _first or last_ door touchpoint of a shift vs seen mid-shift. Doors at or above `DOOR_MAIN_ENTRY_SHARE_THRESHOLD` (default 0.3) are labelled `MAIN`, the rest `internal`. | Separates doors that behave like a main entry/exit (staff arriving/leaving) from internal connectors between rooms. Useful both as a data quality check (a door with near-zero traffic may be a misparsed name). This is a heuristic inferred purely from badge timing, not a ground-truth label (see below).                                                        |
| `[example-sequence]`                          | The full trace of a randomly sampled shift (`--seed` controls which one).                                                                                                                                                                                               | A quick check that individual steps look plausible: correct time ordering, sane gaps between events, resolved (not fallback) locations. This catches pipeline bugs without needing to unpickle and inspect `trajectories.pkl`.                                                                                                                                       |
| `shift_length_histogram.png`                  | Distribution of steps across every kept shift.                                                                                                                                                                                                                          | Shows whether shift complexity is roughly uniform or has a tail. A spike at `MIN_SHIFT_EVENTS` cutoff, or an unexpected second mode, can flag a roster matching issue before trusting `learnability-stats`' test-set accuracy numbers.                                                                                                                               |

The included fake `synthetic_amr.duckdb`, every door in `[door-usage]`
reads `internal`: the generator never simulates staff badging in from outside at shift start (shifts begin
already inside, at the NurseStation), so no door is ever disproportionately
a shift boundary in this test data. Worth knowing before reading too much
into it.

- **`learnability-stats`**: the core numpy+duckdb-only feasibility numbers:
  (1) how many distinct movement paths exist,
  (2) an order-k Markov baseline's test-set accuracy, and
  (3) the conditional entropy gap between H(action) and H(action | state).
  Useful as the cheapest possible check, before fitting anything
  state variant specific: a gap near zero means the state carries
  essentially no signal, however complex it looks, so there's no point
  going further.

- **`irl-feasibility`**: fits a count-based model per state variant and
  compares its accuracy gain over two baselines (majority-class, and
  order-1 Markov). Verdict is one of: barely beats majority (don't attempt
  IRL), beats majority but not Markov (a Markov/empirical model is already
  the ceiling), or beats both baselines (proceed to IRL). This is the
  actual check for spending time on IRL. The majority/Markov
  baselines are the bar a learned reward function would need to clear to
  be worth building at all.

- **`compare-state-variants`**: runs every state definition (S1 through S7)
  and reports which is worth the effort, so a downstream IRL policy gets
  the leanest state that still captures the signal. Useful for picking a
  state representation that generalizes rather than overfits a richer
  variant that scores no better than a simpler one.

## State Variants (S1-S7)

Each variant is a different definition of "state" that a step's next
location gets conditioned on, from simplest to complex. `compare-state-variants`
sweeps all seven so you can see exactly which addition earns its keep --
each column beyond `S1` costs state space size, so it's only worth keeping
if it also buys accuracy:

| Variant                         | Adds                                                    | Why it's useful to test                                                                                                                                                              |
| ------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `S1_loc`                        | current location only                                   | The floor: is location alone predictive at all? Every other variant is judged as a lift (gain) over this.                                                                            |
| `S2_loc_time`                   | + time-of-day bucket                                    | Tests whether movement follows a daily rhythm (e.g. ward rounds cluster at certain hours) independent of who's doing it.                                                             |
| `S3_loc_time_role`              | + staff role                                            | Tests whether different roles (Nurse/HCA/Doctor) move differently even from the same place/time. Relevant if a future policy needs to be role-aware.                                 |
| `S4_loc_time_role_class`        | + interaction class (door/workstation/flowsheet/roster) | Tests whether _what kind_ of touchpoint just happened predicts what happens next, beyond location/time/role alone.                                                                   |
| `S5_prev_loc`                   | + previous location (one step of movement history)      | Tests whether movement has short-range momentum (came from A, likely to go to B). This is usually the biggest single accuracy jump, since raw location alone ignores directionality. |
| `S6_prev_loc_unit`              | + rostered unit                                         | Tests whether the ward/unit a shift belongs to matters beyond individual room history. Incase the real deployment spans multiple wards with different layouts.                       |
| `S7_prev_loc_occupancy_fatigue` | + room occupancy and a fatigue proxy                    | Tests two datalog derived environmental proxies at once. If this doesn't beat `S5`/`S6`, it's a sign the extra complexity isn't worth carrying into an IRL state.                    |

S7's two additions are both **log-derived proxies, not ground truth**,
since there's no real occupancy sensor or fatigue measurement in the data:

- **Occupancy**: how many other staff were resolved to the same room
  within `OCCUPANCY_WINDOW_MINUTES` (default 5) of this step, capped at
  `MAX_OCCUPANCY` (default 5). Computed once, across all shifts together via a
  sliding-window sweep per room. Useful as a proxy for room busyness/crowding,
  which plausibly influences where staff go next (avoiding a full bay).

- **Fatigue**: minutes elapsed since the step's own shift started,
  bucketed into four fixed bins via `FATIGUE_BUCKET_THRESHOLDS_MINUTES`
  (under 2h / 2-4h / 4-6h / 6h+). Useful as a proxy for how movement
  patterns might drift over the course of a shift (more direct routes
  early on, more idling near the end).

**Known limitation:** true multi-agent spatial density (from the separate
GPU physics engine) and genuine physiological fatigue aren't available to
this log-only pipeline at all; S7 is the closest proxy computable from
`Data.StaffLocationEvent` alone.

## Tests

```sh
pytest tests/data_analysis/ -v
```

Run from the repo root, inside the project's venv (see
[Requirements](#requirements)) — `pyproject.toml`'s
`[tool.pytest.ini_options].pythonpath` points at this directory so the
tests `import data_wrangler` / `import markov_analyzer` resolve
without needing `data_analysis` to be installed as a package.

`test_data_wrangler.py` gives exact-value coverage of `place-workstations`
(support/share/room, the nearest-anchor safeguard boundary, cross-staff
isolation) and of `_collect_door_stats` (badge/staff counts, the
first-vs-last shift-boundary split, and the single-touchpoint edge case
that a boundary share can't exceed 1.0). `test_markov_analyzer.py` covers
the pure statistical helpers
(Markov model, splits, prediction scoring), plus stdout-based checks that
`learnability-stats`, `irl-feasibility`, and `compare-state-variants` each
produce the right numbers/verdict on deterministic test data.

## Requirements

This pipeline needs `duckdb` in addition to the main project's
dependencies (`numpy` and `matplotlib`, used by `report`'s plots, already
come in transitively). Install `duckdb` via the `data-analysis` optional
dependency group:

```sh
uv sync --extra data-analysis
```

or, without `uv`:

```sh
pip install -e ".[data-analysis]"
```
