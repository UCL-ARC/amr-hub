# Hardcoded Parameters in `amr_hub_abm`

Inventory of hardcoded parameters in the simulation engine, compiled in support
of the "Extracting hard coded parameters into the config" item in
[`tasks.md`](../tasks.md). Intended as a working reference before deciding what
else to move into config files. Paths below are repo-relative.

## Agent kinematics - ✅ resolved

Extracted into the simulation config (`agent_movement_speed`,
`agent_stochasticity`, `agent_interaction_radius`,
`agent_max_movement_attempts` in `python-code/tests/inputs/simulation_config.yml`
and `python-code/tests/inputs/simulation_config_gpu.yml`), loaded via the
frozen `AgentKinematicsConfig` dataclass in
`python-code/src/amr_hub_abm/agent/kinematics.py`.
`AgentKinematicsConfig.from_config()` raises `InvalidDefinitionError` if any key
is missing, so there are no fallback values left in
`python-code/src/amr_hub_abm/simulation_factory.py`,
`python-code/src/amr_hub_abm/mesa_wrapper.py`, or
`python-code/src/amr_hub_abm/spatial/engine.py`.

## Task timing - ✅ resolved for user-facing durations

The main task durations have now been extracted into config via
`time_needed_attend_patient`, `time_needed_door_access`,
`time_needed_workstation`, and `time_needed_occupy_content` in
`python-code/tests/inputs/simulation_config.yml`. They are loaded by the frozen
`TaskDurationConfig` dataclass in
`python-code/src/amr_hub_abm/task/task_duration.py`, then consumed in
`python-code/src/amr_hub_abm/simulation_factory.py` and
`python-code/src/amr_hub_abm/agent/agent.py`.

There are no remaining hardcoded defaults for task durations in the live task
builder path. The only nearby constant is `TaskDoorAccess.buffer_distance`,
which is intentionally still internal code behaviour rather than a user-facing
config parameter.

| Variable                        | Current Value | File                                       | Notes                                      |
| ------------------------------- | ------------- | ------------------------------------------ | ------------------------------------------ |
| `buffer_distance` (door offset) | `0.05`        | `python-code/src/amr_hub_abm/task/task.py` | Intentionally hardcoded internal parameter |

## Room / spatial geometry

| Variable                        | Current Value              | File                                               |
| ------------------------------- | -------------------------- | -------------------------------------------------- |
| `thickness` (wall default)      | `0.2`                      | `python-code/src/amr_hub_abm/spatial/wall.py`      |
| `CONTENT_SIZES[BED]`            | `(0.2, 0.1)` metres        | `python-code/src/amr_hub_abm/spatial/furniture.py` |
| `CONTENT_SIZES[WORKSTATION]`    | `(0.1, 0.05)` metres       | `python-code/src/amr_hub_abm/spatial/furniture.py` |
| `CONTENT_SIZES[CHAIR]`          | `(0.05, 0.05)` metres      | `python-code/src/amr_hub_abm/spatial/furniture.py` |
| `get_random_point.max_attempts` | `1000`                     | `python-code/src/amr_hub_abm/spatial/room.py`      |
| wall-clearance radius (inline)  | `0.1`                      | `python-code/src/amr_hub_abm/spatial/room.py`      |
| pseudo-room sizing constants    | `2 * len(doors) + 2`, etc. | `python-code/src/amr_hub_abm/spatial/floor.py`     |

## GPU physics path

| Variable                                                              | Current Value                               | File                                         |
| --------------------------------------------------------------------- | ------------------------------------------- | -------------------------------------------- |
| `search_radius` (transmission)                                        | `2.0`                                       | `python-code/src/amr_hub_abm/gpu_physics.py` |
| kinematic `speed` (kernel arg, ignores `agent.movement_speed`)        | `1.5`                                       | `python-code/src/amr_hub_abm/gpu_physics.py` |
| kinematic `dt` (kernel arg)                                           | `1.0`                                       | `python-code/src/amr_hub_abm/gpu_physics.py` |
| snap-to-target threshold                                              | `0.1`                                       | `python-code/src/amr_hub_abm/gpu_physics.py` |
| `HashGrid` dims (`dim_x/y/z`)                                         | `128, 128, 128`                             | `python-code/src/amr_hub_abm/gpu_physics.py` |
| `cad_path` default                                                    | `"tests/inputs/GPU_floorplan_simple_a.npz"` | `python-code/src/amr_hub_abm/gpu_physics.py` |
| `output_dir` default                                                  | `"simulation_outputs"`                      | `python-code/src/amr_hub_abm/gpu_physics.py` |
| infection status ints used in kernels (`SUSCEPTIBLE=0`, `INFECTED=2`) | `0`, `2`                                    | `python-code/src/amr_hub_abm/gpu_physics.py` |

