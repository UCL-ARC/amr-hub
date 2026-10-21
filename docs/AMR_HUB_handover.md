<!-- markdownlint-disable MD024 MD036 -->

# AMR-HUB Analysis: Methods and Findings (Handover)

_Reference for the analysis scripts, key terms, findings, limitations and
recommended next steps._

Handover date: October 2026. Repository: `github.com/UCL-ARC/amr-hub`, folder
`learning-from-data/`. Analysis outputs are held in the TRE and are not in the
repository. Section 11 lists which scripts are in the repository and which are
not.

## 0. Summary

**Question this work addressed.** Before fitting IRL or building a worker
simulator, the project needed to know two things: (a) whether the electronic
records can be turned into worker trajectories with a defensible spatial frame,
and (b) whether those trajectories contain enough sequential structure to learn
from. This work addresses both, and leaves reusable scripts and a staged
decision path for the next stage.

**Delivered**

- Canonical preparation pipeline: raw events → rostered shift sequences
  (`canonical_events.parquet`), reused by all later analyses.
- Shared spatial frame: direct flowsheet room mapping, rule-based workstation
  inference, door-point parsing, with explicit resolved/unresolved flags.
- Descriptive analyses: activity mix, transition matrices, spatial coverage,
  door-event behaviour and a door-transition network.
- Exploratory trigram clustering of shifts.
- Held-out learnability harness: one-step prediction for three targets, with
  baselines, top-1/top-3 and unseen-state reporting.
- Free-running rollout harness, plus seed-length and context-split rollout
  comparisons.
- Optional door → ABM time-series converter (requires a manual crosswalk).
- Demo notebooks and Docker packaging.

**Established**

- Rostered sequences can be reconstructed from explicit roster boundaries.
- Flowsheets give the only direct room mapping; workstation mapping is partial
  (13 of 36 in the exploratory run); door events identify an access point but
  not direction.
- Door events are too sparse and uneven to be the main movement signal; they
  are kept as context.
- Activity-class sequences have strong local structure. One-step top-1 rises
  from about 76% (majority baseline) to 88.6% with current + previous class,
  roughly halving the error rate (24% → 11.4%). Adding time, role and roster
  unit adds about 0.1 percentage points for this target.
- Shift clusters look more like a continuum than distinct groups; `k = 3` is an
  exploratory partition only.

**Open**

- Spatial learnability figures and rollout scores are not reproduced in this
  note (see Sections 7–9 for where they are produced).
- Staff-held-out validation, an event-timing/dwell model, and IRL have not been
  done. Section 12 sets out the order.

## 1. Overall analysis pipeline

| Stage                   | Purpose                                                                                  | Main output / decision                                          |
| ----------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Data and roster QA      | Turn raw electronic records into ordered shift sequences; check source coverage.         | Canonical event sequence and data-quality summaries.            |
| Spatial mapping         | Assign room labels where defensible; avoid turning uncertain events into invented rooms. | Room crosswalks and resolved/unresolved flags.                  |
| Descriptive exploration | Measure activity mix, transition patterns, spatial coverage and door-event behaviour.    | Transition matrices, shift summaries, coverage figures.         |
| Trigram clustering      | Group shifts with similar short activity-pattern proportions.                            | Exploratory clusters, not assumed to be true behavioural types. |
| Learnability            | Test whether next activity or room can be predicted on held-out shifts.                  | Top-1/top-3 accuracy, unseen-state rate, entropy summaries.     |
| Free-running rollouts   | Feed model predictions back into the sequence and check whether it stays plausible.      | Rollout accuracy, correct prefix, composition deviation.        |
| Future simulation / IRL | Use validated states and trajectories to learn rewards and generate simulated behaviour. | Not started; depends on the checks in Section 12.               |

The stages are ordered deliberately: first establish what the electronic records
can represent, then test sequential structure and predictive usefulness, and
only then move toward a full worker simulation. Each stage gates the next, so
IRL is not fitted on a state representation that has not been shown to carry
signal.

## 2. Shared data preparation and key terms

The canonical dataset is built by `generate_learnability_analysis.py`
(Section 7), which writes `canonical_events.parquet`.

