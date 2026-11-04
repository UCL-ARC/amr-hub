# AMR-Hub: novelty, scientific weaknesses and publication strategy

Critical research and publication assessment — draft, 29 October 2026

**Audit basis:** repository revision `dc3b0d620025211232f39e535e45792363a91af2`, plus inspection of the separate stochasticity-sweep worktree. This report evaluates the software that is present, not all capabilities described in the project vision. No simulation code or running experiment was changed. The current 2,100-run sweep is treated as an experiment in progress, not as completed evidence.

**Clinical-study context (updated following investigator clarification):** The public synthetic scenario is a toy problem. The planned application is a UCLH ward with one year of routinely collected staff location/activity records, CAD floorplans and patient-linked positive and negative organism-specific clinical testing results over time. Patient movement and direct ward admission/discharge records are unavailable; ward-stay intervals are inferred from testing timelines. Sensitive clinical records must remain outside this repository. These are investigator-reported data streams for the planned study, not datasets independently inspected in this audit. Availability within the approved environment, completeness, linkage and temporal/spatial resolution have not been assessed. Absence of clinical records from the repository is not a scientific weakness or evidence that the project lacks a clinical application.

**Evidence labels:** _implemented_ means located in inspected code; _demonstrated_ requires an executed example or test; _validated_ means compared with independent observations for a specified use; _proposed_ means future work. These distinctions matter more than the number of features in a README.

## 1. Executive assessment

AMR-Hub has a credible route to peer-reviewed publication, but its strongest present contribution is **research infrastructure for hospital workflow and contact modelling**, not a validated model of antimicrobial resistance transmission. A manuscript claiming the latter now would substantially overstate the evidence.

Hospital infection ABMs, heterogeneous healthcare-worker contact networks, data-driven contact reconstruction, architectural environments, and GPU ABM frameworks all have substantial precedent. In particular, EHR-derived staff contact networks were published in 2013; sensor-informed hospital transmission ABMs predate that; and a 2025 paper already combines high-resolution staff/device trajectories, a hospital floorplan and an infection model. “We combine movement, geometry and infection” will not survive a serious literature review. [Temime et al. (2009)][R01], [Hornbeck et al. (2012)][R02], [Curtis et al. (2013)][R03], [Thota et al. (2025)][R12].

The defensible opportunity is narrower and more interesting: **an auditable, uncertainty-aware route from imperfect routine hospital events and imperfect geometry to contact-network estimates, with explicit tests of when modelling choices change scientific conclusions.** This is a candidate contribution, not a priority claim. AMR-Hub currently supplies parts of that route; it does not yet demonstrate the full inference and validation argument.

My recommended portfolio is:

1. **One software paper**, after narrowing the scope, correcting scientific contract problems and demonstrating reuse. This is the nearest route.
2. **One substantive methods paper** on movement/contact reconstruction or structural uncertainty. The present sweep can motivate it, but cannot alone establish a general result.
3. **One empirical UCLH ward study**, using the planned year of staff records, geometry and organism-specific test results, with a predefined endpoint and temporally held-out evaluation. Patient movement and the testing observation process are central uncertainties.

Geometry extraction, GPU execution, a benchmark dataset and TRE deployment could support additional papers **only if each produces an independently evaluated contribution**. They should not become six thin papers describing pieces of the same implementation.

**Blunt verdict:** there is potentially publishable work here, but the present evidence does not justify “novel AMR digital twin,” “realistic transmission prediction,” “validated GPU acceleration,” or “learned staff decision-making.” More simulation runs cannot compensate for an unvalidated mechanism.

## 2. Review method and its limits

This is a **targeted critical scoping review and code audit**, not a registered systematic review or a meta-analysis. Searches covered hospital/HAI ABMs; staff movement and contact networks; routine EHR and sensor observations; spatial ABM and crowd frameworks; CAD-to-topology extraction; GPU ABMs; secure research computation; model reporting; and publication requirements. Searches deliberately included 2025–2026 work. The companion [search and evidence notes](novelty-review/search-and-evidence-notes.md) describe queries, exclusions and access limitations.

The evidence base prioritises primary research articles, conference papers, author/institutional copies and official journal policies. Bibliographic details were checked against publisher/PubMed records and, where available, Crossref metadata. Journal issue years are used where they differ from online-first years: for example, GAMA is cited as 2019 and STRESS as 2019, with their earlier online publication noted in the bibliography. Search-engine crawl dates are not publication dates.

The review used accessible abstracts and selected full-text sections. Not every paper received full-text appraisal; restricted or partially accessible sources are identified in the evidence notes. No claim that AMR-Hub is “the first” is established by this search. Citation counts, impact factors and acceptance probabilities are not used as substitutes for assessing fit.

The code audit followed the actual CPU and GPU execution paths, task movement, contact measurements, geometry conversion, the event-analysis prototype and the TRE container. Two small non-mutating probes confirmed retry and duration semantics; their outputs are preserved in [code-probes.json](novelty-review/code-probes.json). File fingerprints and the audited revision are in [code-audit-manifest.json](novelty-review/code-audit-manifest.json). This is not a full security assessment, clinical validation study or exhaustive defect hunt.

## 3. What the software currently supports

| Area                       | Evidence in the repository                                                                                                                    | Publication implication                                                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Workflow-driven simulation | Factory-created simulations, event inputs, task lifecycle hooks, resource occupancy, explicit RNG use and interchangeable movement strategies | A useful software contribution if the behavioural contract is specified and reproducible                                                 |
| Spatial representation     | Building/floor/room hierarchy, walls, doors, furniture, spatial queries and topological input support                                         | Necessary infrastructure; neither hierarchy nor geometric realism is novel by itself                                                     |
| CAD preparation            | DXF polygonisation, label attachment, configured corrections, shared-wall normalisation, door/open-boundary construction and diagnostics      | A potentially useful _quality-controlled conversion workflow_, but not evidence of fully automatic extraction across arbitrary hospitals |
| Contact analysis           | Building/floor-aware proximity detection, exclusion of different known rooms, episode construction, pair types and network outputs            | Supports contact-opportunity studies; does not itself estimate acquisition, colonisation or infection                                    |
| CPU infection dynamics     | Infection-status fields and demonstration seeding exist; no infection-update step was found in the inspected CPU loop                         | The CPU sweep is not an AMR transmission experiment                                                                                      |
| GPU infection dynamics     | A separate same-floor proximity kernel identifies an infected neighbour; host code directly changes susceptible status to infected            | A demonstration mechanism, scientifically different from the CPU path; not pathogen-specific AMR dynamics                                |
| Event-data analysis        | Shift reconstruction, mappings, occupancy/time proxies, categorical Markov baselines and “IRL feasibility” diagnostics                        | A prototype for studying observation and prediction, not a trained or validated IRL system                                               |
| TRE deployment             | Container recipe, locked dependencies and instructions for offline use                                                                        | Deployment infrastructure; no inspected evidence establishes disclosure safety or reproducible multi-TRE deployment                      |
| Software sustainability    | Public development structure, tests, documentation, MIT licence and `python-code/CITATION.cff`                                                | Positive software-publication evidence; these do not validate the model scientifically                                                   |

The distinction between CPU and GPU is not cosmetic. In [`simulation.py`](../python-code/src/amr_hub_abm/simulation.py), the GPU branch invokes an additional physics step after CPU task handling. In [`engine_gpu.py`](../python-code/src/amr_hub_abm/spatial/engine_gpu.py), that step also performs transmission. A paper must not describe a single invariant scientific model that merely switches computational backends unless that equivalence has been established.

The project README describes several agent roles, anonymised outputs and infection propagation more broadly than the inspected implementation demonstrates. Currently, [`agent/enums.py`](../python-code/src/amr_hub_abm/agent/enums.py) distinguishes generic, patient and healthcare-worker agents; adding a label for a visitor or cleaner would not by itself establish a realistic role-specific model. The manuscript should use a capability table similar to this one instead of presenting the project roadmap as completed functionality.

## 4. The literature that most directly limits novelty claims

**Follow-up software comparison:** see [closest software comparators](novelty-review/closest-software-comparators.md) for RTLS_ABM, AMRinference, H-Outbreak, the HDI simulator, H-ABM and SmICS, including verified repository links and reuse limitations. H-Outbreak is an additional precedent identified after the initial bibliography.

### 4.1 Hospital contact and infection modelling are mature starting points

