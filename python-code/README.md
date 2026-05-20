# AMR Hub ABM

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Tests status][tests-badge]][tests-link]
[![Linting status][linting-badge]][linting-link]
[![Documentation status][documentation-badge]][documentation-link]
[![License][license-badge]](./LICENSE.md)

<!-- prettier-ignore-start -->
[tests-badge]:              https://github.com/UCL-ARC/amr-hub/actions/workflows/tests.yml/badge.svg
[tests-link]:               https://github.com/UCL-ARC/amr-hub/actions/workflows/tests.yml
[linting-badge]:            https://github.com/UCL-ARC/amr-hub/actions/workflows/linting.yml/badge.svg
[linting-link]:             https://github.com/UCL-ARC/amr-hub/actions/workflows/linting.yml
[documentation-badge]:      https://github.com/UCL-ARC/amr-hub/actions/workflows/docs.yml/badge.svg
[documentation-link]:       https://github.com/UCL-ARC/amr-hub/actions/workflows/docs.yml
[license-badge]:            https://img.shields.io/badge/License-MIT-yellow.svg
<!-- prettier-ignore-end -->

An agent-based model (ABM) for simulating the spread of Antimicrobial Resistant (AMR) infections in hospital settings.

This project is developed in collaboration with the [Centre for Advanced Research Computing](https://ucl.ac.uk/arc), University College London.

## Overview

`amr-hub-abm` is a Python package that provides a framework for modeling and analyzing the transmission dynamics of antimicrobial-resistant pathogens within healthcare facilities. The simulation incorporates spatial modeling, agent behavior, and task management to provide realistic representations of hospital environments and infection spread patterns.

### Key Features

- **Spatial modeling**: Representation of hospital buildings, floors, and room layouts
- **Agent-based simulation**: Model individual agents (patients, healthcare workers) with distinct behaviors
- **Task management**: Simulate realistic workflow patterns with priority-based task assignment
- **Flexible architecture**: Extensible design for incorporating custom behaviors and scenarios

## Installation

### Prerequisites

`amr-hub-abm` requires **Python 3.13** or higher.

We recommend using a virtual environment manager such as [Conda](https://docs.conda.io/projects/conda/en/stable/) or [venv](https://docs.python.org/3/library/venv.html) to create an isolated environment for the package.

### Install from GitHub

To install the latest development version directly from GitHub:

```sh
pip install git+https://github.com/UCL-ARC/amr-hub.git
```

### Install from Source (Development)

For development or to make local modifications:

- Clone the repository:

```sh
git clone https://github.com/UCL-ARC/amr-hub.git
cd amr-hub/python-code
```

- Install in editable mode:

```sh
pip install -e .
```

### Optional Dependencies

Install additional dependencies for development and documentations:

```sh
# For development tools (testing, linting, etc.)
pip install -e ".[dev]"

# For building documentation
pip install -e ".[docs]"

# For running tests
pip install -e ".[test]"
```

## Usage

### Running the simulation

The simulation is driven by `simulate()` in `src/amr_hub_abm/run.py`, which is called by example driver scripts in `examples/`.

#### Configuration

Simulation parameters are defined in `tests/inputs/simulation_config.yml`:

```yaml
mode: data driven # "data driven" or "rule based"
location_timeseries_path: tests/inputs/location_timeseries.csv # HCW location events
buildings_path: tests/inputs/buildings.yml # building/floor/room layout
start_time: 2024-01-01 00:00:00
end_time: 2024-01-02 00:00:00
length_of_timestep_in_seconds: 1
```

The location timeseries CSV defines the schedule of events for each healthcare worker (HCW): which patient to attend, when, which doors to access, and where to sit. See `tests/inputs/location_timeseries.csv` for an example.

#### Running from the terminal

The simplest way to run a simulation is via `examples/simple.py`:

```bash
uv run python examples/simple.py
```

This calls `simulate()` with default flags. To customize, edit `simple.py` and pass arguments to `simulate()`:

| Flag                   | What it does                                                                   |
| ---------------------- | ------------------------------------------------------------------------------ |
| `live=True`            | Opens a matplotlib window that updates every step. Blocks until window closed. |
| `plot=True`            | Saves a PNG of the floorplan to `simulation_outputs/` every step.              |
| `record=True`          | Records each agent's position trajectory at every step.                        |
| `plot_trajectory=True` | At end of run, saves a PNG showing all agent trajectories overlaid.            |
| `seed_infections=True` | Manually set agent[0] to INFECTED and agent[1] to EXPOSED for viz testing.     |

For example, to record trajectories and produce a final overlay PNG:

```python
simulate(record=True, plot_trajectory=True)
```

### Output files

Running with `record=True` and/or `plot_trajectory=True` produces files in `simulation_outputs/` (relative to repo root):

- `agent_<type>_<id>_trajectory.csv` — per-agent positions over time
- `Sample Hospital_time_<N>.png` — per-step floorplan snapshots (with `plot=True`)
- `Sample Hospital_trajectories.png` — overlay of all agent paths (with `plot_trajectory=True`)

These are gitignored — they're generated artifacts.

### Browser-based visualization (SolaraViz)

For an interactive browser-based view with play/pause/step controls, use the Solara app:

```bash
uv run solara run /full/path/to/examples/solara_app.py
```

This opens a web page at `http://localhost:8765` showing the floorplan, agents, and infection status updating in real time. Use the controls panel to play, pause, step, or reset the simulation, and adjust the render interval to balance speed and smoothness.

The Solara app currently seeds two agents with infection status (one INFECTED, one EXPOSED) for visualization testing. Disease dynamics are not yet implemented in the simulation itself.

## Development

### Running Tests

Tests can be run across all compatible Python versions in isolated environments using [`tox`](https://tox.wiki/en/latest/):

```sh
tox
```

To run tests manually with [`pytest`](https://docs.pytest.org/):

```sh
pytest tests
```

To run tests with coverage reporting:

```sh
pytest --cov --cov-report=xml
```

### Building Documentation

Build the MkDocs HTML documentation locally:

```sh
tox -e docs
```

The built documentation will be written to the `site/` directory.

Alternatively, to build and preview the documentation with live reloading:

```sh
mkdocs serve
```

Then open your browser to `http://localhost:8000`.

### Code Quality

This project uses several tools to maintain code quality:

- **[pre-commit](https://pre-commit.com/)**: Git hooks for automatic code formatting and linting
- **[ruff](https://docs.astral.sh/ruff/)**: Fast Python linter and formatter
- **[mypy](https://mypy-lang.org/)**: Static type checker

To set up pre-commit hooks:

```sh
pre-commit install
```

To manually run all pre-commit hooks:

```sh
pre-commit run --all-files
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to:

- Update tests as appropriate
- Follow the existing code style
- Run the test suite before submitting

## Contributors

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/arindamsaha1507"><img src="https://avatars.githubusercontent.com/u/25665512?v=4?s=100" width="100px;" alt="Arindam Saha"/><br /><sub><b>Arindam Saha</b></sub></a><br /><a href="https://github.com/UCL-ARC/amr-hub/commits?author=arindamsaha1507" title="Code">💻</a> <a href="https://github.com/UCL-ARC/amr-hub/commits?author=arindamsaha1507" title="Documentation">📖</a> <a href="https://github.com/UCL-ARC/amr-hub/commits?author=arindamsaha1507" title="Tests">⚠️</a> <a href="#maintenance-arindamsaha1507" title="Maintenance">🚧</a> <a href="#research-arindamsaha1507" title="Research">🔬</a> <a href="https://github.com/UCL-ARC/amr-hub/issues?q=author%3Aarindamsaha1507" title="Bug reports">🐛</a> <a href="https://github.com/UCL-ARC/amr-hub/pulls?q=is%3Apr+reviewed-by%3Aarindamsaha1507" title="Reviewed Pull Requests">👀</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/features/security"><img src="https://avatars.githubusercontent.com/u/27347476?v=4?s=100" width="100px;" alt="Dependabot"/><br /><sub><b>Dependabot</b></sub></a><br /><a href="#security-dependabot" title="Security">🛡️</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/edthink"><img src="https://avatars.githubusercontent.com/u/7822805?v=4?s=100" width="100px;" alt="Ed Manley"/><br /><sub><b>Ed Manley</b></sub></a><br /><a href="#fundingFinding-edthink" title="Funding Finding">🔍</a> <a href="#ideas-edthink" title="Ideas, Planning, & Feedback">🤔</a> <a href="#mentoring-edthink" title="Mentoring">🧑‍🏫</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/gsvarovsky"><img src="https://avatars.githubusercontent.com/u/19226962?v=4?s=100" width="100px;" alt="George Svarovsky"/><br /><sub><b>George Svarovsky</b></sub></a><br /><a href="#infra-gsvarovsky" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/jamespjh"><img src="https://avatars.githubusercontent.com/u/55009?v=4?s=100" width="100px;" alt="James Hetherington"/><br /><sub><b>James Hetherington</b></sub></a><br /><a href="#ideas-jamespjh" title="Ideas, Planning, & Feedback">🤔</a> <a href="#mentoring-jamespjh" title="Mentoring">🧑‍🏫</a> <a href="#fundingFinding-jamespjh" title="Funding Finding">🔍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/ksuchak1990"><img src="https://avatars.githubusercontent.com/u/18059900?v=4?s=100" width="100px;" alt="Keiran Suchak"/><br /><sub><b>Keiran Suchak</b></sub></a><br /><a href="https://github.com/UCL-ARC/amr-hub/commits?author=ksuchak1990" title="Code">💻</a> <a href="https://github.com/UCL-ARC/amr-hub/commits?author=ksuchak1990" title="Documentation">📖</a> <a href="https://github.com/UCL-ARC/amr-hub/commits?author=ksuchak1990" title="Tests">⚠️</a> <a href="#plugin-ksuchak1990" title="Plugin/utility libraries">🔌</a> <a href="#research-ksuchak1990" title="Research">🔬</a> <a href="https://github.com/UCL-ARC/amr-hub/pulls?q=is%3Apr+reviewed-by%3Aksuchak1990" title="Reviewed Pull Requests">👀</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/lsheridanucl"><img src="https://avatars.githubusercontent.com/u/210515269?v=4?s=100" width="100px;" alt="Lauren Sheridan"/><br /><sub><b>Lauren Sheridan</b></sub></a><br /><a href="#infra-lsheridanucl" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/mwij02"><img src="https://avatars.githubusercontent.com/u/171925679?v=4?s=100" width="100px;" alt="Marlon"/><br /><sub><b>Marlon</b></sub></a><br /><a href="#infra-mwij02" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/MonikaSvata"><img src="https://avatars.githubusercontent.com/u/123406697?v=4?s=100" width="100px;" alt="MonikaSvata"/><br /><sub><b>MonikaSvata</b></sub></a><br /><a href="#projectManagement-MonikaSvata" title="Project Management">📆</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/p-j-smith"><img src="https://avatars.githubusercontent.com/u/29753790?v=4?s=100" width="100px;" alt="Paul Smith"/><br /><sub><b>Paul Smith</b></sub></a><br /><a href="#data-p-j-smith" title="Data">🔣</a> <a href="#infra-p-j-smith" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/skeating"><img src="https://avatars.githubusercontent.com/u/1736558?v=4?s=100" width="100px;" alt="Sarah Keating"/><br /><sub><b>Sarah Keating</b></sub></a><br /><a href="#infra-skeating" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/swise5"><img src="https://avatars.githubusercontent.com/u/1005676?v=4?s=100" width="100px;" alt="Sarah Wise"/><br /><sub><b>Sarah Wise</b></sub></a><br /><a href="#ideas-swise5" title="Ideas, Planning, & Feedback">🤔</a> <a href="#mentoring-swise5" title="Mentoring">🧑‍🏫</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/yidilozdemir"><img src="https://avatars.githubusercontent.com/u/30597301?v=4?s=100" width="100px;" alt="yidilozdemir"/><br /><sub><b>yidilozdemir</b></sub></a><br /><a href="https://github.com/UCL-ARC/amr-hub/commits?author=yidilozdemir" title="Documentation">📖</a> <a href="#research-yidilozdemir" title="Research">🔬</a> <a href="https://github.com/UCL-ARC/amr-hub/commits?author=yidilozdemir" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

This project is supported by the [Centre for Advanced Research Computing](https://ucl.ac.uk/arc) at University College London.

## Contact

For questions or support, please contact:

- **Project Lead**: Arindam Saha ([arindam.saha@ucl.ac.uk](mailto:arindam.saha@ucl.ac.uk))
- **ARC Collaborations**: [arc.collaborations@ucl.ac.uk](mailto:arc.collaborations@ucl.ac.uk)