### Rostered sequences

- Event and staff counts are produced by the progress report inside the TRE
  and are not reproduced here.
- Roster Start and Roster End for the same staff member are paired using
  `LinkKey`; the latest start and latest end for each pair are used. An
  interval is valid only if both records exist and the end is after the start.
  Timestamped events inside valid intervals are assigned to shifts.
- If eligible roster intervals overlap, an event is assigned once, to the
  eligible shift with the latest start time. The number of overlapping
  intervals and of events matching more than one interval are written to
  `quality_summary.csv`. The progress report, activity exploration and door
  exploration do not apply this rule; they count such an event in each
  interval.
- Roster boundary events define the shift interval but are not treated as
  activity events.
- The current extract has **two roster units**. Role comes from the staff
  reference table; missing role/unit values are coded as unknown.
- Staff and shifts get sequential pseudonymous IDs (`staff_id`, `shift_id`);
  raw staff identifiers stay inside DuckDB. Absolute event timestamps are left
  out of the exported canonical table unless `--include-timestamps` is set.

### Spatial mapping

| Event source     | Mapping method                                                                                                                                                                        | Interpretation / limitation                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Flowsheet        | Join the event `SourceKey` to `Ref.Department.DepartmentKey` and take `RoomName`; stored as `room:<NAME>` after trimming, collapsing whitespace and upper-casing, e.g. `room:ROOM_A`. | The most direct room mapping in this workflow.                                                                                     |
| Workstation      | Infer a room from the same staff member's flowsheet activity within ±10 minutes; require support ≥ 20 and dominant-room share ≥ 0.60.                                                 | Only confident mappings are used. Exploratory run: 13 of 36 workstations mapped; 23 unresolved.                                    |
| Door Message     | Extract a recognisable code from `DoorName`; stored as a door point, e.g. `doorpoint:XX00A#DOORKEY:000`.                                                                              | Identifies the access point, not the side, direction or destination room. Exploratory run: 12 of 13 doors had a recognisable code. |
| Unresolved event | Kept as an electronic event; an unknown workstation is not treated as a physical room.                                                                                                | Spatial analyses use only resolved room/door-point observations.                                                                   |

Support is the number of flowsheet observations by the same staff member
within the window of a workstation event; share is the fraction of those
naming the most common room. The inference runs in `generate_progress_report.py`
(`--window-min`, `--min-support`, `--min-share`; defaults 10, 20 and 0.60) and
writes `/outputs/ws_crosswalk.csv`. Later analyses read that file and use only
rows with a room filled in.

### Terms used throughout

| Term                              | Meaning                                                                                                                                                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Canonical dataset**             | The standardised, cleaned table used as the common input to later analyses.                                                                                                                                                     |
| **Activity class**                | One of three event classes: Flowsheet (FS), Workstation (WS), Door Message. Roster events are excluded.                                                                                                                         |
| **Resolved location**             | An event with a defensible room or door-point symbol. It does not guarantee the worker's exact physical position.                                                                                                               |
| **State**                         | Information describing the worker's current situation, such as current/previous activity class or room.                                                                                                                         |
| **Context**                       | Additional conditions such as time bucket, role or roster unit.                                                                                                                                                                 |
| **Time bucket**                   | Six-hour band of the event timestamp: `00–06`, `06–12`, `12–18`, `18–24` (hour of day divided by 6, rounded down). Computed once in the canonical dataset, so the learnability and advanced-demo analyses use the same buckets. |
| **Markov / first-order model**    | Predicts the next event from the current event or location only.                                                                                                                                                                |
| **Trigram**                       | An overlapping window of three consecutive event classes, such as `WS → FS → WS`.                                                                                                                                               |
| **Shift-held-out**                | Whole shifts are assigned to train or test. A staff member may still have different shifts in both sets.                                                                                                                        |
| **Top-1 / top-3**                 | Top-1 is correct if the highest-ranked prediction matches; top-3 is correct if the actual target is among the three highest-ranked.                                                                                             |
| **Unseen-state fraction**         | Share of test examples whose exact state never occurred in training; indicates sparsity and how often the fallback is used.                                                                                                     |
| **Entropy / information gain**    | Entropy measures uncertainty in outcomes; information gain measures how much conditioning on a state reduces it.                                                                                                                |
| **Free-running rollout**          | Generating a sequence recursively, feeding predictions back in instead of resetting to the true next event.                                                                                                                     |
| **Total-variation (TV) distance** | Difference between generated and observed activity-class proportions. Zero means identical; lower is better.                                                                                                                    |
| **IRL**                           | Inverse reinforcement learning: infer a reward function that explains demonstrated trajectories. A later stage; the count-based models here do not do this.                                                                     |