| Primary precedent               | What it already establishes                                                                                        | Consequence for AMR-Hub; critical qualification                                                                                                                                                                                                                        |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Temime et al., 2009][R01]      | Agent-based investigation of peripatetic healthcare workers and superspreading                                     | Staff heterogeneity and movement-mediated risk are old questions. This does not settle realistic trajectory reconstruction.                                                                                                                                            |
| [Hornbeck et al., 2012][R02]    | An ICU sensor contact network used in an infection simulation to investigate highly connected workers and hygiene  | “Empirical contacts plus ABM” is not novel. Sensor contacts and modelled transmission still have different evidential status.                                                                                                                                          |
| [Barnes et al., 2012][R06]      | Effects of contact-network structure and worker behaviour, including worker-to-worker transmission                 | A staffing/behaviour sensitivity study needs a sharper question than “network structure matters.”                                                                                                                                                                      |
| [Curtis et al., 2013][R03]      | Hospital staff contact networks reconstructed from EMR data, with preliminary sensor-based validation              | Routine event logs as proxies for movement are direct prior art. The open question is how much uncertainty those proxies leave unresolved.                                                                                                                             |
| [Vanhems et al., 2013][R04]     | Wearable-sensor measurements of contact timing, duration and role mixing                                           | Provides empirical targets, but its approximately 1.5 m/20 s measurement definition is not interchangeable with AMR-Hub’s 0.1 m/1 s definition.                                                                                                                        |
| [Duval et al., 2018][R05]       | Four months of contact observations in a rehabilitation hospital                                                   | A single synthetic day cannot establish the heterogeneity or temporal generality available in this literature. Different settings must not be pooled uncritically.                                                                                                     |
| [Barker et al., 2018][R08]      | A pathogen-specific hospital ABM assessing multiple CDI interventions                                              | Generic proximity counts are substantially short of the evidence needed for infection-control effectiveness claims. Simulated intervention benefits remain model-dependent.                                                                                            |
| [Caudill and Lawson, 2017][R10] | A model linking inter-host interactions, within-host dynamics and antibiotic resistance                            | AMR-specific mechanisms have explicit prior art. A generic susceptible/infected label is not a resistance mechanism.                                                                                                                                                   |
| [Mietchen et al., 2022][R07]    | Comparison of population-interaction structures and their effects on modelled S. aureus acquisition                | Direct precedent for structural uncertainty. A new study must show what spatial trajectories add beyond contact assignment or mixing structure.                                                                                                                        |
| [Scaria et al., 2023][R09]      | Adaptation and validation of a hospital CDI ABM against primary hospital data                                      | Sets a materially higher validation bar than unit tests or plausible animations. Validation remains specific to the chosen data and endpoints.                                                                                                                         |
| [Leclerc et al., 2024][R11]     | Contact-network-informed modelling of targeted pathogen-control interventions                                      | Intervention ranking from temporal contact data is an established research direction. A new pipeline must justify its additional decisions and uncertainty.                                                                                                            |
| [Thota et al., 2025][R12]       | RTLS-driven staff/device trajectories, digitised hospital layout and a C. difficile exposure model in AnyLogic     | The closest recent challenge to a broad movement-plus-layout novelty claim. It uses a proximity proxy, not direct touch; its stated focus excludes patient infection dynamics. Do not equate its exposure forecasts with independently validated clinical predictions. |
| [Gerada et al., 2026][R13]      | A hospital ABM calibration study addressing gastrointestinal transmission and antibiotic-associated susceptibility | A contemporary comparator for any proposed pathogen-specific AMR extension. Abstract/indexed sections establish scope; this review does not grade its full validation design.                                                                                          |

This literature does **not** imply that every published model is trustworthy. Peer review does not abolish uncertain contact definitions, imported parameters, unobserved adherence, under-identification or the difference between fitting and forecasting. AMR-Hub should compare itself with what these studies actually measure and test, not with their most ambitious introductory language.

A synthetic hospital COVID-19 ABM is also already published. That establishes precedent for this kind of paper, not evidence that another synthetic model with a new interface is scientifically necessary. Publication strategy should aim to resolve a substantive uncertainty, rather than imitate the weakest precedent that passed review. [Michaelides and Sarkadi (2025)][R30].

### 4.2 Routine data and informatics are not empty territory

Curtis and colleagues are especially important because they undermine a tempting “first use of routinely collected operational data” narrative. Their EHR observations are proxies, and their validation is explicitly preliminary; those limitations create room for better observation models, but do not erase their priority. [Curtis et al. (2013)][R03].

At a different resolution, Madhobi and colleagues constructed patient co-location networks across multiple hospitals. Such work demonstrates both the utility and the ambiguity of the word _contact_: a shared unit-day is an exposure proxy, not a centimetre-scale interaction. AMR-Hub’s extra spatial detail should earn its complexity by improving independently measured outcomes. [Madhobi et al. (2022)][R14].

The open-source, openEHR-based SmICS system has already been evaluated at three sites for infection-control task efficiency and usability. It is not an ABM competitor in every respect, but it is a strong comparator for claims about interoperable hospital software and practical deployment. Its reported usability limitations also illustrate why availability of a dashboard is not evidence that practitioners can use it effectively. [Biermann et al. (2025)][R15].

There is also recent work combining genomic, microbiological and patient-mobility information to infer hidden carriers. An AMR-Hub inference manuscript would need to specify whether it estimates movement, exposure, colonisation or transmission sources; these are different inference problems with different data requirements. [Pei et al. (2025)][R16].

### 4.3 General frameworks remove several easy novelty claims

GAMA already supports sophisticated spatial ABMs; Menge provides a modular crowd-simulation architecture; Mesa supplies an established Python ABM ecosystem; and FLAME GPU 2 addresses performant general-purpose ABM on GPUs. None is a substitute for every hospital-specific requirement, but their existence makes “Python,” “modularity,” “real geometry” and “GPU” insufficient contributions in isolation. [Taillandier et al. (2019)][R17], [Curtis, Best and Manocha (2016)][R18], [ter Hoeven et al. (2025)][R19], [Richmond et al. (2023)][R20].

A fair comparison would implement the same small hospital use case in an existing ecosystem and measure what AMR-Hub actually improves: preparation effort, correctness diagnostics, reproducibility, calibration integration or execution cost. Do not use a comparison table that labels other tools “poor at geometry” without a reproducible test. The existing internal tools review is a useful starting list, not publishable comparative evidence.

CAD/plan-to-topology conversion also has prior art. Topological repair and room/door reconstruction have been studied outside healthcare, including floorplan-image parsing and navigation-oriented topology construction. AMR-Hub’s strongest possible geometry argument is **error detection and its downstream scientific consequences**, not the invention of converting plans into rooms and doors. [Wu et al. (2021)][R21], [Han et al. (2023)][R22].

The Health Data Insight HAI Simulator is further evidence that a GAMA hospital environment with roles, amenities, intervention controls and multiple proposed transmission routes is not unprecedented. Its project page is **grey literature**, not proof of peer-reviewed model validity; it belongs in a software landscape comparison, not a table of validated epidemiological models. [HDI project description][R31].

### 4.4 Open code around restricted data is established practice

OpenSAFELY demonstrates that open analytical code can run against sensitive records retained in secure infrastructure. Therefore “the code is public but patient data stay in a TRE” is a valuable design principle, not a new methodological discovery. A credible AMR-Hub paper would show how that principle solves the specific problems of geometry, movement calibration, reproducibility and output release. [Williamson et al. (2020)][R23].

Nor do simulated trajectories automatically become anonymous because direct identifiers are removed. Human mobility can be highly distinctive. The classic mobility-privacy study is not a numerical risk estimate for AMR-Hub, but it directly defeats an assumption that trajectory outputs are inherently safe to export. [de Montjoye et al. (2013)][R24].

## 5. Scientific criticism of the present implementation

### 5.1 The current CPU sweep cannot answer an AMR transmission question

The inspected CPU execution path handles tasks, movement, internal needs and recording. Infection status is stored, but I did not find a CPU update that generates new infections. The sweep measures proximity observations and episode summaries after simulation. Those are valid computational outcomes, but none is an observed or modelled count of resistance acquisition.

The GPU path uses a hard-coded search radius of 2.0 and immediately changes susceptible agents to infected when it identifies an eligible infected neighbour. It does not, in the inspected kernel, implement a pathogen-specific dose-response, colonisation/infection distinction, hand contamination, antibiotic selection, clearance, environmental persistence or a sampling/diagnosis process. An AMR transmission model need not include every one of these mechanisms; it must justify the subset needed for its question. The current mechanism does not provide that justification. See [`engine_gpu.py`, proximity kernel and host update](../python-code/src/amr_hub_abm/spatial/engine_gpu.py).

**Required correction to claims:** describe the present CPU work as _hospital workflow and contact-opportunity simulation_. Reserve pathogen-specific transmission language for a documented, calibrated extension. Modelling spread of an already-resistant organism is a legitimate AMR question without modelling resistance evolution, but even that requires a defined organism and transmission mechanism.

### 5.2 CPU and GPU are different scientific implementations

The GPU uses approximate perpendicular angular drift, target overshoot clamping, ray-based collision checks, float32 staging, a tick/thread-based random stream and batched updates. The CPU uses trigonometric angular perturbation, independent component multipliers, room lookup and endpoint-radius wall checks. The simulation also shuffles agent order. Equal parameter names do not imply equal stochastic processes.

More seriously, the GPU proximity kernel filters by floor ID but does not receive building or room identity, or test wall occlusion. Positions are staged with a common z coordinate, and the mesh builder combines walls across buildings/floors. These are **static code findings implying multi-space correctness risks**, not a claim that a particular observed outbreak crossed a wall. Construct dedicated counterexamples before relying on this path. The inspected GPU tests largely exercise mocked initialization and API helpers; they do not establish end-to-end statistical equivalence.

**Publication blocker:** speedup claims must compare the same model, including identical outcome definitions and infection semantics. A faster different model is an approximation study, which needs error bounds or empirical error characterization. It is not a transparent acceleration result.

### 5.3 Collision rejection does not guarantee rejection of movement

`SpatialQuery.try_move_one_step()` returns the last candidate after exhausting the retry loop. In a minimal probe where every room lookup returns `None`, five failed attempts starting at `(0, 0)` returned `(1, 0)`. The GPU code explicitly retains the final failed candidate as well. See [probe output](novelty-review/code-probes.json) and [`engine.py`](../python-code/src/amr_hub_abm/spatial/engine.py).

This does not prove that the running sweep frequently generates invalid positions. It proves that “collision-safe movement” is not an invariant of the algorithm. Quantify out-of-bounds positions, wall crossings, retry exhaustion and unresolved-room contacts before interpreting crowding effects. A rare violation can matter disproportionately if it opens a shortcut or changes shared-resource access. Fixing it later should create a new experiment version; do not quietly combine corrected and legacy results.

### 5.4 “Stochasticity” couples two different interventions

For level `s`, the CPU proposal adds an angle perturbation with standard deviation `s` degrees and independently multiplies x and y displacement by `1 + Normal(0, s)`. Thus the same parameter changes direction and displacement magnitude. At `s = 1`, the angular perturbation is only one degree while each displacement multiplier has unit standard deviation. Calling this a pure heading-noise study is wrong.

A component multiplier reverses sign with probability `Phi(-1/s)` for `s > 0`: approximately 0.0032%, 2.28%, 9.12% and 15.87% at the four positive sweep levels. These are analytic proposal probabilities, not measured accepted-movement frequencies. Collision filtering and target updates can alter the realised distribution.

