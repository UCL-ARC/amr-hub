# Agent-Based Modeling Tools for AMR-HUB

A technical review of platforms and frameworks for modeling movement dynamics in healthcare environments, with focus on disease transmission simulation.

## Overview

I have evaluated agent-based modeling (ABM) platforms for simulating patient and staff movement within hospital floors. The primary use case is understanding infection spread dynamics through realistic spatial navigation and behavioral modeling.

**Key requirements identified:**

- Realistic spatial navigation (continuous space, multi-floor, collision avoidance)
- GIS/CAD data integration for floor plans
- Parameter inference and model calibration capabilities
- Scalability for complex hospital environments
- Python/R integration for analysis pipelines

---

## 1. Primary Platforms Identified

### 1.1 GAMA Platform

**Website:** <https://gama-platform.org/wiki/Home>

**Overview:**
Production-ready, extensive, feature-rich platform specifically designed for spatially-explicit agent-based modeling. Seems like there is strong adoption in epidemiological and urban simulation research.

**Strengths/Important points to consider:**

- Rich primitives for agent movement, communication, and mathematical functions
- Native GIS support: directly imports shapefiles, CAD files, GeoTIFFs
- Continuous space modeling with multi-floor building support
- Flexible geometry management (rooms, doors, corridors as polygons)
- Built-in A\* pathfinding with collision avoidance (less manual specification than alternatives)
- GPU acceleration available
- Python and R interoperability

**Domain-Specific Language (GAML):**
Uses an intuitive high-level DSL for behavior specification. Spatial rules and movement patterns can be implemented declaratively.

**Limitations of GAMA:**

- Learning curve for GAML syntax
- Less native support for inverse reinforcement learning approaches
- Community smaller than NetLogo

#### Relevant Examples in GAMA/papers for our Case Study