## 3. Initial progress report / data-quality analysis

**Script:** `amr_hub_progress_report/generate_progress_report.py`

### Method

- Reconstruct valid roster intervals, calculate shift duration and coverage,
  and summarise staff, shifts, roster units and date range. Shifts with at
  least three activity events are counted separately.
- This script pairs each roster interval from the earliest start and latest
  end, and counts activity events per interval independently, so an event that
  falls inside two overlapping intervals is counted in both. Its shift counts
  are therefore not identical to the canonical dataset's.
- Audit door and workstation references; infer workstation rooms from nearby
  same-staff flowsheet observations.
- Apply the default workstation rule: at least 20 nearby observations
  (**support**) and at least 60% agreement on the dominant room (**share**).
- Export summary CSVs and figures: overall scale, roster-unit counts and
  durations, door identifiers, workstation mapping status, spatial coverage and
  an example sequence.

### Findings

- The records can be converted into ordered activity sequences using explicit
  roster boundaries.
- Flowsheet events provide the most direct room mapping; workstation
  inference works for a subset only.
- Door references mostly have a recognisable code, but the code does not give
  door direction.
- Spatial coverage is a data-quality indicator, not a behavioural trait.

## 4. Door-specific exploration and door-transition network

**Scripts:** `amr_hub_door_jupyter_existing/door_exploration_existing_jupyter.py`
and the notebook `AMR_HUB_Door_Exploration.ipynb`, which calls it. The
separate network figure script, `door_network_svg.py`, is not in the
repository.

### Method

- For each shift, count Door Message events and compute door interactions per
  rostered hour to adjust for shift length.
- Compare door counts with shift duration; compute minutes between consecutive
  door events and the number of non-door records (flowsheet, workstation)
  between them.
- Build a door-to-door transition count matrix from successive door events,
  written as `door_transition_matrix.csv` and a heatmap. Doors are labelled by
  parsed code and door key. The network figure showed frequent transitions as
  stronger links.
- The default run does not deduplicate messages (`--door-dedupe-seconds 0`); a
  Door Message is an electronic proxy, not a verified one-to-one physical door
  pass.

### Findings

- Many shifts have very few recorded door interactions; the lowest bin of the
  door-count histogram was very large.
- Door data describe relationships between instrumented access points, but are
  too sparse or unevenly captured to be the sole measure of movement or the
  main clustering variable.
- A network edge means one observed door interaction followed another. It does
  not show a direct physical route, direction through the door, or floor-plan
  proximity.

**Decision:** keep door events as supporting context; use the broader event
stream and resolved locations for the main sequence analyses.

## 5. General activity and transition exploration

**Script:** `amr_hub_activity_exploration/generate_activity_exploration.py`.
This is the version without the trigram stage; the trigram-enabled version is
not in the repository.

### Method

- Compute events per hour, activity-class composition per shift, number of
  distinct resolved locations, and resolved-location changes per hour.
- Estimate activity-class transition counts and row-normalised probabilities,
  `P(next class | current class)`, pooled and per shift.
- Estimate transitions between successive resolved locations. Consecutive
  repeats of the same location are collapsed for the location-change view;
  unresolved observations are skipped. The heatmap shows the 20 locations
  involved in the most transitions (`--top-locations`).
- Plot the share of events with resolved locations, and compare the electronic
  event rate with the location-change rate.

### Findings

- The activity-class sequence shows strong local persistence, particularly
  `WS → WS` and `FS → FS`. This is non-random sequence structure and is what
  motivated the formal learnability test.