There is a further structural issue: independent x/y multipliers make the proposal distribution depend on the coordinate axes. A path aligned with the x axis and the same path rotated by 45 degrees do not generally experience the same directional perturbations. This is an analytical consequence of component-wise noise; its effect on hospital outcomes has not been measured. Add rotated-copy geometry tests and compare with noise defined in forward/lateral coordinates.

**Required experiment:** separate angular noise, longitudinal speed noise and lateral noise; compare distributions with positive-only speed factors; check timestep scaling; and quantify whether the scientific conclusion survives those choices. The existing coupled sweep can serve as the legacy reference condition.

### 5.5 Speed and time units need a scientific contract

The synthetic configuration sets fixed speed to `0.01` coordinate units per timestep and the timestep to one second. If coordinates represent metres, this is 0.01 m/s. Either that is an intentional effective-progress model, or it is not a realistic walking-speed parameter. The paper must say which. CAD extraction tolerances are explicitly in source coordinate units, so units cannot be inferred merely from a “metres” label in the contact CLI.

Deadline pacing divides remaining Euclidean distance by remaining time until the planned task start, then reverts to base speed after the deadline. The inspected update has no explicit physiological maximum speed. Moreover, the strategies differ in dispatch timing and opportunities for inserting other tasks; their contrast is not necessarily an isolated speed effect. See [`agent.py`](../python-code/src/amr_hub_abm/agent/agent.py) and [`tasklist.py`](../python-code/src/amr_hub_abm/task/tasklist.py).

Before arguing that one strategy is safer, report speed distributions, route lengths, waiting, lateness, missed/completed tasks and care delivered. A model can reduce contacts by failing to deliver care or by moving implausibly; neither is an acceptable operational improvement.

### 5.6 Contact measurements need observation semantics

The 0.1 m threshold is a modelling choice, not a validated universal definition of an infection-relevant encounter. A point-agent proximity event is not necessarily touch, shared air, hand-mediated exposure or contact with a contaminated object. Existing empirical studies use materially different sensing ranges and sampling intervals; comparisons require an explicit measurement model. [Vanhems et al. (2013)][R04].

The detector excludes contacts only when both rooms are known and different. If a room is unresolved, a nearby pair can remain in the output. This interacts with the movement issue above. Report the fraction of observations with unresolved spatial classification rather than allowing them to silently contribute to apparently room-aware estimates.

The episode convention is `number of observations × sampling interval`. The probe with observations at `t = 0` and `t = 1` yields an episode duration of 2, although the time between endpoints is 1. This can be a legitimate interval-support convention, but the sweep records both initial and terminal states: explain which interval the terminal observation represents and prevent inadvertent exposure beyond the observation window. It is a measurement-definition issue until the intended support is specified, not a claim that every reported episode is incorrectly measured.

At a fixed one-second interval, total observation counts and total pair-contact seconds are mathematically redundant under this convention. Presenting them in different panels does not supply independent corroboration. Longest episodes are extreme-value statistics and need distributional inspection, not only means and symmetric confidence intervals.

### 5.7 The staffing sweep mixes staffing, activity and resource pressure

The experiment retains four patients and a small shared-resource layout while adding workers with generated schedules. Therefore increasing HCWs changes both the number of possible pairs and the volume/timing of activity in a fixed environment. It is not a controlled staffing-policy comparison at fixed clinical demand.

Possible HCW-HCW pairs grow as `H(H-1)/2`; possible HCW-patient pairs grow as `4H`. Growth in total contacts is partly built into the design. Changes in pair-type percentages may reflect the changing denominator, not a new behavioural mechanism. Report contacts per possible pair, per active-agent hour and per delivered task alongside totals; also stratify by room and activity. Preserve the original endpoint so normalisation does not conceal absolute burden.

The three-workstation synthetic staff room is useful as a stress test. It is not a representative staffing configuration. Add a second design holding total care demand fixed and varying assignment across workers, and a third scaling resource capacity or floor area. Separate staffing from occupancy density, workload and saturation.

Thirty seeds estimate conditional Monte Carlo variability. They do not sample hospitals, patients, work rosters or measurement errors. One generated schedule per HCW count cannot support population-level claims about real staffing patterns. Common seeds across conditions may support paired comparisons, but paths can consume random numbers differently; do not assume perfect coupling. Use replicate-level contrasts and report Monte Carlo error separately from parameter, observation and structural uncertainty.

### 5.8 The prediction prototype does not establish IRL feasibility

The event-analysis code has useful baseline machinery, but its strongest printed conclusions are unjustified:

- `run_learnability_stats()` and `run_compare_state_variants()` randomly split transition pairs. Transitions from the same staff member or shift can enter both train and test sets.
- `run_irl_feasibility()` improves on this by splitting whole shifts, but that is not necessarily a held-out staff, ward or future-time evaluation.
- Occupancy is annotated from touchpoints within a symmetric window extending to `t + 5 minutes`. That is retrospective information. Using it for online prediction without acknowledging the future window would leak unavailable information.
- The categorical count model is not a proven ceiling on achievable prediction. Fixed accuracy gains of 0.02 or 0.03 do not establish whether IRL “will work.” Selecting the best representation on the same test set also requires a separate final evaluation set.
- Time since the first recorded event is a proxy, not a measurement of physiological fatigue; room touchpoints are not continuous occupancy observations.

These are grounded in [`markov_analyzer.py`](../python-code/data_analysis/markov_analyzer.py) and [`data_wrangler.py`](../python-code/data_analysis/data_wrangler.py). They matter if the output is presented as prediction evidence; retrospective descriptive analysis has different requirements.

IRL concerns which rewards can explain behaviour under assumptions about dynamics and decision-making. Predictive structure is not reward identifiability, and poor performance of one finite-sample baseline does not prove that all policy learning is impossible. A defensible learning study should start with observation models, leakage-resistant splits and simple semi-Markov or supervised baselines. Only introduce IRL if transferable behaviour or a particular counterfactual requires it. [Ng and Russell (2000)][R28].

### 5.9 TRE readiness and anonymisation are currently overclaimed

A container is not a TRE, an output-release procedure, or a privacy guarantee. The inspected Dockerfile also uses floating base/tool image tags; locking Python dependencies alone does not freeze the entire build. The TRE README’s example entrypoint descriptions differ from the actual Docker entrypoint. These are fixable engineering issues, but publication-quality reproducibility should be demonstrated with a clean offline build/run and recorded image digest.

A strong secure-workflow paper would document which inputs remain restricted, which outputs require review, how results are independently recomputed, what disclosure tests are used and how researcher usability is evaluated. Synthetic fixtures support public verification; they do not prove that outputs fitted to real people can leave the TRE. [Williamson et al. (2020)][R23], [de Montjoye et al. (2013)][R24].

## 6. Which novelty claims could survive review?

A subsequent [five-criteria comparison](novelty-review/five-criteria-comparison.md) distinguishes current code from the planned BDI and multi-organism programme, alongside competitor capabilities.

| Proposed claim                            | Current assessment                                                                | Evidence needed to strengthen it                                                                                               |
| ----------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| “A new hospital AMR ABM”                  | Too broad; crowded prior art and incomplete present mechanisms                    | A narrowly defined biological question, explicit mechanism and independent validation                                          |
| “An open Python implementation”           | Useful accessibility, weak scientific novelty                                     | Substantial reusable research functionality, design justification and demonstrated use                                         |
| “Realistic hospital layouts”              | Geometry exists; realism not established                                          | Topological/metric validation, unit provenance and outcome sensitivity to geometry errors                                      |
| “Routine logs reconstruct staff contacts” | Direct precedent exists                                                           | Uncertainty-aware reconstruction with observation-error modelling and independent contact validation                           |
| “Deadline-paced movement improves safety” | Unsupported; current outcome is proximity and strategy changes several behaviours | Care-quality constraints, empirical movement plausibility, structural alternatives and a justified exposure/infection endpoint |
| “Stochasticity changes contact patterns”  | Expected and probably insufficient alone                                          | A generalizable failure boundary, uncertainty decomposition, or reversal of a substantive conclusion across plausible models   |
| “GPU acceleration”                        | Implemented branch; equivalence and speedup not established here                  | Matched semantics, correctness tests, measured accuracy/performance tradeoff and end-to-end benchmarks                         |
| “TRE-compatible reproducible modelling”   | Credible engineering direction; not first-in-field                                | Independently repeated deployment and a demonstrated governance/reproducibility contribution                                   |
| “Automatic CAD ingestion”                 | Configuration-dependent, partly manual correction workflow                        | A diverse annotated benchmark, topology accuracy, failures and manual-effort accounting                                        |

**Most defensible present wording:** “AMR-Hub is an open research software framework for task-driven hospital workflow and contact-opportunity simulation, with geometry-preparation tools and support for restricted-data deployment.”

**Most promising future methods claim:** “We quantify how incomplete event observations and movement-model assumptions propagate into uncertainty in hospital contact-network estimates.” This becomes novel only if the experiments establish something beyond prior contact-network and structural-model comparisons.

## 6A. Comparison against the five proposed distinguishing criteria

This comparison incorporates the investigator’s stated BDI development plan and multi-organism ambition, while distinguishing them from verified current implementation. RCD means routinely collected data.

### 6A.1 Criteria and fair interpretation

1. **Open source:** explicit software licence, distinct from an accessible article or public repository.
2. **Real hospital layout:** distinguish metric geometry from a room/ward hierarchy or patient co-location network. All can be appropriate, but they provide different detail.
3. **Routine staff movement/activity data:** observed operational records collected during care, distinct from dedicated research RTLS deployment, modelled schedules, patient movement records or aggregate hand-hygiene measurements.
4. **BDI:** beliefs, desires and intentions used in an agent reasoning process. Internal variables, task queues and state machines alone do not establish a complete BDI architecture. Absence of documentation is labelled unverified rather than proof of absence.
5. **Multiple strains/pathogens:** distinguish reuse of a contact engine, separate simulations with pathogen-specific parameters, simultaneous competing strains/co-infection, and displaying multiple organisms in surveillance software. These are not interchangeable capabilities.