**[Luneray Flu Tutorial](https://gama-platform.org/wiki/LuneraysFlu):**
Disease spread in urban environment with polygon-based buildings and polyline roads.

**[Healthcare Associated Infection Simulator](https://healthdatainsight.org.uk/project/healthcare-associated-infection-simulator/):**
Direct precedent for our use case.

_Model development stages:_

1. 3D hospital model creation from shapefiles (QGIS for floorplan preprocessing)
2. Agent behavior modeling done with data on staff shifts, patient routines, toilet visits, waiting rooms, lift usage
3. Infection spread mechanics (SEIR model: Susceptible → Exposed → Infected → Recovered)
4. Integration into unified simulator
5. Intervention strategy evaluation

_Modeling details:_

- **Pathogens:** MRSA, C. difficile
- **Transmission modes:** close contact, aerosol, surface contamination
- **Environment:** walls, beds, bays defined as spatial objects
- **Navigation:** Agents navigate realistically without wall collision
- **Outputs:** infection heatmaps, spread trajectories

**[Festival of Lights Pedestrian Simulation (Lyon)](https://www.mdpi.com/1424-8220/24/5/1639):**
Agent-based modeling for festival pedestrian movement with collision avoidance to model strategic destination planning. Agents could do model switching based on zone intensity (Continuum Crowds ↔ Social Force). They calibrated the parameters in their model with real trajectory data captured from cameras.

_Relevance:_
Demonstrates methodology for calibrating movement models against observed data — directly applicable to hospital trajectory data. Authors explicitly noted NetLogo could not capture required spatial behaviors for hospital environments.

---

### 1.2 NetLogo

**Website:** <https://ccl.northwestern.edu/netlogo/>

**Overview:**
Widely-used platform optimized for simpler "KISS" (Keep It Simple, Stupid) models. Extensive educational resources but limited for complex spatial environments.

**Strengths:**

- Low barrier to entry, large community
- Agent inspectors for interactive debugging
- GUI components (sliders, buttons) for parameter exploration
- HubNet extension for distributed/networked simulations
- GIS extension available
- RNetLogo package for R integration

**Limitations:**

- Not designed for complex descriptive models
- Limited GIS data integration compared to GAMA
- Simplified environment representation
- Less suitable for realistic hospital floor navigation

**Relevant work:**
"Should I Turn or Should I Go?" — pedestrian simulation using NetLogo GIS extension with normative pedestrian theory (Hoogendoorn & Bovy, 2002, 2004). Evaluated inconvenience, coverage, completion, and pace metrics.

---

### 1.3 Repast HPC / Repast4Py

**Website:** <https://repast.github.io/repast_hpc.html>

**Overview:**
High-performance computing focused framework designed for massive-scale simulations and mass operations like brute force parameter sweep.

**Variants:**

| Variant         | Language      | Use Case                        |
| --------------- | ------------- | ------------------------------- |
| Repast HPC      | C++ with MPI  | Massive distributed simulations |
| Repast Symphony | Java          | Standard desktop simulations    |
| Repast4Py       | Python        | Python-native implementation    |
| ReLogo          | Logo-like DSL | Simplified model development    |

**Strengths:**

- Designed for scalability across HPC clusters
- Multi-threaded event scheduler
- GIS and spatial modeling support
- Python ecosystem integration (scikit-optimize for inference)
- Brute-force parameter sweeps

**Repast4Py examples:** <https://repast.github.io/repast4py.site/examples/examples.html>

**Considerations:**

- Higher complexity for setup
- May be overkill for single-floor hospital simulations
- Best suited when scaling to hospital-wide or multi-facility models

---

### 1.4 Cormas

**Overview:**
Open source platform with strong support for distributed simulation control and multi-stakeholder interaction.

**Key features:**

- Direct agent manipulation through dedicated interface
- Network-distributed simulation control
- Multiple clients can view and interact with same simulation
- Useful for participatory modeling and serious games

**Applicability:**
Potentially useful for stakeholder engagement (clinicians interacting with simulation), but less feature-rich for pure spatial modeling than GAMA.

---

### 1.5 Mesa

**Website:** <https://mesa.readthedocs.io/>
**Repository:** <https://github.com/projectmesa/mesa>

**Overview:**
Pure Python ABM framework designed to be the Python alternative to NetLogo, Repast, and MASON. Prioritizes accessibility and integration with the scientific Python ecosystem.

**Strengths:**

- **Native Python:** Seamless integration with pandas, NumPy, scikit-learn, PyTorch, inference libraries
- Modular, extensible architecture — easy to plug in custom components
- Built-in data collection (`DataCollector`) exports directly to pandas DataFrames
- `BatchRunner` for parameter sweeps
- Browser-based visualization (SolaraViz in Mesa 3)
- Active development and community
- Jupyter notebook support

**Space types available:**

| Type                     | Description             |
| ------------------------ | ----------------------- |
| OrthogonalMooreGrid      | 8-neighbor grid         |
| OrthogonalVonNeumannGrid | 4-neighbor grid         |
| HexGrid                  | Hexagonal tessellation  |
| Network                  | Graph-based topologies  |
| VoronoiMesh              | Irregular tessellations |
| ContinuousSpace          | Continuous 2D space     |

**Mesa-Geo Extension:**
GIS support via `mesa-geo` package:

- `GeoSpace` hosts `GeoAgents` with Shapely geometry attributes
- Import from shapefiles, GeoJSON, GeoPandas GeoDataFrames
- Coordinate reference system (CRS) handling
- Raster and vector layer support
- Export to GIS formats via Rasterio/GeoPandas

**Key advantage for this project:**
Excellent for model integration specifically for RL and inference — because everything is Python, it's straightforward to wrap Mesa models as gym environments for RL and call inference libraries (sbi, pyABC) directly or scikit-optimize.

**Limitations:**

- **Manual movement specification:** Unlike GAMA's built-in A\* pathfinding and collision avoidance, Mesa requires explicit implementation of:
  - Pathfinding algorithms
  - Collision detection
  - Wall/obstacle avoidance
  - Multi-floor navigation
- Hard to define complex spatial environments (multi-floor hospitals) or realistic human navigation
- Mesa-Geo exists but still seems convoluted to use CAD/shapefile floor plans

---

## 2. Model Calibration & Inference Platforms

### 2.1 OpenMOLE

**Website:** <https://openmole.org/>

**Overview:**
Platform specifically designed for model exploration, calibration, and sensitivity analysis. Integrates with multiple simulation platforms.

**Core capabilities:**

- Parameter space exploration
- Model calibration against observed data
- Sensitivity analysis (Morris method, Sobol indices)
- Multi-objective optimization
- Uncertainty quantification
- Distributed computing support

**Inference methods:**

- `IslandABC()`: Approximate Bayesian Computation with priors and observed data
- `DirectSampling()`: Direct parameter sampling
- Genetic algorithms plugin
- Profile method for stochastic models
- PSE (Pattern Space Exploration) for behavioral diversity

**Integration:**
Native support for GAMA, NetLogo, R, Python models.

**GAMA + OpenMOLE workflow:** <https://openmole.org/GAMA.html>

1. Export GAMA project with `.gaml` file
2. Configure in OpenMOLE: seed, steps, stop conditions
3. Run distributed parameter exploration
4. Fit parameters to minimize distance from observed trajectories

---

## 3. Specific Crowd Simulation Frameworks

### 3.1 Menge

**Website:** <http://gamma.cs.unc.edu/Menge/>
**Repository:** <https://github.com/MengeCrowdSim/Menge>

**Overview:**
Open-source modular framework specifically for crowd simulation. Implements multiple pedestrian dynamics models.

**Models available:**

- Continuum Crowds Model
- Social Force Model
- Model switching based on density/zone

**Relevance:**
Useful for understanding high-traffic areas (ED waiting rooms, cafeterias) but may require integration work for hospital-specific behaviors.

---

### 3.2 CrowdNav

**Repository:** <https://github.com/vita-epfl/CrowdNav>

**Overview:**
Reinforcement learning approach to crowd navigation. Single repository implementation.

**Relevance:**
Aligns with inverse RL objectives for learning navigation policies from observed data. Potential for:

- Learning staff movement patterns from trajectory data
- Policy inference for patient navigation behaviors

---

### 3.3 SimWalk PRO

**Overview:**
Commercial tool focused on traffic and urban pedestrian planning.

**Applicability:**
More suited for urban/transit contexts than healthcare environments.

---

### 3.4 Unity ML-Agents

**Repository:** <https://github.com/Unity-Technologies/ml-agents>

**Overview:**
ML toolkit for Unity game engine. Supports RL agent training in 3D environments.

**Applicability:**

- Strong 3D visualization capabilities
- RL training infrastructure
- However, gaming-oriented and may require significant adaptation for healthcare simulation
- Could be useful for visualization/demonstration layer

---

## 4. Comparison of Main Options

| Platform        | Spatial Model Fidelity | GIS Support | Inference       | Scalability |
| --------------- | ---------------------- | ----------- | --------------- | ----------- |
| GAMA            | +++                    | +++         | Via OpenMOLE    | ++          |
| NetLogo         | +                      | ++          | Via OpenMOLE    | +           |
| Repast4Py/HPC   | ++                     | ++          | Via Python libs | +++         |
| CrowdNav        | ++                     | +           | Native RL       | ++          |
| Unity ML-Agents | ++                     | +           | Native RL       | ++          |

---

## 5. Recommendation

### Primary recommendation: GAMA + OpenMOLE

**Rationale:**

1. Direct precedent (HAI Simulator) for hospital environments
2. Native support for complex spatial geometry (walls, rooms, multi-floor)
3. Built-in pathfinding eliminates manual human navigation implementation
4. OpenMOLE integration enables parameter inference and sensitivity analysis
5. SEIR and other epidemiological models well-documented

### For Inverse RL / Learning from Trajectories

**Hybrid approach:**

1. Use GAMA for environment and basic agent mechanics
2. Extract trajectory data for offline RL training
3. Use CrowdNav or custom PyTorch implementation for policy learning
4. Re-integrate learned policies into GAMA simulation

---

## 6. Open Questions

- How to integrate real-time sensor data (RTLS) for model validation?
- How many ways can we identify to use trajectory data from UCLH?
- GPU acceleration benchmarks for GAMA vs. Repast on hospital-scale models?

---

## References

- GAMA Platform Documentation: <https://gama-platform.org/wiki/Home>
- OpenMOLE Documentation: <https://openmole.org/>
- HAI Simulator: <https://healthdatainsight.org.uk/project/healthcare-associated-infection-simulator/>
- Repast4Py: <https://repast.github.io/repast4py.site/>
- Festival of Lights Study: <https://www.mdpi.com/1424-8220/24/5/1639>
- Menge Crowd Simulation: <http://gamma.cs.unc.edu/Menge/>
- CrowdNav: <https://github.com/vita-epfl/CrowdNav>

---

_Last updated: January 2025_
_Project: AMR-HUB Hospital Movement & Infection Dynamics Simulation_