- Spatial transitions describe successive resolved observations, not a complete
  physical route. Unresolved events can hide intermediate activity or movement.
- Resolved-event coverage and distinct-location counts must be read alongside
  mapping quality: low apparent spatial breadth can reflect missing mappings
  rather than restricted movement.

## 6. Three-event motifs and exploratory shift clustering

**Scripts:** the trigram-enabled version of `generate_activity_exploration.py`
(not in the repository); follow-up
`amr_hub_cluster_meeting/generate_cluster_meeting.py`

### Method

The first five points describe the trigram stage, which is not in the
repository and could not be checked against code.

- Create overlapping three-event windows. For example, `WS → WS → FS → FS`
  produces `WS → WS → FS` and `WS → FS → FS`.
- Represent each shift by the proportions of its trigram patterns rather than
  raw counts, so longer shifts do not dominate.
- Require at least 10 trigram windows for a shift to be included.
- Fit K-means on the trigram-proportion vectors for `k = 2` to `6` and compare
  with the Calinski–Harabasz score. A 2-D embedding is for visualisation only,
  not the clustering input.
- Inspect cluster sizes, mean trigram profiles, top motifs, and the
  distribution of role and roster unit across clusters.
- The follow-up script reads the trigram stage's output files
  (`per_shift_class_trigram_features.csv`, `trigram_cluster_assignments.csv`,
  `trigram_cluster_top_patterns.csv`) and the per-shift transition file from
  activity exploration. It draws a 2-D embedding from a singular value
  decomposition of the trigram features, and computes within-cluster transition
  matrices and a descriptive transition-concentration measure: for each current
  class, take the most common next class and measure how concentrated
  transitions are around it. It does not use role or roster unit.

### Findings

- Among `k = 2–6`, **`k = 3`** had the highest Calinski–Harabasz score. This
  supports it as an exploratory partition, not as evidence of exactly three
  behaviour types.
- In 2-D the clusters overlap and look more like a continuum than separated
  groups.
- Differences between clusters are largely quantitative (how often classes
  persist versus switch) rather than distinct behavioural patterns.
- The transition-concentration measure is descriptive and in-sample; it is not
  held-out prediction accuracy.

**Interpretation:** use clusters as hypotheses or optional stratification, not
as established staff types.

## 7. Learnability analysis: one-step held-out prediction

**Script:** `amr_hub_learnability_bundle/generate_learnability_analysis.py`

Reusable outputs: `canonical_events.parquet`, `canonical_shift_summary.csv`,
`spatial_location_map_used.csv`, `quality_summary.csv`,
`pooled_learnability.csv`, `subgroup_learnability.csv`,
`entropy_summary.csv`, `LEARNABILITY_REPORT.md`.

### Method

- 80% train / 20% test split by whole shift, fixed seed `20260813`. No shift
  appears in both sets; this is not a staff-held-out split.
- Three targets:
  1. **Next event class:** the next event's activity class.
  2. **Next room observation:** the next resolved room observation, keeping
     repeated same-room observations.
  3. **Next room change:** the next _different_ room, after collapsing
     consecutive repeats. This separates movement from staying in a room:
     target 2 is partly a measure of dwell, target 3 is not.
- Door points stay in the canonical dataset but are not treated as rooms in
  targets 2 and 3.
- Compare a global majority baseline with count-based conditional models. For
  event class, the state grows from current class, to current + previous class,
  to adding time bucket and role, and finally roster unit. Spatial models add
  previous room, time, role, current activity class and roster unit in the
  same way.
- For each exact state, count next-target outcomes and predict the most
  frequent.
- If a test state was unseen in training, fall back to the global top-3
  ranking, so no test example is dropped.
- Report top-1, top-3 and unseen-state fraction. Entropy summaries are
  descriptive (in-sample), not held-out validation.
- For both spatial targets, compare majority, current-room Markov and
  full-context models within role and roster-unit subgroups that have at least
  30 distinct shifts and 100 test pairs.

### Findings: next activity class

