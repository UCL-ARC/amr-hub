# Hardcoded Parameters in `amr_hub_abm`

Inventory of hardcoded parameters in the simulation engine, compiled in
support of the "Extracting hard coded parameters into the config" item in
[`tasks.md`](../tasks.md). Intended as a working reference before deciding
what to move into a config file. Paths are relative to `python-code/` inside
the repo.

## Agent kinematics — ✅ resolved

Extracted into the simulation config (`agent_movement_speed`, `agent_stochasticity`,
`agent_interaction_radius`, `agent_max_movement_attempts` in
`tests/inputs/simulation_config.yml` / `simulation_config_gpu.yml`), loaded via the
frozen `AgentKinematicsConfig` dataclass in `src/amr_hub_abm/agent/kinematics.py`.
`AgentKinematicsConfig.from_config()` raises `InvalidDefinitionError` if any key is
missing — no hardcoded fallback values remain in `simulation_factory.py`,
`mesa_wrapper.py`, or `space/space.py`. The SolaraViz `agent_speed`/
`agent_stochasticity` sliders in `examples/solara_app.py` were removed accordingly,
since `HospitalABM` no longer accepts runtime overrides for these.

## Config keys defined but unused (⚠️ dead — not read anywhere in code)

Distinct from `agent_movement_speed` above — these keys describe a min/average/max
HCW speed range that has no corresponding logic anywhere in the codebase.

| Variable            | Current Value | File                                                                           |
| ------------------- | ------------- | ------------------------------------------------------------------------------ |
| `average_hcw_speed` | `1.4`         | `tests/inputs/simulation_config.yml`, `tests/inputs/simulation_config_gpu.yml` |
| `minimum_hcw_speed` | `1.0`         | `tests/inputs/simulation_config.yml`, `tests/inputs/simulation_config_gpu.yml` |
| `maximum_hcw_speed` | `2.0`         | `tests/inputs/simulation_config.yml`, `tests/inputs/simulation_config_gpu.yml` |

## Task timing

| Variable                              | Current Value | File                                        |
| ------------------------------------- | ------------- | ------------------------------------------- |
| `DEFAULT_TIME_NEEDED[ATTEND_PATIENT]` | `15`          | `src/amr_hub_abm/task/task.py:431` (unused) |
| `DEFAULT_TIME_NEEDED[DOOR_ACCESS]`    | `1`           | `src/amr_hub_abm/task/task.py:432` (unused) |
| `DEFAULT_TIME_NEEDED[WORKSTATION]`    | `30`          | `src/amr_hub_abm/task/task.py:433` (unused) |
| `DEFAULT_TIME_NEEDED[OCCUPY_CONTENT]` | `10`          | `src/amr_hub_abm/task/task.py:434` (unused) |
| `DEFAULT_TIME_NEEDED[GOTO_LOCATION]`  | `0`           | `src/amr_hub_abm/task/task.py:435` (unused) |
| `time_needed` (attend patient)        | `15`          | `src/amr_hub_abm/task/task_builders.py:72`  |
| `time_needed` (door access)           | `1`           | `src/amr_hub_abm/task/task_builders.py:99`  |
| `time_needed` (workstation)           | `30`          | `src/amr_hub_abm/task/task_builders.py:114` |
| `time_needed` (occupy content)        | `10`          | `src/amr_hub_abm/task/task_builders.py:132` |
| `buffer_distance` (door offset)       | `0.05`        | `src/amr_hub_abm/task/task.py:318`          |

## Room / space geometry

| Variable                        | Current Value              | File                                     |
| ------------------------------- | -------------------------- | ---------------------------------------- |
| `thickness` (wall default)      | `0.2`                      | `src/amr_hub_abm/space/wall.py:27`       |
| `CONTENT_SIZES[BED]`            | `(0.2, 0.1)` metres        | `src/amr_hub_abm/space/content.py:33`    |
| `CONTENT_SIZES[WORKSTATION]`    | `(0.1, 0.05)` metres       | `src/amr_hub_abm/space/content.py:34`    |
| `CONTENT_SIZES[CHAIR]`          | `(0.05, 0.05)` metres      | `src/amr_hub_abm/space/content.py:35`    |
| `get_random_point.max_attempts` | `1000`                     | `src/amr_hub_abm/space/room.py:165`      |
| wall-clearance radius (inline)  | `0.1`                      | `src/amr_hub_abm/space/room.py:181`      |
| pseudo-room sizing constants    | `2 * len(doors) + 2`, etc. | `src/amr_hub_abm/space/floor.py:156-174` |

