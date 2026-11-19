# Task-driven mobility between recorded healthcare events

Literature and design discussion, 14 November 2026.

This is a **separate, targeted review**, not a revision of the
[original novelty review](../amr-hub-novelty-and-publication-review.md) or
the [full-text discussion](./full-text-discussion.md). Its question is how
AMR-Hub could represent healthcare-worker (HCW) activities and movement
that are not recorded in routine data, and whether its partially implemented
needs/“mock BDI” idea is worth developing.

The wider aim is an **open-source, adaptable hospital simulation platform**:
take a hospital floorplan in CAD form, combine its geometry with available
operational movement and patient-interaction records and infection test
results, and use an agent-based model to generate predictions and explore
counterfactuals. The intended scope is use across hospitals and floorplans,
subject to the available inputs and the platform's eventual support for
them. The project context includes EPIC, which the investigator describes as
widely used in UK hospitals, and routinely available infection test results.
The exact data streams, their provenance, accessibility and formats must be
established for each deployment; this review has not verified them.

Movement modelling serves that integrated goal. Records may be incomplete
or patchy: for example, someone may follow a colleague through a door
without generating their own access event. Other activities, such as meals,
toilet visits, rest and informal conversations, may not be recorded at all.
The practical question is how to represent these gaps in a useful and
transparent way, rather than whether each behavioural component is novel.

## 1. Short answer

**Yes: pursue needs-informed, task-driven mobility, but begin with a small,
constrained and testable scheduler rather than a full belief–desire–intention
(BDI) architecture.** A needs-based activity model is a plausible way to
generate candidate meals, toilet visits and rests between recorded work
events. It should produce a _distribution of possible histories_, not claim
to discover which breaks or conversations actually happened.

Existing general human-activity and healthcare models offer useful
starting points. Most notably, Stone et al. [H1] describe
an aged-care model with prioritised tasks, staff bathroom use, staggered
breaks, adaptable floorplans and proximity-based contact generation.
Scaria et al. [H2] include staff cafeteria visits in a hospital-specific ABM.
Brandon and Price [G1] model human activities using competing needs.

In the platform's context, the guiding question is:

> How can a reusable CAD-to-ABM workflow combine available hospital records
> with plausible, explicitly uncertain models of unrecorded movement, so
> that its predictions and counterfactuals remain useful when those
> records are incomplete?

The literature can guide the choice of movement model and help establish
which assumptions matter. Comparisons with simpler alternatives,
independent observations where available, and tests across settings will
help determine how well the integrated workflow works in practice.

## 2. What is observed, inferred and simulated?

An event can constrain a person's possible location or activity at a
particular time without revealing the whole journey, the preceding task, or
what they did between events. Different streams have different observation
processes: a door swipe concerns a door, a workstation event concerns a
terminal, and a clinical event may have timestamp and location uncertainty.
Door-access records can also miss crossings, for example when a person
tailgates. Their semantics and coverage must be checked against the actual
data, not assumed.

Consequently, a long gap does **not** prove the person was idle, took a
break, stayed in the last room or left it. Likewise:

- Hunger, fatigue and toilet urgency are **latent modelling constructs**,
  not measured physiological states unless there are independent observations.
- A simulated restaurant visit or conversation is an **assumed possible
  event**, not evidence that it occurred.
- A pair of simulated agents close together for some time yields a
  **simulated proximity/contact opportunity**. It is not a direct observation
  of physical touch, a conversation, exposure, or transmission. Depending
  on the pathogen, surfaces, hand hygiene and room air may matter too.
- Infection test results can inform and evaluate the wider model, but a
  recorded result is not necessarily the time or place of acquisition.
  Testing practices and unobserved infections affect what those results show.

Two different uses need separate modes:

1. **Retrospective reconstruction:** condition feasible histories on the
   observed records, their timing/location uncertainty and observation
   mechanism. Holding trustworthy observed anchors fixed is a modelling
   choice; noisy or incompatible observations may instead need explicit
   tolerances. The model must report conflicts rather than silently forcing
   an impossible journey.