| Model                                    | Top-1 |
| ---------------------------------------- | ----- |
| Global majority baseline                 | ~76%  |
| Current + previous class                 | 88.6% |
| Full context (+ time, role, roster unit) | 88.7% |

- The majority baseline is high because one class dominates. The relevant
  measure is the error rate: it falls from about 24% to 11.4% with the previous
  event, i.e. roughly halved.
- Immediate local history explains most of the gain; richer context adds about
  0.1 percentage points for this target.
- This does not carry over to spatial prediction: it does not show that role,
  time or roster unit are irrelevant for where staff go next.

### Findings: spatial targets

Spatial results are written to `pooled_learnability.csv` in the TRE and are
not reproduced in this note.

## 8. Free-running rollout analysis

**Notebook:** `AMR_HUB_Free_Running_Rollout.ipynb`. Reads
`learnability_analysis/canonical_events.parquet` and writes to
`learnability_analysis/rollout_inspection/`. The advanced demo (Section 9) runs
the same policy comparison with a seed length of 2.

### Method

- Reuse `canonical_events.parquet` and the same whole-shift 80/20 split
  (seed `20260813`).
- Seed each held-out shift with its first two true event classes; predict the
  third, feed the prediction back into the state, and continue to the end of
  the shift.
- Compare majority, current-class Markov, current + previous class, time/role
  and full-context count policies.
- Metrics:
  - **Rollout accuracy** after the seed.
  - **Exact generated-suffix match.**
  - **Correct prefix length** before the first error.
  - **Unseen-state fraction.**
  - **TV distance** between generated and actual class proportions.
- Conditional rollout: role and roster unit are given, and the time bucket is
  taken from the held-out event timing. The model generates event classes, not
  timestamps or dwell times.

### What this tests

- One-step prediction always receives the true current event; a free-running
  rollout does not. This tests whether errors compound once the model
  conditions on its own output.
- A high one-step score alone does not establish that a model generates
  plausible long sequences.

### Results status

The summary table is not reproduced here. Re-executing the notebook, or the
advanced demo, in the TRE regenerates it.

## 9. Advanced demo: seed-length and context-split rollouts

**Script:** `amr_hub_advanced_demo/generate_advanced_demo_analysis.py`. Reads
`canonical_events.parquet` from the learnability output folder.

### Method

- Run rollouts with seed lengths of **1, 2, 3, 5 and 10** real events to test
  how much observed history improves generated sequences. Same split and seed
  (`20260813`) as Section 7.
- Global policies for all five state models (majority to full context).
  Segment-specific policies, fitted separately by time bucket, role or roster
  unit, use the current + previous class state; a time-bucket policy with the
  full-context state is also run.
- A segment-specific policy is only fitted if its training segment has at
  least **1,000 pairs**; otherwise it falls back to the global policy.
- Produce Markov transition matrices globally and by time bucket (`00–06`,
  `06–12`, `12–18`, `18–24`), role and roster unit, for segments with at least
  1,000 training pairs.
- Report rollout accuracy, exact suffix match, correct prefix, unseen-state
  fraction and class-composition TV distance.

### Interpretation and results status

- This tests whether time-, role- or unit-specific policies improve sequence
  continuation or class-mix realism compared with a pooled policy.
- The time bucket is supplied from held-out timing, so event timing is not
  generated. This is not yet an autonomous simulator.
- Outputs: `rollout_summary_by_seed.csv`, `rollout_per_shift_by_seed.csv`,
  `rollout_examples.csv`, `markov_transition_probabilities_by_segment.csv`,
  `advanced_demo_summary.csv`, six PNG figures, `ADVANCED_DEMO_BRIEF.md` and
  `IRL_REWARD_DESIGN_NOTES.md`. Results are not reproduced here.

## 10. Door-to-ABM time-series conversion

**Scripts:** `amr_hub_door_to_abm_timeseries.py`; supporting parser
`amr_hub_door_matching_only.py`. Neither is in the repository.

### Method

- Read `DoorKey`/`DoorName` from the reference table and parse a door code.
- Generate a door-crosswalk template (source door key, building, floor, room,
  door ID) for a user to complete before conversion.
