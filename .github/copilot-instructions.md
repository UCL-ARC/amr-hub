# Copilot instructions for AMR-Hub

AMR-Hub is an agent-based model (ABM) simulating hospital workflows, human
movement, and antimicrobial resistance (AMR) transmission in hospitals. It is
built around a Trusted Research Environment (TRE)-centric workflow: sensitive
healthcare data stays inside the TRE, while the simulation engine here is
open-source. **Never commit real patient/hospital data, secrets, or large
files** — only synthetic fixtures under `tests/inputs/`.

All Python code lives under `python-code/`; the repo-root `Makefile`
auto-detects this and `cd`s into it, so commands below can be run from either
the repo root or `python-code/`.

## Build, test, and lint

Dependency management uses `uv` exclusively (no pip/poetry). Set up once with
`make install-dev` (repo root) or `curl -LsSf https://astral.sh/uv/install.sh | sh && uv sync --group dev` (from `python-code/`).

- **Run the full test suite**: `make test` (syncs the `test` dependency group,
  then runs `pytest tests --cov=src --cov-report=term-missing`).
- **Run a single test**: there's no Makefile target for this — after deps are
  synced (e.g. via `make test`/`make install-dev`), run pytest directly:
  `cd python-code && uv run pytest tests/test_agent.py::test_agent_initialization -v`.
- **Lint/format**: `make lint` (= `make format` + `make type-check`).
  - `make format` runs `ruff format .` and `ruff check --fix .` (mutates files).
  - `make type-check` runs `mypy src/`. Note: this currently reports ~100
    pre-existing `import-untyped` errors across the codebase (missing
    `py.typed`/stubs) — don't try to fix these unless that's the task at hand.
- **All pre-commit hooks** (ruff, ruff-format, markdownlint, mypy, prettier,
  toml-sort, etc.): `make pre-commit`.
- **Docs** (MkDocs + mkdocstrings, numpy docstring style): `make docs` builds
  to `python-code/site/`; `make docs-serve` serves with live reload.
- CONTRIBUTING.md requires `make pre-commit` and `make test` to both pass
  before opening a PR.

CI mirrors this: `.github/workflows/tests.yml` runs `tox run` (pytest+cov),
`linting.yml` runs `pre-commit run --all-files`, `coverage.yml` uploads to
Codecov, `docs.yml` builds and deploys MkDocs to GitHub Pages. All run with
`working-directory: python-code`.

## Architecture

The simulation is data-driven, assembled by
`simulation_factory.create_simulation()` from a YAML config (e.g.
`tests/inputs/simulation_config.yml`, pointing at `buildings_path` and
`location_timeseries_path`) plus a CSV of healthcare-worker (HCW) location
events. This produces a `Simulation` (`simulation.py`), which owns:

- **`space/`** — the spatial hierarchy: `Building` → `Floor` → `Room`, plus
  `Wall`, `Door` (connects two rooms), `Content` (beds/chairs/workstations),
  and `Location`. `space/space.py::SpatialQuery` is the CPU engine for
  geometry lookups/movement and is passed into agent/task code as an explicit
  `engine` argument (not read off the agent) — this is what allows swapping
  CPU and GPU backends.
- **`agent/`** — `Agent` is a dataclass holding location, heading, task list,
  and `InfectionStatus`. `Agent.perform_task()` runs an ordered tuple of
  handler functions from `task/tasklist.py`
  (`perform_in_progress_task`, `perform_moving_to_task_location`,
  `perform_suspended_task`, `perform_to_be_started_task`); each returns
  truthy when it has handled the step, short-circuiting the rest.
- **`task/`** — `Task` is a plain dataclass; subclasses only exist where
  there's real extra behaviour (e.g. `TaskDoorAccess`, `TaskOccupyContent`),
  expressed via lifecycle hooks (`on_start_moving`, `on_started`,
  `on_completed`) rather than `isinstance` checks. `task_builders.py` maps
  `TaskType` to builder functions via the `TASK_BUILDERS` dict (factory
  pattern), so `Agent.add_task` avoids a long if/elif chain. See the design
  notes in `task/task.py`'s module docstring for the reasoning.
- **GPU path**: `simulation.use_gpu=True` routes physics through
  `gpu_physics.GPUPhysicsEngine` (NVIDIA Warp) instead of the CPU
  agent-by-agent loop; PNG plotting is disabled in this mode. This is a
  parallel code path, not a drop-in replacement — check `use_gpu` branches in
  `simulation.py` and `run.py` when touching movement/physics.
- **`run.py`** — the `simulate()` entry point used by `examples/simple.py`;
  drives the step loop, optional live/PNG plotting, trajectory recording to
  `simulation_outputs/` (gitignored).
- **`mesa_wrapper.py`** — a thin `mesa.Model` wrapper (`HospitalABM`) around
  the same `Simulation`, used only to plug into SolaraViz for the interactive
  dashboard (`examples/solara_app.py`), not the primary simulation loop.
- **`floorplan_extractor/` and `floorplan_extractor_python/`** — a separate,
  loosely-coupled pipeline that converts CAD/DXF floorplans into the
  YAML/NPZ formats the simulation reads; not part of the ABM step loop.
- **`docker/cadflow/`** and **`docker/tre/`** — containerised workflows
  (DWG→GPKG conversion, and a self-contained TRE deployment image) with their
  own Makefiles/READMEs, independent of the `python-code/` tooling above.

Custom exceptions (`SimulationModeError`, `TimeError`, `InvalidRoomError`,
`InvalidDoorError`, `NonNegativeValueError`, etc.) are centralized in
`amr_hub_abm/exceptions.py` — raise these for domain errors instead of bare
`ValueError`/`Exception`.

## Conventions

- **Explicit RNG threading**: an `np.random.Generator` (`rng_generator`) is
  created once in `simulation_factory` and passed explicitly through
  `Agent`, `SpatialQuery`, and factory functions for reproducibility. Don't
  use global `random`/`np.random` state.
- **Type hints are mandatory** and enforced by `mypy` (`ruff` lint selects
  `ALL` rules, see `pyproject.toml` for the specific ignores). Avoid `Any`.
- **NumPy-style docstrings** on public functions/classes/modules (see
  CONTRIBUTING.md for the exact format) — required for mkdocstrings to
  render the API docs correctly.
- **Structured state over dicts**: prefer dataclasses/enums/typed containers
  (as used throughout `agent/`, `space/`, `task/`) instead of loosely-typed
  dicts.
- Some modules contain `# --8<-- [start:X]` / `[end:X]` marker comments
  (e.g. `agent.py`, `simulation.py`) — these are `pymdownx.snippets` anchors
  used to embed code excerpts into the MkDocs documentation; keep them
  paired if you move/edit that code.
- Comments should explain scientific/modelling assumptions and non-obvious
  reasoning, not restate the code.
- PRs should have a single responsibility and link to an issue; `main` is
  protected (no direct or force pushes).