2. **Counterfactual intervention:** a change to layout, staffing or tasks may
   change later observed events themselves. Replaying all original future
   events as immutable can suppress the effect being studied. Specify what is
   held fixed, what is allowed to change, and why.

Sparse events generally do not identify a unique path or activity sequence.
An ensemble can quantify uncertainty _conditional on the model and its
parameters_; it cannot by itself prove that the correct behaviour has been
reconstructed.

## 3. What relevant healthcare models already do

| Study                                                          | Activity or movement mechanism                                                                                                                                                                                                                                                                                              | Evidence and limitations for this question                                                                                                                                                                                                                                                                                                                       |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Stone et al. 2026 [H1]**, aged care                          | Staff and resident tasks are generated by time, condition or messages, prioritised in queues, and executed via statecharts and pedestrian movement. Staff self-hygiene includes bathroom use; breaks are staggered. Resident social activities include preferences and friends. Spatial layout is separated from behaviour. | Closest direct behavioural comparator. A 21-question worker survey informed task parameters; a synthetic single-storey facility is used. Resident social functions should not be mistaken for a validated model of informal _staff_ conversations. No automated CAD ingestion or routine-event-conditioned gap reconstruction is described in the cited methods. |
| **Scaria et al. 2023 [H2]**, acute hospital CDI                | The hospital-specific ABM includes a cafeteria that staff may visit once per shift when not interacting with patients, and ward common rooms. Nurses and doctors differ in their use of wards.                                                                                                                              | An example of modelling staff movement to shared spaces. Primary hospital data and literature informed the hospital model; comparing infection trends and a network proxy is not direct validation of individual cafeteria visits or trajectories.                                                                                                               |
| **Michaelides and Sarkadi 2025 [H3; R30]**, synthetic hospital | Staff, patients and visitors move in a grid hospital containing a cafe and staff kitchen; decisions, movements and room durations are probabilistic.                                                                                                                                                                        | Shows a configurable multi-room hospital and stochastic behaviour; the main paper does not establish empirical validation of individual HCW activities. Existence of a cafe alone does not establish the frequency or mechanism of staff cafe visits.                                                                                                            |
| **Milazzo et al. 2011 [H4]**, hospital ward                    | Worker shifts and movement during ward rounds drive patient–worker encounters in a stochastic MRSA model.                                                                                                                                                                                                                   | Uses ward data including admissions and staff shifts; much simpler care-round representation than a full discretionary-activity model. The paper calibrates transmission using prevalence and evaluates other periods; disease fit is not proof of correct movement.                                                                                             |
| **Duval et al. 2024 [H5]**, long-term care                     | Samples temporal proximity contacts by hour, staff category and ward, favours recurrent pairs, and includes an observation model for missing records.                                                                                                                                                                       | A serious **non-spatial network baseline** for contact questions, not a reconstruction of actual walking paths or personal motives. It uses dedicated proximity observations to estimate parameters and compares generated networks with those data; this is not independent proof of the unobserved contacts.                                                   |
| **R03 [H6]**, hospital                                         | EMR computer-session events and a blueprint-derived room graph are used to estimate contacts through temporal proximity and graph distance.                                                                                                                                                                                 | Routine-event comparator, but computer logins are not door-entry records or observed conversations. Its preliminary sensor comparison uses sensor-derived synthetic logins rather than simultaneous actual logins. See the [earlier discussion](./full-text-discussion.md).                                                                                      |

**Implication.** [H1] is a particularly useful source of design ideas for
AMR-Hub: its task queues, bathroom and break activities, and separation of
behaviour from layout offer concrete examples to consider when filling gaps
between hospital records. Its aged-care setting differs from an acute
hospital, so rules and parameters need to be adapted rather than copied
unchanged. Neither [H1] nor [H2] establishes that their particular
unobserved staff breaks occurred as simulated. [H1] reports no direct
sensor-based contact validation and is internally inconsistent about
replication: its methods describe 100 replicates, while its limitations
also refer to a single run. Its quantitative results therefore warrant
caution.

## 4. General approaches and what they offer