- Join door events to the crosswalk and export rows with a complete mapping in
  an ABM-oriented schema: worker ID, timestamp, location, event type, patient
  ID, door ID, content type.
- Export conversion diagnostics and coverage counts.

### Notes

- This is an optional downstream path. It needs a manually completed crosswalk
  and does not infer the room on either side of a door or travel direction.
  The crosswalk has not been completed as of this handover.
- It is separate from the learnability spatial map, which keeps door
  interactions as door points.
- The parser is deterministic; no matching probability is claimed.
- The same door-code pattern and `doorpoint:<code>#DOORKEY:<key>` format are
  implemented in the simulation package as
  `amr_hub_abm.data_ingestion.door_mapping.read_door_mapping()`, which reads
  `Ref.Door` from a DuckDB file.

## 11. Demo notebooks and packaging

- `AMR_HUB_RISE_Demo.ipynb` assembled existing figures and tables into a
  narrative from raw events to learnability and rollouts. It is a presentation
  layer, not a new model, and is not in the repository.
- `AMR_HUB_Advanced_RISE_Demo.ipynb` displays the advanced-demo figures and
  the IRL design notes (also written by the script as `ADVANCED_DEMO_BRIEF.md`
  and `IRL_REWARD_DESIGN_NOTES.md`); it is not an IRL fit.

### Docker bundles in `learning-from-data/`

| Folder                                                                                                  | Image                      | Input                                     | Status                                                                                      |
| ------------------------------------------------------------------------------------------------------- | -------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------- |
| `amr_hub_progress_report/`                                                                              | `amr-bc-jupyter-report`    | DuckDB database                           | Full analysis. Also serves `AMR_HUB_BC_Triage.ipynb` in JupyterLab.                         |
| `amr_hub_door_jupyter_existing/`                                                                        | none                       | DuckDB database                           | Full analysis. Copied into `/outputs` and run inside the JupyterLab container above.        |
| `amr_hub_activity_exploration/`                                                                         | `amr-activity-exploration` | DuckDB database                           | Full analysis, without the trigram stage.                                                   |
| `amr_hub_cluster_meeting/`                                                                              | `amr-cluster-meeting`      | Trigram-stage outputs                     | Full follow-up, but its inputs come from the trigram stage, which is not in the repository. |
| `amr_hub_learnability_bundle/`                                                                          | `amr-learnability`         | DuckDB database                           | Full analysis; builds `canonical_events.parquet`.                                           |
| `amr_hub_advanced_demo/`                                                                                | `amr-advanced-demo`        | `canonical_events.parquet`                | Full analysis.                                                                              |
| `activity_exploration/`, `sequence_clustering/`, `learnability/`, `rollout_analysis/`, `door_matching/` | as folder name             | `canonical_events.parquet` or `doors.csv` | Simplified. See below.                                                                      |

The Dockerfiles for activity exploration, cluster meeting and the advanced demo
were reconstructed from the build history of the images used in the TRE. The
exported image `.tar` files are not committed; rebuild them from the
Dockerfiles and import them through the airlock.

The five simplified images are not exact reproductions of the analyses above:

- They expect `iclass` and `event_time` columns, whereas the canonical dataset
  from Section 7 has `interaction_class` and omits `event_time` by default. The
  columns must be renamed (and the dataset exported with
  `--include-timestamps`) before they run on it.
- The learnability and rollout images split shifts 80/20 with seed `42`, not
  `20260813`.
- Clustering applies no minimum number of trigram windows.
- Learnability reports top-1 and unseen fraction only, with no top-3 and no
  subgroup analysis.
- Rollout uses no 1,000-pair minimum for segment policies, and reports no
  exact suffix match or unseen-state fraction.
- `door_matching` parses codes but does not build door points or a crosswalk.
- The simplified activity exploration measures shift length from first to last
  event rather than from the roster interval, and writes each shift's start and
  end timestamps to `shift_activity_features.csv`.

## 12. Limitations and recommended next steps

### Limitations

- Electronic events are proxies for work activity, not a complete record of
  clinical actions or movement.
- Door records are sparse/uneven and carry no direction. Spatial sequences omit
  unresolved observations and may hide intermediate movement.