## Driver / config / I/O paths

| Variable                  | Current Value                           | File                                          | Notes                                                         |
| ------------------------- | --------------------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| `sim_config` default      | `"tests/inputs/simulation_config.yml"`  | `python-code/src/amr_hub_abm/config.py`       | Global config is loaded eagerly at import time                |
| `config_path` argument    | `"tests/inputs/simulation_config.yml"`  | `python-code/src/amr_hub_abm/mesa_wrapper.py` | Stored on `HospitalABM`, but not actually used to load config |
| plot output dir           | `"../simulation_outputs"`               | `python-code/src/amr_hub_abm/run.py`          | Used for PNG output                                           |
| agent state output path   | `"simulation_outputs/agent_states.csv"` | `python-code/src/amr_hub_abm/run.py`          | Used for CSV recording                                        |
| GPU export output dir     | `"simulation_outputs"`                  | `python-code/src/amr_hub_abm/run.py`          | Passed through to `GPUPhysicsEngine.export_data()`            |
| live-plot refresh cadence | `simulation.time % 100 == 0`            | `python-code/src/amr_hub_abm/run.py`          |                                                               |

### GPU config caveat

`python-code/tests/inputs/simulation_config_gpu.yml` now defines the required
task-duration keys, but the current runtime wiring still imports `sim_config`
from `config.py`, so `run.py` and the Mesa wrapper always build the simulation
from `tests/inputs/simulation_config.yml` unless that loading path is changed.

## Visualization / cosmetic (lower priority - style, not science)

| Variable                                  | Current Value                    | File                                               |
| ----------------------------------------- | -------------------------------- | -------------------------------------------------- |
| infection ring `markersize`               | `12`                             | `python-code/src/amr_hub_abm/agent/plotter.py`     |
| infection ring `markeredgewidth`          | `2`                              | `python-code/src/amr_hub_abm/agent/plotter.py`     |
| agent dot `markersize`                    | `5`                              | `python-code/src/amr_hub_abm/agent/plotter.py`     |
| label offset (x, y)                       | `0.1, 0.05`                      | `python-code/src/amr_hub_abm/agent/plotter.py`     |
| label `fontsize`                          | `7`                              | `python-code/src/amr_hub_abm/agent/plotter.py`     |
| trajectory `linewidth` / `alpha`          | `1.5` / `0.7`                    | `python-code/src/amr_hub_abm/agent/plotter.py`     |
| `ROLE_COLOUR_MAP`                         | `blue/red/green`                 | `python-code/src/amr_hub_abm/agent/enums.py`       |
| `INFECTION_RING_COLOUR`                   | `gold/darkred/blue`              | `python-code/src/amr_hub_abm/agent/enums.py`       |
| `CONTENT_COLORS`                          | `lightblue/lightgreen/lightgray` | `python-code/src/amr_hub_abm/spatial/furniture.py` |
| `marker_size` (content)                   | `100`                            | `python-code/src/amr_hub_abm/spatial/furniture.py` |
| `marker_type` (content)                   | `"s"`                            | `python-code/src/amr_hub_abm/spatial/furniture.py` |
| content label offset                      | `+0.05, -0.15`                   | `python-code/src/amr_hub_abm/spatial/plotter.py`   |
| content label `fontsize`                  | `6`                              | `python-code/src/amr_hub_abm/spatial/plotter.py`   |
| default door colour / width               | `"brown"` / `2`                  | `python-code/src/amr_hub_abm/spatial/plotter.py`   |
| `hash(...) % 128` (int8 packing)          | `128`                            | `python-code/src/amr_hub_abm/agent/output.py`      |
| QR code `version` / `box_size` / `border` | `1` / `10` / `5`                 | `examples/solara_app.py`                           |
| `figsize`                                 | `(6, 6)`                         | `examples/solara_app.py`                           |
| `play_interval` / `render_interval`       | `100` / `100`                    | `examples/solara_app.py`                           |