| Approach                              | How the missing period is filled                                                                                                        | Strength                                                                                               | Main limitation                                                                                                               |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| **No extra activity / direct travel** | Wait or travel between known tasks under a stated route and timing rule.                                                                | Transparent minimum baseline; few assumptions.                                                         | May miss shared-space visits and underestimate mixing; even waiting location is an assumption.                                |
| **Fixed schedule / activity diary**   | Sample or replay role- and shift-specific activities, times, destinations and durations.                                                | Interpretable and calibratable from diaries.                                                           | A fixed timetable may fit poorly around interrupted or irregular care work; diary coverage and recall matter.                 |
| **Stochastic state and dwell model**  | Transition between work, break, transit, etc.; sample dwell times, perhaps conditional on time, role and history.                       | Flexible baseline for irregular timing; a semi-Markov model permits non-geometric dwell distributions. | Needs suitable data; unconstrained sampling can violate recorded events and staffing requirements.                            |
| **Needs-driven rules**                | Accumulate needs; an eligible agent selects a feasible activity when sufficiently urgent; completion reduces the need. [G1]             | Mechanistic, understandable and close to current state variables.                                      | Thresholds and rates are not automatically identifiable; simple needs are not measured psychology.                            |
| **Utility-based scheduling**          | Score eligible activities by urgency, time, travel, preference and disruption, then choose deterministically or probabilistically. [G2] | Makes trade-offs and location choice explicit.                                                         | Weights can be arbitrary or unidentifiable without data; do not score away hard safety constraints.                           |
| **Joint/social activity model**       | Coordinate two or more available agents, with shared place/time and explicit social participation rules.                                | Can represent planned meetings or informal shared breaks, not merely independent trips.                | Partner preferences, mutual availability and interaction durations require evidence; co-location alone is not a conversation. |
| **Full BDI / planning**               | Maintain beliefs, desires and intentions, select plans and reconsider them when perceptions or commitments change. [G3]                 | Useful for explicit knowledge, commitments, interruptions and adaptation.                              | More assumptions, states and validation burden; BDI terminology does not make behaviour empirically correct.                  |
| **Direct network generation**         | Generate contacts from observed or estimated contact statistics rather than positions. [H5]                                             | Efficient comparator when the outcome is a contact network.                                            | Does not provide geometric routes or detailed room-use counterfactuals.                                                       |

[G1] is an especially useful precedent for the proposed “mock BDI”: its
agents have time-varying satisfaction, thresholds and urgency, and select
actions to address needs. It calibrates on longitudinal time-use data and
evaluates against separate single-day data. It is **general-population
activity modelling, not HCW validation**. [G2], assessed from its public
abstract, schedules flexible urban activities within free windows using
survey-derived start/duration distributions and utility. Its transport
context does not determine the correct hospital rules. [G3] is platform
documentation illustrating BDI concepts, not evidence that BDI improves
hospital mobility prediction.

Recent LLM-based desire-driven work [G4] also proposes activities from
needs, including social needs, but evaluates text-based activities for
plausibility rather than physical HCW trajectories or hospital contacts.
It is a conceptual comparison, not a reason to introduce an LLM into a TRE
simulation.

## 5. What AMR-Hub currently has

This is a focused inspection of revision `26e1370`, not a full software
audit or a verification of clinical datasets.

- [`InternalState`](../../python-code/src/amr_hub_abm/agent/internal_state.py)
  stores normalised hunger and toilet need, and HCW fatigue; updates are
  configurable per timestep and capped, with default rates of zero.
  Reset helpers exist for future task integration. The values currently
  **do not themselves generate activities**.
- [`Simulation.step`](../../python-code/src/amr_hub_abm/simulation.py)
  updates internal state when configured, then runs the task state machine.
- [`Task`](../../python-code/src/amr_hub_abm/task/task.py) represents
  progress, timing, location and priority; task subclasses provide
  resource/lifecycle behaviour. The dispatcher in
  [`tasklist.py`](../../python-code/src/amr_hub_abm/task/tasklist.py)
  handles in-progress, moving, suspended and not-started tasks in that
  order; within a progress category it selects by `(time_due, priority.value)`.
  This should not be described as a general urgency-based BDI deliberator.