- Shift-held-out evaluation can include the same staff in train and test. A
  staff-held-out split would be stricter.
- State-rich models become sparse; unseen-state fractions and fallback
  behaviour matter alongside accuracy.
- Predictive association is not causation, and predictive importance of a
  state variable is not the same as its reward weight in IRL.

### Recommended order

1. **Regenerate missing tables** (rollout notebook, spatial rows of
   `pooled_learnability.csv`). Cheap; no new code.
2. **Next-room-change learnability**, including role/unit subgroups. This is
   the result that decides whether movement has conditional structure worth
   modelling.
3. **Room-change rollouts**, to check that structure survives free-running
   generation.
4. **Staff-held-out sensitivity test**, to check results are not driven by
   individuals seen in training.
5. **Decide on IRL.** If context adds little beyond the previous room, an
   empirical transition kernel plus dwell times is the simpler simulator
   input; if role/time clearly modulate movement, IRL over those features is
   justified.
6. **Add an event-timing/dwell-time model** in either case, since the current
   models generate sequences but not timing.

## 13. Findings at a glance

| Area                  | Finding                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Data preparation      | Rostered event sequences can be reconstructed; two roster units in the current extract.                            |
| Spatial coverage      | Flowsheet room mapping is direct; workstation mapping is partial (13/36); door codes identifiable for 12/13 doors. |
| Door exploration      | Too sparse/uneven to be the main movement or clustering signal; kept as context.                                   |
| Activity transitions  | Strong local persistence, especially `WS → WS` and `FS → FS`.                                                      |
| Trigram clustering    | `k = 3` best by Calinski–Harabasz among `k = 2–6`, but the data look like a continuum.                             |
| Next activity class   | Top-1 ~76% (majority) → 88.6% (current + previous class) → 88.7% (full context); error rate roughly halved.        |
| Spatial learnability  | Harness built and run; figures are in `pooled_learnability.csv` in the TRE and are not reproduced here.            |
| Free-running rollouts | Harness and metrics defined; scores need regenerating in the TRE.                                                  |
| IRL                   | Not fitted. Current work screens the state/context variables and trajectory structure that IRL would use.          |

## Source scripts / notebooks

In the repository (paths relative to `learning-from-data/`):

- `amr_hub_progress_report/generate_progress_report.py`: data and spatial QA.
- `amr_hub_door_jupyter_existing/door_exploration_existing_jupyter.py` and
  `AMR_HUB_Door_Exploration.ipynb`: door analysis.
- `amr_hub_activity_exploration/generate_activity_exploration.py`: activity,
  transitions, spatial changes.
- `amr_hub_cluster_meeting/generate_cluster_meeting.py`: cluster profiles and
  transition concentration.
- `amr_hub_learnability_bundle/generate_learnability_analysis.py`: canonical
  dataset, held-out one-step prediction and subgroup analysis.
- `amr_hub_advanced_demo/generate_advanced_demo_analysis.py`: seed-length and
  context-split rollouts.
- `AMR_HUB_Free_Running_Rollout.ipynb`: recursive class-sequence rollout.
- `AMR_HUB_Advanced_RISE_Demo.ipynb`: advanced-demo figures and IRL notes.
- `amr_hub_progress_report/AMR_HUB_BC_Triage.ipynb`: an earlier DuckDB triage
  and behaviour-cloning prototype. It treats doors as edges (`door:A|B`)
  rather than door points and uses seed `0`, so its results are not comparable
  with Section 7.
- The five simplified Docker analyses (Section 11).

Not in the repository:

- The trigram-enabled version of `generate_activity_exploration.py`
  (trigrams, K-means clustering).
- `door_network_svg.py`: door network figure.
- `amr_hub_door_to_abm_timeseries.py`, `amr_hub_door_matching_only.py`: door
  crosswalk and ABM export.
- `AMR_HUB_RISE_Demo.ipynb`.

### Running the analyses

Images are built outside the TRE, exported with `docker save`, imported
through the airlock, and run inside the TRE with the database folder mounted
read-only at `/data` and an output folder at `/outputs`. Scripts that read the
database pick up the only `.db`/`.duckdb` file in `/data`, or take `--db`.

