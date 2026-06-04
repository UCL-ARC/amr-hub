# AMR-Hub Project

[![pre-commit]][pre-commit]
[![Tests status][tests-badge]][tests-link]
[![codecov](https://codecov.io/gh/UCL-ARC/amr-hub/graph/badge.svg)](https://codecov.io/gh/UCL-ARC/amr-hub)
[![Linting status][linting-badge]][linting-link]
[![Documentation status][documentation-badge]][documentation-link]
[![License][license-badge]][license-link]

Welcome to the AMR-Hub Project. We aim to model the transmission of Anti-Microbial Resistance in Hospitals.

<!-- prettier-ignore-start -->
[pre-commit]:              https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white
[tests-badge]:              https://github.com/UCL-ARC/amr-hub/actions/workflows/tests.yml/badge.svg
[tests-link]:               https://github.com/UCL-ARC/amr-hub/actions/workflows/tests.yml
[linting-badge]:            https://github.com/UCL-ARC/amr-hub/actions/workflows/linting.yml/badge.svg
[linting-link]:             https://github.com/UCL-ARC/amr-hub/actions/workflows/linting.yml
[documentation-badge]:      https://github.com/UCL-ARC/amr-hub/actions/workflows/docs.yml/badge.svg
[documentation-link]:       https://github.com/UCL-ARC/amr-hub/actions/workflows/docs.yml
[license-badge]:            https://img.shields.io/badge/License-MIT-yellow.svg
[license-link]:             https://github.com/UCL-ARC/amr-hub/blob/main/LICENSE
<!-- prettier-ignore-end -->

AMR-HUB is an open-source agent-based modelling (ABM) framework for simulating hospital workflows, human movement, and antimicrobial resistance (AMR) transmission dynamics within healthcare environments. The project is designed around a Trusted Research Environment (TRE)-centric workflow that separates sensitive healthcare data from publicly distributable simulation software and anonymised outputs.

The framework combines hospital geometry modelling, task scheduling, infection propagation, movement simulation, and interactive visualisation into a modular research software platform. It is intended both as a scientific modelling framework and as a reusable infrastructure for future epidemiological and operational healthcare simulations.

## Official documentation

- [AMR-HUB Technical Documentation](https://amr-hub.readthedocs.io/)
- [AMR-HUB GitHub Repository](https://github.com/amr-hub/amr-hub)

## Overall Workflow

The architecture is structured around four major stages:

![Data Pipeline for the project](<static/Agent Movement Trajectory.png>)

This separation ensures that sensitive healthcare datasets remain securely inside Trusted Research Environments while allowing the simulation engine itself to remain open-source and publicly distributable.

### TRE Inputs

The input layer contains sensitive or restricted healthcare datasets that remain inside the TRE. These include hospital floorplans, routinely collected operational data, infection-related datasets, and simulation configuration files. Before simulation, the data is transformed into simulation-ready formats that define hospital geometry, infection parameters, agent schedules, and movement constraints.

The simulation configuration is typically controlled using YAML files, while healthcare datasets may originate from databases, spreadsheets, or time-series movement records. Architectural hospital layouts are converted into structured geometric representations suitable for spatial simulation.

### Simulation Code

The simulation engine is the core computational layer of the project and is designed to be publicly distributable. The codebase handles agent movement, task scheduling, occupancy modelling, interaction generation, infection transmission, and temporal progression within hospital environments.

Agents may represent patients, healthcare workers, visitors, cleaning staff, or administrative personnel. Their behaviour combines deterministic scheduling with stochastic movement and environmental awareness. The simulation environment itself is composed of buildings, floors, rooms, walls, and doors, allowing the framework to support realistic hospital geometries rather than simple grid-based environments.

The architecture is intentionally modular and extensible to support future developments such as uncertainty quantification, reinforcement learning approaches, GPU acceleration, and modelling of multiple pathogens.

More information on the simulation code can be found in the [simulation documentation](python-code/README.md).

### Simulation Outputs

The simulation produces anonymised outputs suitable for downstream analysis and visualisation. These outputs include movement trajectories, interaction timelines, task histories, and infection progression records.

Agent movement trajectories can be used to analyse occupancy patterns and movement hotspots. Interaction matrices and timelines support contact-network analysis and transmission studies. Task histories provide insight into operational workflows, while infection timelines allow researchers to study outbreak progression and intervention effectiveness over time.

The output layer is designed so that only anonymised summaries need to leave the TRE environment.

### Interactive Dashboard

The dashboard layer provides interactive visualisation and reporting capabilities built using Mesa, Solara, Matplotlib, and Pandas. Depending on governance requirements, the dashboard may operate entirely inside the TRE or on anonymised exported outputs.

The dashboard can provide live floorplan visualisation, task monitoring, infection summaries, occupancy statistics, movement replay, animations, and interactive reports. The visualisation layer is designed to be configurable according to end-user requirements while preserving privacy and governance constraints.

## Repository Structure

The repository is organised to separate simulation code, documentation, examples, and development infrastructure.

```text
amr-hub/
├── .devcontainer/        # Development container configuration
├── .github/              # GitHub Actions and repository automation
├── docker/               # Docker configurations and supporting
|
├── docs/                 # Documentation source files
├── examples/             # Example simulations and demonstrations
├── python-code/          # Core AMR-Hub simulation package
├── schemas/              # Configuration and data schemas
├── static/               # Static assets for documentation and
|
├── workspace_settings/   # Shared development environment settings
├── README.md
├── CONTRIBUTING.md
├── Makefile
└── LICENSE
```

### Key Directories

- **`python-code/`** contains the core simulation framework, including agent definitions, environment models, infection dynamics, task scheduling, visualisation components, and tests. The core agent-based model is implemented in `python-code/src/amr_hub_abm/`, while `python-code/src/floorplan_extractor/` contains logic to convert floorplan data into the simulation format.
- **`docs/`** contains the source files used to build the project documentation website.
- **`examples/`** provides example configurations, demonstrations, and tutorials for users and developers.
- **`schemas/`** defines the validation rules and schemas used for simulation input files.
- **`static/`** stores images, diagrams, and other static assets referenced throughout the documentation.
- **`.github/`**, **`.devcontainer/`**, and **`workspace_settings/`** provide the tooling required for continuous integration, reproducible development environments, and containerised workflows.

## Development Philosophy

The project emphasises modularity, reproducibility, extensibility, testing, and documentation. The architecture is intentionally designed so that preprocessing pipelines, simulation logic, visualisation layers, and TRE infrastructure remain independently maintainable and replaceable.

The framework follows modern research software engineering practices with a focus on maintainability, transparency, and long-term reuse.

See the [contributing guidelines](CONTRIBUTING.md) for more information on how to get involved with the project.

## License

This project is licensed under the MIT License.
Welcome to the AMR-Hub Project. We aim to model the transmission of Anti-Microbial Resistance in Hospitals.

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->

[![All Contributors](https://img.shields.io/badge/all_contributors-13-orange.svg?style=flat-square)](#contributors-)

<!-- ALL-CONTRIBUTORS-BADGE:END -->

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

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!