## GPU physics path

| Variable                                                         | Current Value                               | File                                           |
| ---------------------------------------------------------------- | ------------------------------------------- | ---------------------------------------------- |
| `search_radius` (transmission)                                   | `2.0`                                       | `src/amr_hub_abm/gpu_physics.py:128`           |
| kinematic `speed` (kernel arg, ignores `agent.movement_speed`)   | `1.5`                                       | `src/amr_hub_abm/gpu_physics.py:166`           |
| kinematic `dt` (kernel arg)                                      | `1.0`                                       | `src/amr_hub_abm/gpu_physics.py:166`           |
| snap-to-target threshold                                         | `0.1`                                       | `src/amr_hub_abm/gpu_physics.py:48`            |
| `HashGrid` dims (`dim_x/y/z`)                                    | `128, 128, 128`                             | `src/amr_hub_abm/gpu_physics.py:127`           |
| `cad_path` default                                               | `"tests/inputs/GPU_floorplan_simple_a.npz"` | `src/amr_hub_abm/gpu_physics.py:111`           |
| `output_dir` default                                             | `"simulation_outputs"`                      | `src/amr_hub_abm/gpu_physics.py:223`           |
| infection status ints (`SUSCEPTIBLE=0`, `INFECTED=2`) in kernels | `0`, `2`                                    | `src/amr_hub_abm/gpu_physics.py:80,95,195-196` |

## Driver / I/O paths

| Variable                    | Current Value                              | File                                 |
| --------------------------- | ------------------------------------------ | ------------------------------------ |
| `config_path` default (CPU) | `"tests/inputs/simulation_config.yml"`     | `src/amr_hub_abm/run.py:41`          |
| `config_path` default (GPU) | `"tests/inputs/simulation_config_gpu.yml"` | `src/amr_hub_abm/run.py:45`          |
| `config_path` default       | `"tests/inputs/simulation_config.yml"`     | `src/amr_hub_abm/mesa_wrapper.py:26` |
| live-plot refresh cadence   | `simulation.time % 100 == 0`               | `src/amr_hub_abm/run.py:144`         |

## Visualization / cosmetic (lower priority — style, not science)

| Variable                              | Current Value                    | File                                                |
| ------------------------------------- | -------------------------------- | --------------------------------------------------- |
| infection ring `markersize`           | `12`                             | `src/amr_hub_abm/agent/plotter.py:41`               |
| infection ring `markeredgewidth`      | `2`                              | `src/amr_hub_abm/agent/plotter.py:44`               |
| agent dot `markersize`                | `5`                              | `src/amr_hub_abm/agent/plotter.py:52`               |
| label offset (x, y)                   | `0.1, 0.05`                      | `src/amr_hub_abm/agent/plotter.py:98-99`            |
| label `fontsize`                      | `7`                              | `src/amr_hub_abm/agent/plotter.py:101`              |
| trajectory `linewidth` / `alpha`      | `1.5` / `0.7`                    | `src/amr_hub_abm/agent/plotter.py:129,131`          |
| `ROLE_COLOUR_MAP`                     | `blue/red/green`                 | `src/amr_hub_abm/agent/enums.py:23-27`              |
| `INFECTION_RING_COLOUR`               | `gold/darkred/blue`              | `src/amr_hub_abm/agent/enums.py:29-34`              |
| `CONTENT_COLORS`                      | `lightblue/lightgreen/lightgray` | `src/amr_hub_abm/space/content.py:38-42`            |
| `marker_size` (content)               | `100`                            | `src/amr_hub_abm/space/content.py:70`               |
| `marker_type` (content)               | `"s"`                            | `src/amr_hub_abm/space/content.py:69`               |
| `hash(...) % 128` (int8 packing)      | `128`                            | `src/amr_hub_abm/agent/output.py:122`               |
| QR code `version`/`box_size`/`border` | `1` / `10` / `5`                 | `examples/solara_app.py:46` (repo root `examples/`) |
| `figsize`                             | `(6, 6)`                         | `examples/solara_app.py:26`                         |
| `play_interval` / `render_interval`   | `100` / `100`                    | `examples/solara_app.py:133-134`                    |