| Script                                 | Input                                                              | Outputs (under `/outputs/`)                                                                                           | How to run                                                                                                                              |
| -------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `generate_progress_report.py`          | Database                                                           | `progress_report/`: six CSVs, nine PNGs, `REPORT_INDEX.txt`; `ws_crosswalk.csv` (reused unless `--refresh-crosswalk`) | Image `amr-bc-jupyter-report` with `--entrypoint /app/run_progress_report.sh`                                                           |
| `AMR_HUB_BC_Triage.ipynb`              | Database                                                           | Printed diagnostics; optional crosswalk CSV                                                                           | Same image, default entrypoint (JupyterLab)                                                                                             |
| `door_exploration_existing_jupyter.py` | Database                                                           | `door_exploration/`: five CSVs, six SVGs                                                                              | Copy into `/outputs` and run from a JupyterLab terminal or the notebook; `--door-dedupe-seconds`                                        |
| `generate_activity_exploration.py`     | Database; `ws_crosswalk.csv` if present                            | `activity_exploration/`: shift features, class and location transition CSVs, eight PNGs                               | Image `amr-activity-exploration`; `--top-locations`                                                                                     |
| `generate_learnability_analysis.py`    | Database; `ws_crosswalk.csv` if present                            | `learnability_analysis/`: canonical dataset, learnability CSVs, five SVGs, report                                     | Image `amr-learnability` (or `Dockerfile.reuse` on top of the activity image); `--seed`, `--min-group-shifts`, `--min-group-test-pairs` |
| `generate_advanced_demo_analysis.py`   | `learnability_analysis/canonical_events.parquet`                   | `advanced_demo_analysis/` (Section 9)                                                                                 | Image `amr-advanced-demo`; `--seed-events`, `--min-segment-train-pairs`                                                                 |
| `AMR_HUB_Free_Running_Rollout.ipynb`   | `learnability_analysis/canonical_events.parquet`                   | `learnability_analysis/rollout_inspection/`: summary, per-shift and example CSVs                                      | JupyterLab, after the learnability analysis                                                                                             |
| `generate_cluster_meeting.py`          | Trigram-stage outputs in `activity_exploration/`                   | `cluster_meeting/`: embedding, transition and concentration CSVs, SVGs, Markdown summary                              | Image `amr-cluster-meeting`; needs the trigram stage, which is not in the repository                                                    |
| Simplified images                      | `canonical_events.parquet` (after renaming columns) or `doors.csv` | One folder per image                                                                                                  | `docker build -t <name> <folder>/`, then `docker run` with `/data` and `/outputs` mounted                                               |

Run order: progress report (creates the workstation crosswalk) → activity
exploration and learnability → advanced demo.

### Checking outputs before export from the TRE

Several outputs are record-level or contain reference names, and need
disclosure checks before anything leaves the TRE:

- **Event- or shift-level (keep in the TRE):** `canonical_events.parquet`,
  `canonical_events_sample.csv`, `canonical_shift_summary.csv`,
  `shift_activity_features.csv`, the per-shift transition files,
  `shift_door_activity.csv`, `door_episodes.csv`,
  `rollout_per_shift_by_seed.csv`, `rollout_examples.csv`, the rollout
  notebook's `next_class_rollout_per_shift.csv` and
  `next_class_rollout_examples.csv`, the cluster
  embedding CSV, and the progress report's `example_sequence.csv`.
- **Reference names:** `spatial_location_map_used.csv`, location transition
  files, `door_counts.csv`, `door_transition_matrix.csv`, and the progress
  report's `doors.csv` and `workstations.csv` contain room names or door codes
  and keys.
- **Small cells and subgroups:** subgroup thresholds count shifts or pairs,
  not staff, so a role or unit row can pass the threshold with fewer than 10
  staff. Check staff counts in `subgroup_learnability.csv` and the role/unit
  rows of `markov_transition_probabilities_by_segment.csv`, and check door and
  location transition matrices for cells below 10, before export.
- `overall_summary.csv` contains the first and last event timestamps.