- [`Agent.attempt_task_insertion`](../../python-code/src/amr_hub_abm/agent/agent.py)
  may insert an occupation task for the first available chair in the current
  room when there is time before the next task. It does not choose meals,
  toilets or social visits based on needs. Its current check considers travel
  to the chair before the next move time; it does **not** establish the full
  activity-plus-return feasibility condition proposed below.
- [`parse_location_timeseries`](../../python-code/src/amr_hub_abm/simulation_factory.py)
  maps supported `attend_patient`, `door_access`, `workstation` and
  `occupy_content` records to tasks; the builders set the task's `time_due`
  from the event timestamp, and durations are configured separately. Whether
  a source timestamp denotes start, end or some other event therefore needs
  explicit reconciliation before treating it as an exact anchor.

Within the inspected source paths and searches, there is no implemented
belief-update/desire-selection/intention-reconsideration loop or linkage
from need satisfaction to task completion. Task progress and internal needs
are useful **building blocks**, but are not yet a full BDI architecture or
an implemented needs-driven scheduler. Supported fixture event types should
not be taken as independent evidence of the contents or quality of the
restricted hospital data, nor as proof of implemented roster ingestion.

## 6. A practical model to try first

### 6.1 Define activities separately from recorded obligations

Represent mandatory observed or operational care commitments separately
from **generated, uncertain** discretionary activities. A first version
could consider:

- **Meal:** start-time window and duration; eligible staff kitchen, cafe,
  ward space or off-model option if appropriate.
- **Toilet:** need or time-since-last-use, accessible toilet and duration;
  do not infer sensitive personal histories as facts.
- **Rest:** a break space or chair and duration; a break need not mean eating.
- **Social encounter:** initially count incidental simulated co-location
  separately from an optional, explicitly modelled joint activity. Do not
  label every shared-room encounter as a conversation.

Record whether each event is observed, inferred from a specific rule or
sampled; attach assumptions and parameter provenance. Sample durations and
preferences rather than using a single value for everyone where the data
support it. Distinguish variability between workers from day-to-day
variability within a worker. Initial needs and activities before the first
event and after the last event also require explicit assumptions.

### 6.2 Check the whole gap, not just the trip out

For an illustrative reconstruction, suppose an agent is available at place
`A` at 10:00 and must be at anchor `B` at 10:40. A candidate break at `C`
requires five minutes to reach `C`, twelve minutes there, and seven minutes
from `C` to `B`. With a four-minute uncertainty/dispatch buffer, the total
is 28 minutes, so it fits the 40-minute gap under those travel assumptions.

In general, require:

```text
travel(A, C) + activity_duration(C) + travel(C, B) + buffer
    <= available_gap(A, B)
```

For multiple activities, include all intermediate legs, durations and
constraints. Use feasible accessible routes and account for doors, floor
connectivity, congestion, capacity and timing uncertainty as appropriate.
An estimate that is systematically too optimistic is not a guarantee of
arrival. An event timestamp may constrain a task start, end, interval or
door crossing; derive the actual available gap from the **source semantics**,
not the example alone. Reserve sufficient staff coverage and necessary
resources; preserve mandatory care and any applicable break protections.
Allow an explicit **no discretionary activity** option.

If even the direct journey is infeasible, report the conflict, its source
and affected observations. Do not manufacture a feasible history by
silently skipping a clinical event or accelerating beyond allowed limits.
Some observed records may themselves be noisy; resolve that through a
declared observation-error policy, not hidden repair.

### 6.3 Choose and execute with explicit rules

For each agent and opportunity, update needs, generate candidates supported
by the environment and role, filter by hard constraints, and score or sample
among feasible candidates using a small number of documented factors:
urgency, time-of-shift, travel cost, expected relief and scheduling
disruption. A fixed schedule, an empirically parameterised stochastic rule,
and a simple needs threshold are alternatives—not evidence that one is best.

