# Instructions

## Setup

Python 3.10+ required. Install:

```bash
pip install duckdb numpy
pip install jax flax optax   # optional — only for the neural-BC comparison; skip if it fights the VM
```

Place `bc_prototype.py` anywhere and note the path to the DuckDB file (below as `DB=/path/to/amr.duckdb`).

## Commands, in order

**1. Infer workstation locations** (writes `ws_crosswalk.csv` in the working directory):

```bash
python bc_prototype.py --db $DB infer-ws | tee infer_ws.log
```

**2. Learnability battery:**

```bash
python bc_prototype.py --db $DB battery --crosswalk ws_crosswalk.csv | tee battery.log
```

**3. BC rule-out** (the main result; drop `--bc` if jax isn't installed):

```bash
python bc_prototype.py --db $DB ruleout --crosswalk ws_crosswalk.csv --bc | tee ruleout.log
```

**4. State-variant sweep:**

```bash
python bc_prototype.py --db $DB sweep --crosswalk ws_crosswalk.csv | tee sweep.log
```

**5. (Bonus, if time)** repeat 2–3 with `--action next_class` appended, saving to `battery_class.log` / `ruleout_class.log`.

## What "worked" looks like

Each of 2–4 starts with a line like `loaded ~19,000 shifts, ~2,500,000 touchpoints, ~3,500 staff` followed by a `--- shared spatial frame ---` block, then the analysis. `infer-ws` ends with `[infer-ws] N/36 workstations placed`. If a command dies, send me the full traceback and the log up to that point — partial output is still useful.

## What to save

The four `.log` files plus `ws_crosswalk.csv`. Contents are aggregate statistics, room/door/workstation names, and model accuracies and no patient or staff identifiers appear in any output but please manually verify.
