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

Install additional dependencies for development and documentation:

```sh
# For development tools (testing, linting, etc.)
pip install -e ".[dev]"

# For building documentation
pip install -e ".[docs]"

# For running tests
pip install -e ".[test]"
```

## Usage

Basic example of using the package:

```python
from amr_hub_abm import __version__
from amr_hub_abm.space import Location, Building
from amr_hub_abm.agent import Agent
from amr_hub_abm.task import Task, TaskType, TaskPriority

# Create a location
location = Location(x=10.0, y=20.0, floor=1)

# Additional usage examples coming soon...
```

For more detailed examples and API documentation, please refer to the [documentation](https://ucl-arc.github.io/amr-hub/).

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