### 6A.2 Comparison matrix

| Candidate                                           | Open source                                                                       | Real hospital layout                                                                                                  | Routine staff records driving movement                                                                                                | BDI agent reasoning                                                                                  | Organism/strain scope                                                                                                                           |
| --------------------------------------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **AMR-Hub: current code and stated UCLH programme** | MIT                                                                               | CAD/DXF conversion and spatial engine implemented; UCLH deployment planned, not independently assessed here           | Event-to-task ingestion implemented; routine UCLH staff records confirmed by investigator for planned application                     | Supporting needs/task components implemented; complete BDI loop not verified; completion planned     | Generic contact layer can support multiple organism studies; pathogen-specific transmission and simultaneous multi-strain dynamics not verified |
| **RTLS_ABM**                                        | Public AnyLogic model; explicit open-source licence unverified                    | Digitised real hospital floorplan; original CAD format unverified                                                     | Measured staff/device trajectories from a dedicated UWB RTLS deployment; not demonstrated as pre-existing routine operational records | Not documented in inspected sources; movement replay and disease-state logic are not evidence of BDI | Published application is C. difficile; adjustable parameters do not demonstrate multiple validated pathogens or interacting strains             |
| **AMRinference**                                    | Apache-2.0; MATLAB/C                                                              | Actual patient-location network from administrative records; no metric CAD movement model demonstrated                | No explicit observed staff movement; patient records supply network                                                                   | No BDI reasoning described; probabilistic carriage inference is a different mechanism                | CRKP application with genomic information; genomic distinctions are not evidence of concurrent multi-strain dynamics                            |
| **H-Outbreak**                                      | BSD-3-Clause; Python                                                              | Hospital hierarchy based on a real Spanish hospital; no CAD metric movement demonstrated                              | No; patients are the only agents                                                                                                      | No BDI described; patient rules and disease-state transitions                                        | Paper explicitly assumes one microorganism; CDI application; broader reuse is distinct from demonstrated multi-strain operation                 |
| **HDI HAI Simulator**                               | Specific model licence/source availability unverified; GAMA itself is open source | QGIS floorplan/furniture shapefiles; provenance of a particular real hospital deployment unverified                   | Staff agents and schedules; empirical movement calibration described as future work                                                   | Unverified for this model. GAMA supports BDI, but platform capability does not establish model use   | General HAI concept mentioning MRSA/CDI and several routes; calibrated pathogen modules or simultaneous strains not established                 |
| **H-ABM**                                           | Public code/licence not verified                                                  | Actual hospital room/ward organisation, common rooms and cafeteria; not demonstrated as CAD-resolved walking geometry | Staff agents follow rules; observed hand hygiene and other hospital summaries inform parameters, not individual movement trajectories | No BDI described; behavioural rules and disease-state model                                          | CDI-specific published model; multi-strain dynamics not demonstrated                                                                            |
| **SmICS**                                           | Core Apache-2.0; visualisation licence unverified                                 | Actual ward/room stay identifiers and co-location; no physical floorplan simulator demonstrated                       | No staff movement input described                                                                                                     | Not applicable: surveillance/investigation application, not an agent simulator                       | Multiple organism/resistance findings can be analysed; this is surveillance breadth, not multi-strain transmission simulation                   |

### 6A.3 Verification of AMR-Hub claims

**Open source and geometry:** [MIT licence](../LICENSE) and [floorplan extraction documentation](../python-code/docs/floorplan_extraction.md) support the first two engineering capabilities. Geometry support is demonstrated by implementation; successful clinical deployment is a separate evidential question.

**Routinely collected data:** [simulation_factory.py](../python-code/src/amr_hub_abm/simulation_factory.py) reads and validates location events, then builds agent tasks. The UCLH provenance and planned year-long coverage are investigator-provided context. The public toy input is not the clinical dataset, and absence of that dataset from Git is appropriate.

**BDI status:** [internal_state.py](../python-code/src/amr_hub_abm/agent/internal_state.py) implements hunger, toilet need and fatigue, with updates and reset helpers. Its documentation calls this a state-only implementation and describes resets for future task integrations. [agent.py](../python-code/src/amr_hub_abm/agent/agent.py) and [tasklist.py](../python-code/src/amr_hub_abm/task/tasklist.py) implement lifecycle handlers, due-time/priority selection, suspension/resumption and opportunistic chair tasks. These are reusable foundations. I did not find an explicit belief-update system, competing-desire deliberation, or an intention-selection/reconsideration loop linking needs to decisions. Therefore the verified wording is **“BDI planned, with internal-state and task-execution foundations implemented”**, rather than a completed or experimentally evaluated BDI agent. This conclusion is based on execution-path inspection as well as text search, not class names alone.

**Strain scope:** [agent.py](../python-code/src/amr_hub_abm/agent/agent.py) contains one `infection_status` and a generic `infection_details` dictionary; [enums.py](../python-code/src/amr_hub_abm/agent/enums.py) supplies generic susceptible/exposed/infected/recovered states. No operational strain-indexed state or pathogen-specific transmission registry was found. The README describes multiple-pathogen modelling as future development. A generic movement/contact engine is useful across organisms, but does not itself supply organism-specific transmission, resistance mechanisms, mixed colonisation or strain competition.

### 6A.4 Publication interpretation