An activity should reduce the relevant need only when it actually completes,
according to the selected model; define interruption, partial completion,
waiting for a resource, and failed or abandoned plans. Re-evaluate the
remaining schedule when conditions change. Avoid perpetual starvation of
breaks and do not assume everyone responds identically. A two-person social
activity requires both agents to agree, remain available and fit their
respective commitments; individual random visits alone only yield possible
co-location.

## 7. Is full BDI worth pursuing?

**Recommendation: pursue the modelling idea, starting simply and keeping
full BDI as an option for later.**

The current state variables map naturally to _needs_ and the task list to
_commitments_, but those labels do not imply a true BDI model. Full BDI
typically requires, at minimum, a representation of what an agent believes,
possible desires, a selected persistent intention, plans for it, perception
updates and an intention-reconsideration policy [G3]. It can be worthwhile
if a concrete question requires, for example:

1. Different agents have incomplete or stale information about room
   availability or colleagues.
2. Intentions persist despite minor changes, but a clinical interruption
   can suspend or replace them.
3. Staff coordinate a joint activity or task using information available
   to them rather than an omniscient scheduler.
4. An intervention changes norms, knowledge or choices, not just geometry.

These are **potential research requirements**, not established properties
of the available data. If simple state-based rules reproduce the relevant
held-out activity and contact statistics as well as BDI, they may be the
more practical choice for the platform. If BDI is tried, compare it against
the same constraints, data, seeds where feasible, and compute budget. Report
added parameters, runtime, uncertainty and measurable benefits; do not claim
psychological realism from architecture alone.

## 8. Evaluation and decision gates

### Baselines

At minimum compare: **B0** direct travel/waiting without generated activities;
**B1** scheduled or time/role-conditioned stochastic breaks; **B2**
needs-driven rules; and optionally **B3** richer BDI only when motivated.
Where measured contact-network parameters exist, include an [H5]-inspired
network comparator for common network outcomes. Match data, roster,
geometry, contact definitions and clinical constraints as far as the
comparison allows. Separate the effect of adding activities from the effect
of changing the route, contact definition or transmission model.

### Evidence and validation

1. **Input/observation audit:** document each stream's event meaning,
   sampling, omissions, clock alignment, room mapping and known access
   limitations. Treat gaps as missing information, not evidence of absence.
2. **Verification:** synthetic scenarios with known geometry and schedules;
   test infeasible anchors, overlapping tasks, no available destination,
   resource capacity, interrupted breaks, both staff in a joint activity,
   end-of-shift and reproducibility. Check the same semantics on CPU and GPU
   paths if both are claimed to support the new behaviour.
3. **Independent mobility data where feasible:** a small, consented,
   governance-approved time-and-motion study, diary or suitable proximity /
   location sample can measure break timing, duration, destination and
   staff co-location. Split by day, worker or ward to avoid leakage; report
   limitations and whether the same people informed both calibration and
   validation. Do not send sensitive records outside the TRE.
4. **Masked-event tests:** remove selected events and evaluate predictions
   against them, stratified by event type and gap duration. This evaluates
   held-out _recorded_ events, not unseen toilets or conversations. Model
   non-random recording; a data split alone does not validate missingness.
5. **Compare distributions, not just a single path:** room occupancy and
   dwell, travel/arrival errors, task delay and missed-care rates, activity
   timing, staff–staff and staff–patient proximity duration, and network
   patterns. Match the observation device's spatial/time thresholds and
   missingness when comparing simulated contacts to measured ones. Report
   uncertainty and the predictive coverage of held-out observations.
6. **Decision robustness:** vary activity rates, need parameters, room
   choice, staffing coverage, travel and missingness assumptions. Compare
   intervention rankings and effect sizes across baselines as well as
   stochastic replicates. Distinguish parameter, structural and stochastic
   uncertainty; narrow Monte Carlo intervals alone do not quantify all three.

Synthetic recovery verifies that a method can recover patterns generated
under stated assumptions; it does not establish real-world recovery.
Agreement with infection incidence is useful but cannot independently
validate mobility, because different movement and transmission assumptions
can yield similar incidence [H2].

