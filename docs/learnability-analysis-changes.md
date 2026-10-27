# Learnability analysis: what changed from the earlier prototypes

This note compares the learnability analysis in
`learning-from-data/legacy/amr_hub_learnability_bundle/` with the two earlier
versions of the same idea:

- my behaviour-cloning prototype, `bc-prototype.py` (July 2026, branch
  `yio/rl-preparation`), and
- Nicolin's `python-code/data_analysis/` scripts (`data_wrangler.py`,
  `markov_analyzer.py`, `make_synthetic_db.py`; August 2026, on `main`).

Nicolin's wrangler keeps most of the prototype's set-up: four time bands, at
least three events per shift, dropping unrostered events, door names split into
"A | B" edges, the `ws:` / `fs:` / `door:` fallback labels, and the workstation
voting rule (10-minute window, 20 votes, 60% share). The voting idea itself
came from Keiran. So the comparison below is mostly between that shared earlier
design and what I changed for the learnability analysis.

## What changed and why

| Earlier approach (prototype and Nicolin's scripts)                                                                                                     | Learnability analysis                                                                                                                               | Why                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Doors stored as edges between the two rooms in the door name ("A \| B")                                                                                | Doors stored as door points: the parsed code plus the door key                                                                                      | A door message doesn't tell us which side someone was on, so an edge implies more than the data gives us. A door point keeps what we actually know (which door) without guessing a direction, and the door key stops two doors with the same code being merged.          |
| One "next location" target, where a location can be a room, a door or an unresolved name like `ws:WOW Cart 1`                                          | Three separate targets: next activity class, next room (repeats kept), next room change (repeats collapsed)                                         | If unresolved names count as locations, the model is partly learning where our mapping has gaps. And next room with repeats mostly picks up people charting several times in the same room. I wanted next room change on its own so I could look at movement, not dwell. |
| Train/test split by individual event pairs in `learnability-stats` and `compare-state-variants`; by shift in `irl-feasibility`                         | Always split by whole shift, with a fixed seed (`20260813`)                                                                                         | Events next to each other in a shift are very alike, so splitting pairs puts bits of the same shift on both sides and makes the scores look better than they are. Splitting by shift everywhere keeps the numbers honest and comparable.                                 |
| Markov baseline built on previous actions but looked up with the current location, so for `next_class` it mostly misses and falls back to the majority | Markov baseline built on the same sequence it predicts, for every task                                                                              | I hit this in the triage notebook and fixed it there ("Revised rule-out"). The baseline has to be right, otherwise every comparison against it is off.                                                                                                                   |
| Unseen states smoothed (Laplace, α = 0.5)                                                                                                              | Unseen states fall back to the overall top-3, and the unseen-state fraction is reported                                                             | I'd rather see how often the model meets a situation it never saw in training than have smoothing hide it. A high unseen fraction tells me the state is too detailed for the data.                                                                                       |
| Overlapping shifts: an event goes to the first matching shift, without a count                                                                         | The event goes to the shift with the latest start, and the number of overlaps and affected events is reported                                       | This way nothing is counted twice, and the data issue shows up in the outputs instead of being absorbed silently.                                                                                                                                                        |
| Pickled Python objects holding raw staff IDs and patient keys                                                                                          | DuckDB/SQL pipeline exporting `canonical_events.parquet` with pseudonymous staff and shift IDs, no timestamps by default, and a yes/no patient flag | It had to run on the full extract inside the TRE, be repeatable, and be safe to work with. I didn't want patient keys or raw staff IDs sitting in an intermediate file.                                                                                                  |
| One pooled result                                                                                                                                      | Role and roster-unit subgroups, only where there are at least 30 shifts and 100 test pairs; entropy kept as descriptive                             | I wanted to check whether context matters within groups without reading too much into very small ones, and to keep in-sample numbers separate from held-out ones.                                                                                                        |

One difference is a choice rather than a fix. For workstation placement, the
progress report counts every flowsheet entry within ±10 minutes of a login as a
vote, while Nicolin's wrangler gives each login one vote for its nearest
flowsheet. I went with all the flowsheet activity around the login and let the
20-vote and 60% thresholds filter out weak evidence; nearest-only is less noisy
per login. Both are reasonable.

## What I left out, and why

Nicolin's scripts add occupancy (other staff in the same room within five
minutes), fatigue (time into the shift) and perplexity. I didn't add them to
the learnability analysis:

- **Occupancy and fatigue.** I didn't have a model of how either should change
  where staff go next, so I had no basis for choosing how to encode them (which
  time window, which bands, whether they act on their own or with role). Adding
  features without a reason also makes the state more detailed, which raises
  the unseen-state fraction and makes any gain hard to interpret. They're worth
  testing once there's a clear hypothesis behind them.
- **Perplexity.** It depends on the smoothing, which I'd taken out on purpose.
  Top-1, top-3 and the unseen-state fraction answered the question I was asking.
  Perplexity could be added later as a held-out likelihood, which the IRL
  review also suggests.

## What Nicolin's scripts add

Besides the features above, they include a door-usage report that separates
main entrances from internal doors, and a synthetic database generator.
The generator produces a database in the same schema as the TRE extract,
and the legacy progress report and learnability scripts run on it without
changes (see `learning-from-data/README.md`).