The proposed combination of open software, CAD-derived geometry, routine staff event inputs, BDI behaviour and organism-specific model extensions is a plausible research programme. It is not currently a five-feature implemented superiority claim. BDI itself is established: [GAMA already supplies a BDI architecture](https://gama-platform.org/wiki/BuiltInArchitectures). Its contribution here would need to be the hospital-specific decision model and demonstrated benefit over simpler rules.

For the present software paper, emphasize open geometry-constrained workflow/contact modelling and event ingestion. For the methods paper, test whether routine staff information improves contact or outcome inference under uncertain patient presence. For a later BDI contribution, compare its predictions and counterfactual behaviour with the existing task scheduler on held-out observations. For a multi-organism contribution, specify whether this means separate parameterised runs or simultaneous strains, then validate the relevant mechanisms. Do not award AMR-Hub planned capabilities while denying competitors comparable extensibility.

### 6A.5 Primary sources

- RTLS_ABM: [repository](https://github.com/MVL-PATHS/RTLS_ABM), [paper](https://doi.org/10.1145/3765612.3767222).
- AMRinference: [repository](https://github.com/SenPei-CU/AMRinference), [paper](https://www.nature.com/articles/s41467-025-65241-w).
- H-Outbreak: [repository](https://github.com/denissekim/H-outbreak), [paper](https://www.nature.com/articles/s41598-023-47296-1).
- HDI: [project description](https://healthdatainsight.org.uk/project/healthcare-associated-infection-simulator/); grey literature, not peer-reviewed validation.
- H-ABM: [paper](https://doi.org/10.1371/journal.pone.0284611).
- SmICS: [paper](https://www.nature.com/articles/s41746-025-01795-9), [Core](https://github.com/highmed/SmICSCore).
- BDI semantics/platform capability: [GAMA BDI tutorial](https://gama-platform.org/wiki/1.9.1/BDIAgents_step2).

Competitor assessments concern the inspected publication/repository versions. “Not documented” and “not verified” must not be converted into categorical absence in a manuscript table without further source inspection or author clarification.

## 7. Ranked publication routes and concrete study designs

These are alternative or sequential projects, not a promise of eight papers. Effort categories are relative planning judgments: _bounded engineering_ means an achievable package of corrections and evaluation; _substantial methods_ means new modelling and experiments; _data-dependent_ means timing is dominated by access and validation. No acceptance probability is implied.

### Route A — Research software paper: the nearest viable route

**Working title:** _AMR-Hub: reproducible task-driven simulation of hospital workflows and contact opportunities._

**Contribution:** a documented, reusable pipeline with explicit scientific contracts for event inputs, geometry, task execution and contact outputs. Its value is the ability of another researcher to use and test it for a real research problem. It need not invent ABM, Python or hospital simulation.

**Minimum evidence package:**

1. Define the supported CPU model and label experimental GPU/transmission features accurately. Resolve or explicitly constrain the correctness issues in Section 5.
2. Supply an ODD description and a STRESS-ABS experiment specification, including time units, update order, noise, resource allocation and measurement conventions. These are established reporting tools, not decorations. [Grimm et al. (2020)][R25], [Monks et al. (2019)][R26].
3. Demonstrate two materially different synthetic layouts and input schedules, with a short reproducible example and a full experiment manifest.
4. Have a researcher outside the implementation team install, run and adapt an example; record the changes and obstacles. This is a proposed usability test, not a journal-mandated sample size.
5. Explain why the standalone engine is needed alongside Mesa/GAMA, rather than claiming that those frameworks cannot do spatial modelling.
6. Archive a tagged release with a persistent identifier, update existing citation metadata and supply contributor/support information. FAIR4RS is a useful framework for this work. [Barker et al. (2022)][R27].

**Likely venues:** JOSS, SoftwareX or Journal of Open Research Software (JORS). Choose one principal software publication. **Readiness:** closest route, but not ready to market as a validated AMR simulator. **Effort:** bounded engineering plus demonstrable research use. **Likely rejection:** feature inventory without a clear research need; reinvention without justification; clinical language exceeding functionality.

**Stop or narrow the claim if:** the only advantage over an existing platform is personal preference, or external users cannot reproduce the examples.

### Route B — Structural uncertainty in hospital contact models: strongest synthetic-data route

**Working title:** _When movement assumptions change hospital contact estimates: a reproducible study of structural uncertainty._

**Question:** are contrasts between staffing/workflow scenarios stable under equally plausible movement, geometry and contact-observation assumptions?

This is more valuable than another plot showing that larger staff populations create more pair contacts. The closest methodological comparator is the literature on interaction-structure sensitivity, so the new contribution must involve spatial reconstruction or decision robustness that those simpler models do not resolve. [Mietchen et al. (2022)][R07].

**Study design:** retain the current sweep as a frozen legacy experiment. Build a second, corrected and explicitly versioned model. Compare fixed and deadline-paced travel with at least a schedule-preserving route baseline and a dwell/travel-time model. Independently vary angular and speed noise; include rotated copies of layouts; measure invalid movement, missed tasks and care completion. Cross several layout families, schedule draws and resource-capacity regimes, rather than multiplying seeds for one fixture.

Predefine a primary contrast: for example, the difference in contact time per delivered patient-care task between two scheduling policies under a fixed total workload. Report its sign and magnitude across structural alternatives. Use an explicit model-index factor and nested schedule/seed replication; do not treat every timestep or every contact as an independent experimental subject. Sensitivity ranges should be empirically motivated or explicitly labelled exploratory.

Include sampling interval, contact distance, unresolved-position handling and endpoint conventions in the measurement layer. A timestep change must preserve physical speed, durations and the intended noise process; otherwise it is not a numerical-convergence experiment.

**Minimum publishable result:** a reproducible explanation of when a substantive conclusion survives, fails or becomes unidentified, together with diagnostics that detect that boundary. A null result can be valuable if it establishes robust conditions across a well-motivated range. A result produced solely by the rejected-movement defect is a bug report unless it leads to a broader, independently tested methodological lesson.

**Likely venues:** Journal of Simulation, JASSS or PLOS ONE; PLOS Computational Biology only if a substantial biological/methodological insight is established. **Readiness:** promising next project, current sweep insufficient. **Effort:** substantial methods, possible without clinical data. **Likely rejection:** arbitrary ranges, one toy ward, obvious pair-count effects, or conclusions that disappear after fixing basic correctness.

### Route C — Routine-event reconstruction and identifiability: priority methods route for UCLH

**Working title:** _What can routine hospital event logs tell us about contact networks? Identifiability and validation of constrained movement reconstruction._

**Question:** how much of a contact network can be inferred from doors, workstation activity, care documentation and rosters, and what remains indeterminate?

The most important comparator is Curtis et al.’s EMR-based reconstruction, supplemented by empirical proximity data and recent RTLS integration. The contribution cannot be merely reading another database format. [Curtis et al. (2013)][R03], [Vanhems et al. (2013)][R04], [Thota et al. (2025)][R12].

**Stage 1, controlled identification:** start with fully observed synthetic trajectories or an approved sensor dataset; censor it into event streams with controlled missingness, timestamp error and location ambiguity. Test whether the method recovers room occupancy, dwell times, contact duration distributions and role mixing. Include cases with multiple physically feasible trajectories producing the same logs but different contacts. Such counterexamples expose the inferential limit directly.

**Stage 2, competing methods:** compare last-observation-carried-forward, feasible shortest-path interpolation, empirical semi-Markov dwell/travel models, schedule-constrained simulation and the proposed uncertainty-aware method. Evaluate whether uncertainty intervals cover the held-out truth; a single plausible animated path is not a successful uncertainty estimate.

**Stage 3, independent validation:** train on one time block and evaluate later blocks; hold out staff and, where possible, a ward or site. Compare matched measurement definitions. A sensor range must not be silently substituted for physical touch. Assess failure modes by role, event density and missingness, not only pooled mean error.

**Endpoints:** interval coverage and width, occupancy/dwell error, temporal contact precision/recall at a declared resolution, mixing-matrix error, duration-distribution distance and accuracy of a predefined downstream policy contrast. Choose these before inspecting which method looks best. If contacts cannot be identified, publish bounds or calibrated uncertainty rather than claiming recovered truth.

**Likely venues:** Journal of Biomedical Informatics, BMC Medical Informatics and Decision Making, or PLOS Computational Biology if methodological substance and biological relevance justify it. npj Digital Medicine is a stretch target conditional on convincing real-world validation and utility. These are editorial-fit judgments, not evidence of current readiness.

**Readiness:** best scientific direction, incomplete implementation and validation. **Effort:** substantial methods plus independent observation data. **Likely rejection:** simulated truth generated by the same model used for reconstruction; random transition splits; no observation model; or claiming hidden trajectories are uniquely identified from sparse logs.

### Route D — Geometry preparation and error propagation

**Working title:** _From architectural drawings to auditable hospital simulation geometry: topology validation and its effect on contact estimates._

**Contribution:** documented repair and diagnostics for clinically meaningful connectivity, with measured preparation effort and downstream consequences. Existing image-parsing and navigation-topology studies require comparison; DWG/DXF-to-YAML conversion alone is not enough. [Wu et al. (2021)][R21], [Han et al. (2023)][R22].

**Study design:** assemble a legally shareable, annotated set spanning drawing conventions, wall thicknesses, non-orthogonal rooms, open boundaries, ambiguous door symbols and multiple floors. Compare a manually curated reference with naive polygonisation, a reasonable existing conversion baseline and the AMR-Hub workflow. Measure room/door precision and recall, adjacency accuracy, reachability errors, dimensional error and manual correction time. Polygon overlap alone is insufficient: a visually tiny missing doorway can disconnect a ward.

Inject controlled geometric defects into otherwise identical models and quantify changes in route feasibility, delay and contact estimates. Report rejected/ambiguous cases and operator decisions. If conversion requires substantial site-specific configuration, count that effort rather than hiding it behind “automatic.”

**Likely venues:** SoftwareX/JORS for a reusable converter; ISPRS International Journal of Geo-Information for a substantive spatial method; an applied built-environment venue only with a credible design application. **Readiness:** implementation exists, independent benchmark missing. **Effort:** bounded-to-substantial evaluation, including annotation. **Likely rejection:** a standard geometry pipeline tested only on its development drawing.

### Route E — Scientifically equivalent GPU execution or quantified approximation

**Working title:** _Correctness and performance trade-offs in GPU-accelerated hospital agent-based simulation._

**Contribution:** a defined equivalence contract, or a deliberately approximate solver with characterised error. A generic “we used Warp” paper is weak against existing GPU ABM frameworks. [Richmond et al. (2023)][R20].

**First experiment:** construct single-agent, two-agent, wall/door, distinct-room, repeated-floor-ID and overlapping-building-coordinate cases. Test task completion, legal positions and transmission eligibility. Separate deterministic equivalence from distributional equivalence of stochastic outputs. Match random-stream policy where possible; otherwise use meaningful distributional tolerances tied to scientific endpoints.

**Benchmark:** include CPU reference, optimised/vectorised CPU where applicable, GPU and a fair established-framework comparison if feasible. Measure warm-up/JIT separately, then report end-to-end time including preparation, task logic, host-device transfer, recording and contact analysis. Vary agents, geometry complexity and recording volume. Report memory, device/software versions, precision and crossover size. A fast kernel may deliver little end-to-end improvement if serial task logic dominates.

**Readiness:** currently blocked by semantics and validation gaps. **Effort:** substantial engineering. **Likely venues:** Software: Practice and Experience, a computational-software venue, or a specialist simulation/HPC conference. **Likely rejection:** speedup purchased by changing the model, comparisons with an avoidably slow baseline, or benchmarks too small to establish scaling. Do not publish this before resolving the multiple-space and infection differences.

### Route F — Reproducible simulation within secure research environments

**Working title:** _Reproducible hospital simulation across secure research environments: an evaluated open-code workflow._

**Contribution:** demonstrated transferability of an actual research workflow under restricted data access, not a Docker recipe. OpenSAFELY and SmICS provide established precedents for secure/open computation and reusable hospital informatics respectively. [Williamson et al. (2020)][R23], [Biermann et al. (2025)][R15].

**Study design:** have independent researchers reproduce a specified analysis in at least two deployment contexts, ideally independent TREs. Test offline installation, version capture, input mapping, parameter recovery, run provenance, approved output release and reproducibility across environments. Measure completion rates, preparation time, support interventions and discrepancies. The number of sites is a proposed design target, not a guarantee that two sites alone suffice.

Include a threat model and an evaluated release policy for calibrated parameters, networks and trajectories. Distinguish public synthetic fixtures, approved aggregates and restricted microdata. Do not describe data as anonymous solely because identifiers were replaced. A locked dependency file is useful but not a complete provenance record.

**Likely venues:** JORS’s research-software practice section, SoftwareX as part of the main software contribution, or a health-informatics venue if deployment evaluation is substantial. **Readiness:** premature as a standalone paper. **Effort:** data/governance-dependent. **Likely rejection:** a generic container deployment with no independent use or measurable advantage.

### Route G — A reusable benchmark/data resource

**Working title:** _A benchmark for hospital movement-to-contact reconstruction under observation and geometry uncertainty._

**Contribution:** an externally useful challenge with known truth and independent baseline implementations. A ZIP of trajectories from the present fixture is not enough. A suitable resource could pair multiple synthetic layouts and latent trajectories with deliberately censored event streams, measurement models, reference contacts and predefined train/test splits.

Document generator assumptions, licences, seeds, versions, units and each intended use. Prevent circular evaluation by generating test cases from more than the model family used by the leading baseline. Include malformed geometry and hard negative contact cases. Demonstrate usefulness with independent methods and external users. Data quality and reuse are the contribution; “synthetic” alone is neither novelty nor a guarantee of privacy when parameters were fitted to restricted people.

**Likely venues:** Scientific Data if the resource meets its technical-validation and reuse standards, or Data in Brief for a narrower data article. [Scientific Data submission guidance][R35], [Elsevier Research Elements][R34]. **Readiness:** prospective; present outputs are experiment results rather than a general benchmark. **Effort:** substantial dataset design. **Likely rejection:** one-generator, one-layout circular benchmark or a data article duplicating the methods paper without independent reuse value.

### Route H — A pathogen-specific operational or infection-control application

**Working title:** _Validated effects of [a specified workflow intervention] on [a specified organism and endpoint] in [a defined hospital setting]._

Choose the question before expanding the mechanism. Suitable examples might concern staff assignment, shared-equipment workflows or the placement of resources. Model care delivery and feasibility alongside infection-relevant outcomes. A proposal to increase staffing, alter patient contact or rearrange care must represent the corresponding workload and clinical constraints.

For a resistant-organism transmission question, define acquisition/colonisation/infection states, transmission routes, importation, persistence and the observation process as needed. Calibrate on one dataset; assess temporal or external validation; test intervention predictions against an independently observed change where possible. Explain the causal assumptions behind counterfactuals. Calibration to baseline incidence alone does not validate the mechanism or the intervention effect. [Barker et al. (2018)][R08], [Scaria et al. (2023)][R09], [Gerada et al. (2026)][R13].

**Likely venues:** Journal of Hospital Infection or Infection Control & Hospital Epidemiology for a convincing infection-control study; PLOS ONE for a rigorous more limited application. A clinical or digital-health flagship is conditional on independently compelling evidence, not on the software branding.

**Readiness:** a concrete planned UCLH application with investigator-confirmed data streams; clinical validation has not yet been demonstrated. The CPU sweep alone does not support transmission claims. **Effort:** substantial, dependent on governed data preparation, endpoint feasibility and interdisciplinary work. **Likely rejection:** proximity presented as infection risk; unidentified fitted parameters; no independent validation; or a policy recommendation that reduces care delivery to reduce contacts.

## 7A. Revised study design for the planned year-long UCLH ward application

This section supersedes any implication that the toy fixture describes the intended clinical evidence base. Its small patient count, generated schedules and simplified layout limit conclusions from that experiment; they are not descriptions of the UCLH ward. Code-level mechanism and measurement concerns still apply wherever the same implementation is used clinically.

### What the confirmed data streams enable

| Investigator-confirmed stream                                                             | Proposed use                                                                                     | Remaining uncertainty to resolve inside the approved environment                                                                                                                                                       |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Routinely collected staff location and activity                                           | Estimate activity schedules, observed location transitions and workflow variation                | Sampling frequency, event-triggered versus continuous recording, spatial precision, missingness, linkage across shifts and changes in collection practice                                                              |
| Ward CAD floorplans                                                                       | Build and verify rooms, doors, barriers and work locations                                       | Units, as-built accuracy, temporary closures and changes during the year; a floorplan alone does not record occupancy                                                                                                  |
| Patient-linked positive and negative clinical testing time series                         | Define longitudinal observed detection outcomes and compare models against held-out observations | Specimen versus reporting date, specimen-location attribution, repeat specimens, resistance phenotype, testing indications and volume still need assessment; testing is clinically indicated, not systematic screening |
| No patient movement or direct ward admission/discharge records; stays inferred from tests | Treat patient presence, locations and turnover as latent quantities constrained by observations  | First/last tests are not observed admission/discharge boundaries; between-test continuity, transfers, readmissions and never-tested patients are unresolved; aggregate census availability is unconfirmed              |

Routine staff records are an important empirical input, but their existence does not establish continuous trajectories or centimetre-scale contact accuracy. First assess their resolution; use room transitions or activity timing as primary movement endpoints if finer contact truth is unavailable. CAD constraints reduce the set of feasible paths without selecting a unique actual path. Routine-data contact reconstruction has precedent; the contribution must be the demonstrated accuracy, uncertainty treatment or scientific utility of this particular method. [Curtis et al. (2013)][R03].

### A concrete, testable primary question

**Proposed question:** Does incorporating routine staff workflow and ward geometry improve temporally held-out prediction of a specified organism's observed testing outcomes compared with simpler time-series and aggregate-mixing models, and how sensitive is that improvement to unobserved patient location and testing assumptions?

This is a candidate protocol, not a prediction that the spatial ABM will win. If the outcome series is too sparse, or testing practice cannot be represented adequately, prioritise the workflow/reconstruction methods paper and report the infection-outcome analysis as exploratory or infeasible. One year of records supplies repeated observations from one ward; it is not a year of independent experiments or evidence of transportability across hospitals.

Keep the biological and observation models distinct. A positive specimen is an observed detection, not a directly observed acquisition time or transmission edge. Define colonisation, clinical infection and resistance status according to the actual organism and available fields. Existing hospital inference work explicitly represents incomplete testing rather than equating recorded detections with all carriers. [Pei et al. (2025)][R16]. Patient-linked positive and negative clinical tests are confirmed. They support longitudinal detection endpoints, but absence of testing is not a negative result and a negative result is not proof of absence of carriage. Do not label detections as incidence rates without an appropriate denominator or hospital acquisition without supporting timing information.

### Evaluation that fits these data

1. **Audit the data before choosing the endpoint.** Produce governed summaries of coverage, event frequency, missing periods, test numbers, repeat positives and changes in workflow or testing. Choose one sufficiently observed organism/outcome first; do not select it because it produces the strongest association.
2. **Validate movement and infection outcomes separately.** Predict held-out recorded staff locations/activities using only information available at prediction time. This assesses prediction of recorded events, not unobserved contacts. Evaluate the testing-outcome model on a separate time block. Matching outcome counts does not uniquely validate the underlying contact network.
3. **Use temporal evaluation.** Plan an early development/calibration period, an intermediate tuning period and an untouched later evaluation period, subject to event counts. Use rolling-origin checks within development where feasible. Fit preprocessing and parameters within each training window. Avoid random event splits and future-window occupancy features. A single annual cycle does not independently establish a seasonal pattern.
4. **Make complexity earn its place.** Compare a simple organism-outcome time-series baseline, an aggregate model using the same available activity/testing covariates, a room-level contact model and the detailed spatial model. Give baselines comparable data access. Use ablations to separate the contribution of staff events, geometry and model complexity; define predictive scores and interval coverage before evaluation.
5. **Represent missing patient movement honestly.** Compare explicit latent occupancy/turnover scenarios, restricted by any legitimately available aggregates. Evaluate whether plausible alternatives change predictions or intervention rankings. Synthetic recovery experiments can test identifiability, but cannot establish which patient history occurred at UCLH. Do not infer who infected whom from these streams alone.
6. **Separate retrospective explanation from forecasting.** Replaying the actual staff activity of an evaluation week uses information that may not have been available before that week. Label this a conditional retrospective evaluation. A prospective forecast must use only known rosters/events or forecast staff activity and propagate its uncertainty.

Hospital-specific validation against observed outcomes is established precedent, so “a real ward” and “one year” are not sufficient novelty claims. The stronger contribution would be a defensible result about whether staff-resolved spatial modelling adds useful information under this particular observation regime, including a rigorous negative result if it does not. [Scaria et al. (2023)][R09].

### Patient stays inferred from clinical testing: a central identification problem

The investigator confirms that ward-stay intervals are inferred from testing timelines rather than observed admission/discharge records. This is an explicit modelling assumption, not a recovered administrative fact. A specimen collection date with reliable ward attribution supports presence at that observation time; a result-reporting date or requesting-service label may not. Two ward-attributed tests do not establish uninterrupted residence between them, and first/last tests need not coincide with arrival/departure. Patients who never receive a test are absent from a test-derived roster.

Clinical testing is selective. The inference problem therefore has at least three coupled components: patient presence, underlying organism status, and the clinical testing process. Treating a first-to-last-test interval as certain occupancy can make frequently tested patients appear to have greater exposure simply because they have more observations. This is a plausible bias mechanism to investigate, not a measured finding at UCLH. The distinction from prior inference studies that use hospitalization records should be explicit. [Pei et al. (2025)][R16].

**Proposed analysis:** retain first-to-last-test occupancy as a transparent reference assumption, then compare alternative start/end extensions, breaks between tests and turnover scenarios. Do not choose arbitrary day buffers and describe them as validated stays. Use independent operational information or an approved record-review subset to constrain these alternatives if obtainable; otherwise report sensitivity or partial identification. Full-ward patient-days, untested occupancy and hospital acquisition cannot be recovered uniquely from the stated streams alone.

**Prevent information leakage:** a future test used to define a patient's present-day occupancy supplies future information. Retrospective reconstruction may use the full timeline if labelled accordingly. Forecast evaluation must reconstruct presence using information available at each forecast time. Do not use held-out test results to tune occupancy or transmission assumptions before evaluating predictions against those same results. In a joint retrospective model, explicitly model the shared observation process rather than treating reconstructed occupancy as independent ground truth.

A feasible initial endpoint is positivity at clinically obtained specimens, conditional on the observed testing schedule and available history. This evaluates prediction among tested patients, not ward-wide prevalence or the number of future positive tests. Predicting detection counts requires a testing-frequency model as well; predicting acquisition requires further assumptions about presence, importation and latent carriage. These are proposed endpoint choices to assess against the available sample size and organism, not promises of identifiability.

### Revised publication priority

Advance the software paper and the UCLH data/observation specification together. Prioritise Route C as the methods contribution, with Route B supplying controlled uncertainty experiments. Pursue Route H as a separate application only if the outcome information and validation support a distinct scientific claim; otherwise combine the methods and ward evaluation into one stronger paper. Restricted clinical records can support these papers without being placed in the public repository: release code, synthetic analogues and permitted aggregate evidence, and document governed access and reproducibility. No sensitive records were accessed or copied for this revision.

## 8. Publication fit and submission constraints

| Venue / format                                            | What would make this project fit                                                                  | Current decision                                                                                                                                                                                                                           |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **JOSS: research software**                               | A mature, reusable, research-used package with clear scope and design decisions                   | Plausible after readiness work. Current guidance requires more than six months of active public history and demonstrated research use. Do not assume Git timestamps prove when the repository became public. [Official requirements][R32]. |
| **SoftwareX: software and application**                   | A detailed, reproducible account of useful research software and its application                  | Strong alternative for Route A or a genuinely independent converter; do not submit the same software story to several venues. [Publisher description][R34].                                                                                |
| **JORS: software metapaper / research-software practice** | Reuse and quality assurance; or an independently evaluated practice contribution                  | Plausible for software or an evidenced TRE workflow. These are peer-reviewed formats. [Author guidance][R33].                                                                                                                              |
| **Journal of Simulation / JASSS**                         | A well-specified methodological result about model structure, uncertainty or simulation behaviour | Candidate Route B venues, not a default home for arbitrary sweeps. Reporting standards are necessary but insufficient. [STRESS][R26], [ODD][R25].                                                                                          |
| **PLOS Computational Biology**                            | Significant biological or methodological insight, rigorous methods and substantial evidence       | Stretch target for Routes B/C/H, not a feature inventory. Its stated publication criteria are more demanding than “the code works.” [Journal criteria][R36].                                                                               |
| **Scientific Data**                                       | A reusable, well-documented dataset with technical validation                                     | Only after building an actual benchmark resource; a results CSV is not automatically a Data Descriptor. [Official guidance][R35].                                                                                                          |
| **Clinical infection-control journals**                   | A relevant pathogen/intervention question and credible validation                                 | Route H only after a material increase in evidence; see the published CDI modelling/validation examples. [Barker][R08], [Scaria][R09], [Gerada][R13].                                                                                      |

Venue rules were checked on the review date; they may change. Fees, word limits, current indexing and turnaround times are intentionally not estimated here. SoftwareX’s detailed guide was access-restricted during this review; the publisher’s accessible Research Elements description supports the scope assessment, not an assertion that every submission requirement has been checked.

JOSS currently requires disclosure of AI assistance and human review, and restricts AI use in author–editor/reviewer conversations except translation. This AI-assisted planning document is not a substitute for human scholarly judgement or author correspondence. Any eventual submission should follow the venue’s policy then in force. JOSS also explicitly allows related science/methods publications with disclosure; that supports a distinct software-plus-science portfolio, not duplicate manuscripts. [JOSS submission guidance][R32].

## 9. A staged research programme with decision gates

### Gate 1: define and verify the model before collecting more plots

Create an ODD document and a one-page scientific contract: supported agents, task semantics, physical units, time support, stochastic process, scheduling order, spatial constraints and output definitions. Add targeted tests for rejected movement, room/building/floor separation, missing spatial classifications, bounded travel and terminal-interval handling. Decide whether the GPU path is experimental, equivalent or intentionally approximate.

Freeze the running sweep’s code and provenance. Complete and report it honestly as a legacy-model sensitivity exercise. If correctness fixes affect its outcomes, rerun a new version; retain both for a transparent comparison. Do not silently replace inconvenient output or retrofit the hypothesis after seeing a favourable trend.

**Pass condition:** each scientific outcome has a precise definition and the implementation satisfies the claimed invariants, or documented exceptions constrain the permitted use.

### Gate 2: choose one scientific question and an independent reference

For the planned UCLH study, prioritise Route C using the confirmed staff records and geometry, and establish what those observations can independently validate. Use Route B to test assumptions where ground truth is unavailable; organism-specific testing outcomes offer a separate evaluation target, not direct contact ground truth. Agree with clinical collaborators on the endpoint and the minimum effect worth resolving before running an expensive factorial design.

For movement reconstruction, the observation model is essential: an event is evidence of a location or activity at a time, not continuous proof of where a person was between events. Distinguish late documentation, shared workstations, missing badge events, staff role differences and absent off-shift records. A calibrated point estimate that ignores these mechanisms may simply fit their biases.

**Pass condition:** the experiment can distinguish success from a plausible but incorrect reconstruction, and the reference is not merely another output of the same simulator.

### Gate 3: compare meaningful baselines and uncertainty sources

Implement at least a simple room-level or network baseline and a simple movement reconstruction baseline before a complex learned policy. More geometry and more parameters should improve the intended outcome enough to justify their cost. Use held-out time/staff/site splits as appropriate, with nested tuning and a final untouched test set.

For calibration, assess parameter recovery on independent synthetic scenarios, posterior/predictive calibration where applicable, and held-out observed summaries. Modern simulation-based inference tools already exist; calling one is not itself a new statistical contribution. [Tejero-Cantero et al. (2020)][R29].

Separate stochastic replicate variation, schedule/layout variability, parameter uncertainty, observation error and structural choices. Use a pilot to plan replication from precision requirements. Thirty is a design choice, not a universal adequacy threshold. Predefine primary contrasts and distinguish exploratory from confirmatory analyses; do not interpret non-overlapping or overlapping individual confidence intervals as a complete test of a paired difference.

**Pass condition:** conclusions survive relevant uncertainty checks or the paper explicitly establishes their limits.

### Gate 4: produce independently reusable evidence

Provide a tagged release, input/configuration manifests, a small runnable reproduction and a longer archived experiment. Include supported environment/hardware information and a public synthetic analogue when real data are restricted. An access statement must explain how independent assessment is possible without promising unrestricted release of sensitive records.

Have an independent user repeat the main result. Compare their output and document discrepancies. The software paper can then emphasize demonstrated reuse; the methods paper can emphasize the scientific result. ODD, STRESS and FAIR4RS provide complementary reporting and stewardship frameworks, not certifications of truth. [Grimm][R25], [Monks][R26], [Barker][R27].

**Pass condition:** another researcher can reconstruct the claim and its limits, rather than only reproduce an image.

## 10. Likely reviewer objections and the evidence that answers them

| Reviewer objection                                               | A substantive answer                                                                                                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| “Why build this instead of using GAMA or extending Mesa?”        | A precise unmet requirement, a reproducible baseline implementation, and evidence that the new architecture reduces effort or enables a needed analysis |
| “Where is the AMR model?”                                        | A defined resistant-organism mechanism with calibrated/validated endpoints, or a narrower movement/contact manuscript                                   |
| “Why does adding workers increase contacts?”                     | Normalised outcomes, fixed-workload designs and an analysis separating combinatorics from behaviour                                                     |
| “Is the noise physiologically meaningful?”                       | Independently parameterised, unit-consistent movement components and empirical or explicitly exploratory ranges                                         |
| “Are differences caused by illegal movement?”                    | Invariant diagnostics, corrected-model experiments and a transparent comparison with the legacy implementation                                          |
| “Are your 30 replicates independent hospitals?”                  | Explicitly no: report the hierarchy and the conditional scope of the intervals                                                                          |
| “You trained and tested on the same workers or adjacent events.” | Staff/time/site holdouts and a final untouched test set, with features restricted to available information                                              |
| “Can sparse logs identify centimetre-scale encounters?”          | Identifiability experiments, observation-error models and calibrated bounds rather than an unsupported unique reconstruction                            |
| “Is GPU speedup measuring the same model?”                       | Semantic tests, distributional agreement or quantified approximation error, and end-to-end timings                                                      |
| “Is this a digital twin or just a simulation?”                   | Define synchronization, updating, validation and the intended decision loop; omit the digital-twin label if these are absent                            |
| “How can restricted-data results be checked?”                    | Public synthetic reproductions, approved aggregate evidence, governed access and independently repeated computation                                     |
| “What is new beyond the closest published paper?”                | A one-paragraph claim tied to a specific new capability or finding and an experiment that isolates it                                                   |

A sceptical referee would be justified in rejecting a manuscript that substitutes architecture diagrams, many parameters, a dashboard or thousands of runs for these answers. Conversely, resolving one of these problems convincingly could produce a stronger paper than claiming to solve all hospital AMR modelling at once.

## 11. Suggested manuscript framing

### A defensible draft software abstract

Hospital workflow simulations require consistent representations of spatial geometry, time-stamped activities and interaction measurements, while sensitive operational data may remain within restricted research environments. AMR-Hub is an open-source Python framework for task-driven hospital movement and contact-opportunity simulation. It provides structured spatial and task models, synthetic examples, geometry-preparation utilities and contact-analysis tools. This software contribution describes the supported computational contracts, reproducibility workflow and relationship to existing ABM platforms. The present CPU model generates proximity-based contact outcomes; these should not be interpreted as validated estimates of antimicrobial-resistant infection acquisition. Publication should accompany an archived release, reproducible examples and an independently demonstrated research application. **The final sentence and all validation claims must be rewritten around evidence actually completed before submission.**

### A proposed methods-paper abstract structure

**Background:** Sparse routine events do not uniquely determine between-event movement, and different admissible movements may imply different contact networks. **Objective:** quantify how observation sparsity and movement assumptions affect a predefined contact or policy contrast. **Methods:** compare explicit reconstruction models across independent layouts/schedules; censor known trajectories; evaluate against independent observations where available; propagate observation, parameter and structural uncertainty. **Results:** insert measured accuracy, interval coverage, computational cost and robustness results only after analysis. **Conclusion:** state the conditions under which a claim is identifiable, robust or unsupported. Do not pre-write a claim that a more complex model is better.

The central editorial choice is whether AMR-Hub is being presented as a reusable instrument, a new inference method, or evidence about hospital practice. Those can support separate contributions, but the validation burden changes at each step. My recommendation is to **finish a narrowly scoped software contribution while concentrating new scientific work on uncertainty and validation of event-to-contact reconstruction**. Treat the current stochasticity sweep as evidence about the behaviour of one model, not as a shortcut to an AMR intervention paper.

## References

The first 30 entries are peer-reviewed research/methods/software publications or conference proceedings. R31 is explicitly grey literature. R32–R36 are official editorial/publisher guidance, not research evidence. Detailed DOI metadata are retained in [reference-metadata.json](novelty-review/reference-metadata.json).

1. **R01.** Temime L, Opatowski L, Pannet Y, Brun-Buisson C, Boëlle PY, Guillemot D. (2009). _Peripatetic health-care workers as potential superspreaders_. Proceedings of the National Academy of Sciences, 106, 18420–18425. [Paper][R01].
2. **R02.** Hornbeck T, Naylor D, Segre AM, Thomas G, Herman T, Polgreen PM. (2012). _Using sensor networks to study the effect of peripatetic healthcare workers on the spread of hospital-associated infections_. Journal of Infectious Diseases, 206, 1549–1557. [Paper][R02].
3. **R03.** Curtis DE, Hlady CS, Kanade G, Pemmaraju SV, Polgreen PM, Segre AM. (2013). _Healthcare Worker Contact Networks and the Prevention of Hospital-Acquired Infections_. PLOS ONE, 8, e79906. [Paper][R03].
4. **R04.** Vanhems P et al. (2013). _Estimating Potential Infection Transmission Routes in Hospital Wards Using Wearable Proximity Sensors_. PLOS ONE, 8, e73970. [Paper][R04].
5. **R05.** Duval A et al. (2018). _Measuring dynamic social contacts in a rehabilitation hospital: effect of wards, patient and staff characteristics_. Scientific Reports, 8. [Paper][R05].
6. **R06.** Barnes SL, Golden BL, Wasil EA. (2012). _Exploring the effects of network structure and healthcare worker behavior on the transmission of hospital-acquired infections_. IIE Transactions on Healthcare Systems Engineering, 2, 259–273. [Paper][R06].
7. **R07.** Mietchen MS, Short CT, Samore MH, Lofgren ET. (2022). _Examining the impact of ICU population interaction structure on modeled colonization dynamics of Staphylococcus aureus_. PLOS Computational Biology, 18, e1010352. [Paper][R07].
8. **R08.** Barker AK, Alagoz O, Safdar N. (2018; online 2017). _Interventions to Reduce the Incidence of Hospital-Onset Clostridium difficile Infection: An Agent-Based Modeling Approach to Evaluate Clinical Effectiveness in Adult Acute Care Hospitals_. Clinical Infectious Diseases, 66, 1192–1203. [Paper][R08].
9. **R09.** Scaria E, Safdar N, Alagoz O. (2023). _Validating agent-based simulation model of hospital-associated Clostridioides difficile infection using primary hospital data_. PLOS ONE, 18, e0284611. [Paper][R09].
10. **R10.** Caudill L, Lawson B. (2017). _A unified inter-host and in-host model of antibiotic resistance and infection spread in a hospital ward_. Journal of Theoretical Biology, 421, 112–126. [Paper][R10].
11. **R11.** Leclerc QJ, Duval A, Guillemot D, Opatowski L, Temime L. (2024). _Using contact network dynamics to implement efficient interventions against pathogen spread in hospital settings: A modelling study_. PLOS Medicine, 21, e1004433. [Paper][R11].
12. **R12.** Thota RC, Uddin YS, Bani-Yaghoub M, Abourraja MN, Sutkin G, Paschal S. (2025). _Enhancing Agent-Based Models with Real-Time Movement Data to Assess Impacts of Biosecurity Interventions on Disease Exposure in Healthcare Settings_. Proceedings of ACM BCB 2025, 1–10. [Paper][R12].
13. **R13.** Gerada A et al. (2026). _Simulating interventions to prevent gastro-intestinal transmission of Clostridioides difficile and antimicrobial-resistant bacteria in healthcare settings: a model calibration study_. Journal of Hospital Infection. [Paper][R13].
14. **R14.** Madhobi KF et al. (2022). _Use of Contact Networks to Estimate Potential Pathogen Risk Exposure in Hospitals_. JAMA Network Open, 5, e2225508. [Paper][R14].
15. **R15.** Biermann P et al. (2025). _An openEHR based infection control system to support monitoring of nosocomial bacterial clusters and contacts_. npj Digital Medicine, 8, 385. [Paper][R15].
16. **R16.** Pei S, Seeram D, Blumberg S, Shopsin B, Uhlemann AC, Shaman J. (2025). _Inferring asymptomatic carriers of antimicrobial-resistant organisms in hospitals using genomic, microbiological and patient mobility data_. Nature Communications, 16. [Paper][R16].
17. **R17.** Taillandier P et al. (2019; online 2018). _Building, composing and experimenting complex spatial models with the GAMA platform_. GeoInformatica, 23, 299–322. [Paper][R17].
18. **R18.** Curtis S, Best A, Manocha D. (2016). _Menge: A Modular Framework for Simulating Crowd Movement_. Collective Dynamics, 1, 1–40. [Paper][R18].
19. **R19.** ter Hoeven E et al. (2025). _Mesa 3: Agent-based modeling with Python in 2025_. Journal of Open Source Software, 10, 7668. [Paper][R19].
20. **R20.** Richmond P, Chisholm R, Heywood P, Chimeh MK, Leach M. (2023). _FLAME GPU 2: A framework for flexible and performant agent based simulation on GPUs_. Software: Practice and Experience, 53, 1659–1680. [Paper][R20].
21. **R21.** Wu Y et al. (2021; online 2020). _Indoor mapping and modeling by parsing floor plan images_. International Journal of Geographical Information Science, 35, 1205–1231. [Paper][R21].
22. **R22.** Han L, Qiao H, Li Z, Liu M, Zhang P. (2023). _Navigation-Oriented Topological Model Construction Algorithm for Complex Indoor Space_. ISPRS International Journal of Geo-Information, 12, 248. [Paper][R22].
23. **R23.** Williamson EJ et al. (2020). _Factors associated with COVID-19-related death using OpenSAFELY_. Nature, 584, 430–436. [Paper][R23].
24. **R24.** de Montjoye YA, Hidalgo CA, Verleysen M, Blondel VD. (2013). _Unique in the Crowd: The privacy bounds of human mobility_. Scientific Reports, 3, 1376. [Paper][R24].
25. **R25.** Grimm V et al. (2020). _The ODD Protocol for Describing Agent-Based and Other Simulation Models: A Second Update to Improve Clarity, Replication, and Structural Realism_. Journal of Artificial Societies and Social Simulation, 23(2), 7. [Paper][R25].
26. **R26.** Monks T, Currie CSM, Onggo BS, Robinson S, Kunc M, Taylor SJE. (2019; online 2018). _Strengthening the reporting of empirical simulation studies: Introducing the STRESS guidelines_. Journal of Simulation, 13, 55–67. [Paper][R26].
27. **R27.** Barker M et al. (2022). _Introducing the FAIR Principles for research software_. Scientific Data, 9, 622. [Paper][R27].
28. **R28.** Ng AY, Russell S. (2000). _Algorithms for Inverse Reinforcement Learning_. Proceedings of ICML, 663–670. [Author-hosted paper][R28].
29. **R29.** Tejero-Cantero A et al. (2020). _sbi: A toolkit for simulation-based inference_. Journal of Open Source Software, 5, 2505. [Paper][R29].
30. **R30.** Michaelides P, Sarkadi Ş. (2025). _Covid-19 in hospitals: Studying influencing factors through agent-based modelling_. PLOS ONE, 20, e0326350. [Paper][R30].
31. **R31.** Health Data Insight. _Healthcare Associated Infection Simulator_. Project/internship description; **not a peer-reviewed validation paper**. Accessed 29 October 2026. [Project page][R31].
32. **R32.** Journal of Open Source Software. _Submitting a paper to JOSS_. Official requirements and policy; accessed 29 October 2026. [Guidance][R32].
33. **R33.** Journal of Open Research Software. _Submissions / Author Guidelines_. Official format and review guidance; accessed 29 October 2026. [Guidance][R33].
34. **R34.** Elsevier. _Research Elements journals_. Official descriptions of SoftwareX, Software Impacts, MethodsX and Data in Brief; accessed 29 October 2026. [Publisher page][R34].
35. **R35.** Scientific Data. _Submission Guidelines_. Official Data Descriptor and technical-validation guidance; accessed 29 October 2026. [Guidance][R35].
36. **R36.** PLOS Computational Biology. _Journal Information / Criteria for Publication_. Official publication criteria; accessed 29 October 2026. [Guidance][R36].

[R01]: https://doi.org/10.1073/pnas.0900974106
[R02]: https://doi.org/10.1093/infdis/jis542
[R03]: https://doi.org/10.1371/journal.pone.0079906
[R04]: https://doi.org/10.1371/journal.pone.0073970
[R05]: https://doi.org/10.1038/s41598-018-20008-w
[R06]: https://doi.org/10.1080/19488300.2012.736120
[R07]: https://doi.org/10.1371/journal.pcbi.1010352
[R08]: https://doi.org/10.1093/cid/cix962
[R09]: https://doi.org/10.1371/journal.pone.0284611
[R10]: https://doi.org/10.1016/j.jtbi.2017.03.025
[R11]: https://doi.org/10.1371/journal.pmed.1004433
[R12]: https://doi.org/10.1145/3765612.3767222
[R13]: https://doi.org/10.1016/j.jhin.2026.06.007
[R14]: https://doi.org/10.1001/jamanetworkopen.2022.25508
[R15]: https://doi.org/10.1038/s41746-025-01795-9
[R16]: https://doi.org/10.1038/s41467-025-65241-w
[R17]: https://doi.org/10.1007/s10707-018-00339-6
[R18]: https://doi.org/10.17815/CD.2016.1
[R19]: https://doi.org/10.21105/joss.07668
[R20]: https://doi.org/10.1002/spe.3207
[R21]: https://doi.org/10.1080/13658816.2020.1781130
[R22]: https://doi.org/10.3390/ijgi12060248
[R23]: https://doi.org/10.1038/s41586-020-2521-4
[R24]: https://doi.org/10.1038/srep01376
[R25]: https://doi.org/10.18564/jasss.4259
[R26]: https://doi.org/10.1080/17477778.2018.1442155
[R27]: https://doi.org/10.1038/s41597-022-01710-x
[R28]: https://ai.stanford.edu/~ang/papers/icml00-irl.pdf
[R29]: https://doi.org/10.21105/joss.02505
[R30]: https://doi.org/10.1371/journal.pone.0326350
[R31]: https://healthdatainsight.org.uk/project/healthcare-associated-infection-simulator/
[R32]: https://joss.readthedocs.io/en/latest/submitting.html
[R33]: https://openresearchsoftware.metajnl.com/about/submissions
[R34]: https://www.elsevier.com/researcher/author/tools-and-resources/research-elements-journals
[R35]: https://www.nature.com/sdata/submission-guidelines
[R36]: https://journals.plos.org/ploscompbiol/s/journal-information