### Suggested stages

1. **Specify** event semantics, clinical constraints and the intended
   intervention question with clinical/operational partners.
2. **Establish B0/B1** and a minimal activity catalogue; record provenance,
   feasibility failures and outputs.
3. **Add B2** for one or two needs, with configurable parameters, consistent
   timestep units and completion-linked relief. Keep it optional so the
   baseline remains reproducible.
4. **Calibrate and compare** using independent observations where available,
   otherwise clearly labelled scenarios and sensitivity bounds.
5. **Only then consider B3:** identify a failure of simpler rules that
   explicit beliefs, commitment or coordination can address, define its
   evaluation beforehand, and adopt it only if the gain matters.

If new observations cannot be obtained, the method remains useful for
**scenario exploration** but claims about recovered individual behaviour,
calibrated probabilities or superior real-world fidelity must remain limited.

## 9. Sources and search limits

Searches used public OpenAlex keyword queries for hospital staff workflows,
breaks, task scheduling, human needs and BDI; the cited primary texts or
public abstracts were checked on 14 November 2026. This is a targeted
exploratory review, **not a systematic search**: no exhaustive database
strategy, formal screening, risk-of-bias assessment or completeness claim
is implied. Earlier PDF reading and its limitations are documented in the
[full-text discussion](./full-text-discussion.md). Supporting appendices
were not systematically reviewed. No restricted clinical data were inspected.

### Healthcare

- **[H1]** Stone et al. (2026), _Generating a Contact Matrix for Aged Care
  Settings in Australia: An Agent-Based Model Study_.
  [Full text and DOI](https://doi.org/10.18564/jasss.5993).
  Methods: parameterisation, activity scheduling, staff task priorities
  and contact definition.
- **[H2]** Scaria, Safdar and Alagoz (2023), _Validating agent-based
  simulation model of hospital-associated Clostridioides difficile
  infection using primary hospital data_.
  [Full text and DOI](https://doi.org/10.1371/journal.pone.0284611).
  Methods: adaptation to target hospital, cafeteria and validation.
- **[H3; R30]** Michaelides and Sarkadi (2025), _Covid-19 in hospitals:
  Studying influencing factors through agent-based modelling_.
  [Full text and DOI](https://doi.org/10.1371/journal.pone.0326350).
  Methods: hospital setting, simulation and model verification.
- **[H4]** Milazzo et al. (2011), _Modelling of Healthcare Associated
  Infections: A study on the dynamics of pathogen transmission by using an
  individual-based approach_. [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC7114833/);
  [DOI](https://doi.org/10.1016/j.cmpb.2011.02.002).
- **[H5]** Duval et al. (2024), _An algorithm to build synthetic temporal
  contact networks based on close-proximity interactions data_.
  [Full text and DOI](https://doi.org/10.1371/journal.pcbi.1012227).
- **[H6; R03]** See [R03 in the original review](../amr-hub-novelty-and-publication-review.md)
  and the [full-text discussion](./full-text-discussion.md) for its full
  citation and appraisal.

### General activity and decision models

- **[G1]** Brandon and Price (2019), _Calibrating an agent-based model of
  longitudinal human activity patterns using the Consolidated Human
  Activity Database_. [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC10436654/);
  [DOI](https://doi.org/10.1038/s41370-019-0156-z).
- **[G2]** Ordóñez, _Scheduling weekly flexible activities in a large-scale
  multi-agent mobility simulator_ (2017).
  [Record and DOI](https://doi.org/10.3929/ethz-b-000206133).
  Public abstract assessed; full text was inaccessible during this search.
- **[G3]** GAMA Platform, [BDI agents tutorial](https://gama-platform.org/wiki/1.9.1/BDIAgents_step2).
  Framework documentation, version 1.9.1; illustrative, not HCW evidence.
- **[G4]** Wang et al., _Simulating Human-like Daily Activities with
  Desire-driven Autonomy_ (2024 preprint).
  [Preprint](https://doi.org/10.48550/arxiv.2412.06435).
