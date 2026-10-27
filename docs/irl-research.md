# Inverse reinforcement learning for hospital staff movement in AMR-HUB

## Summary

- Inverse reinforcement learning (IRL) infers a reward under which observed behaviour looks close to optimal. For AMR-HUB this would be a reward over rooms on the floorplan graph, giving a stochastic staff movement policy to roll out in the agent-based model (ABM).
- I searched around and found no published IRL or imitation-learning study of hospital staff movement. Hospital transmission models replay sensor contacts, build contact networks from sensors or electronic medical record (EMR) logins, or use rule-based staff profiles.
- In mobility research, IRL gains over simple baselines are modest. A first-order Markov chain matched or beat IRL and adversarial imitation on simple, well-sampled route data [1]. The main argument for IRL is transfer to new layouts or policies, and a 2026 review (preprint) finds that evidence weak [2].
- Our data are offline, partially observed and irregularly timed. Our first build should be an empirical semi-Markov kernel (next room plus dwell time), conditioned on role, unit and time. If IRL is tried, it should be a tabular or linear-feature maximum causal entropy (MCE) model, estimated as a logit dynamic discrete choice (DDC) model on the room graph, with a hidden-room layer and a separate dwell model. GAIL and AIRL need simulator rollouts and do not suit our data.
- Recommendation: IRL is not recommended for this data at this stage-or at least to my knowledge. For next activity class, local history already explains almost all of the structure we can measure (88.6% top-1 with current and previous class, 88.7% with time, role and unit added); the spatial data is too incomplete for location rewards to be identified; and two roster units are not enough to test transfer. Next-room results are not yet recorded, so this is a judgement on the data we have.
- The proposed route is an empirical semi-Markov model first, then forward RL with a specified (not learned) reward, once the agent state includes room, current and next task, time of shift, role and nearby task demand. Staff agents would be trained in the ABM with actor–critic PPO, trained centrally and run per agent: one shared policy per role first (IPPO), then a centralised critic (MAPPO) if coordination matters, through a PettingZoo wrapper, and checked against held-out logs.
- IRL can be revisited if door direction is resolved, workstation mapping improves and data from more than one layout are available.

## Background

### Why a reward function

In the AMR-HUB model, staff agents move between rooms and carry out tasks, and
that movement produces contacts and infection outcomes. The model is built from
three kinds of input: floorplans for the space, routinely collected data for
checkpoints and agent parameters, and infection data for infection parameters.

The idea behind IRL was to close the loop between the model and the
observations. Instead of replaying recorded movement, or sampling from a
transition table fitted to it, each staff agent would act on a reward function:
a score for what it is trying to achieve, such as reaching patients, finishing
tasks and not walking further than needed. IRL would recover that reward from
the observed trajectories, and the agents' behaviour would follow from it.

The reason this matters is counterfactuals. A replay or a fitted transition
table only reproduces behaviour under the conditions we observed. A reward can,
in principle, be carried into situations we never observed, such as a new ward
layout, different staffing, isolation rules or infection-aware behaviour, and
the agents re-plan around the change. That is what would make it useful for
testing interventions in the simulation.

Whether this works depends on two things this work set out to check: whether
the data contain enough structure to learn from, and whether a reward can be
identified from the data we have. The rest of this document covers both, and
why I recommend a simpler route first.

### IRL in brief

IRL can be framed as recovering a reward from behaviour and dynamics (Ng and Russell), but the problem is ill-posed: many rewards fit the same behaviour, including a zero reward under which every policy is optimal [3]. There are several tie-breakers for this; for example, Abbeel and Ng assume a reward linear in known features and match the expert's expected feature counts [4]. Maximum entropy (MaxEnt) IRL picks, among distributions that match those counts, the one with most entropy, so P(trajectory) ∝ exp(reward) and noisy, suboptimal behaviour keeps non-zero likelihood [5]. Maximum causal entropy extends this to stochastic dynamics and yields a softmax ("soft Bellman") policy [6]. Both classical algorithms need a known transition model and solve a soft value iteration in the inner loop.

Even with infinite data, MaxEnt-type models identify the reward only up to potential-based shaping and a constant. Recovery up to a constant needs demonstrations under sufficiently different dynamics or discount factors [7]. Skalse et al. argue that the useful question is whether the remaining ambiguity matters for the downstream task [8]. For us, recovery matters because the model would be used to predict behaviour under a changed layout.

### Project context

The AMR-HUB data (inside TRE, as reconstructed) describes offline electronic event logs from staff in two roster units. These are turned into rostered shift sequences of three activity classes:

- Flowsheet events, which map to rooms directly.
- Workstation events, which map to rooms only through an inferred crosswalk (13 of 36 workstations mapped).
- Door messages, which give a door point but not the direction of travel.

Many events have no room. On a whole-shift 80/20 split, count-based models predict the next activity class (top-1) at about 76% with the majority class, 88.6% with current plus previous class, and 88.7% with full context (time bucket, role, roster unit). So at class level the predictable structure is almost entirely low-order Markov. The ABM, however, needs room-to-room movement with dwell times, and neither next-room-change learnability nor timing has been measured; rollouts generate class sequences only.

## Methods

| Method                                     | Needs                                   | Simulator or known model?            | Output                                 | Fit for our data                                               |
| ------------------------------------------ | --------------------------------------- | ------------------------------------ | -------------------------------------- | -------------------------------------------------------------- |
| Empirical (semi-)Markov kernel             | Transition and dwell counts             | No                                   | Transition matrix, dwell distributions | Strong baseline; tied to observed rooms, so no layout transfer |
| Behaviour cloning / conditional logit      | (state, action) pairs                   | No                                   | Policy                                 | Baseline; errors compound in long rollouts                     |
| Tabular or linear-feature MaxEnt / MCE IRL | Trajectories plus transition model      | Known model (floorplan graph serves) | Reward and soft policy                 | Best fit if IRL is used                                        |
| Logit DDC (NFXP, CCP)                      | As above                                | Estimated or known model             | Same as MCE, with standard errors      | Same model, econometric estimation route                       |
| GAIL, AIRL                                 | Expert data plus on-policy rollouts     | Yes                                  | Policy (GAIL); reward (AIRL)           | Poor: no simulator independent of the ABM                      |
| Offline deep IRL (IQ-Learn, CLARE-type)    | Expert transitions; learned world model | No                                   | Implicit or conservative reward        | Unnecessary for a small graph; overfitting risk                |

### DDC and MaxEnt IRL are the same model

Econometrics has estimated these models since Rust's nested fixed point (NFXP) estimator [9]. A 2026 survey (preprint) shows that soft-Q IRL and logit DDC with extreme-value shocks give the same softmax choice probabilities and smooth Bellman equations [10]. Tran, Bui and Mai add that the mathematical link does not make reward, utility and policy behaviourally interchangeable [2]. In practice the equivalence gives us:

- maximum-likelihood estimation with standard errors on a small tabular state space, with no simulator, because the soft Bellman equation is solved exactly on the room graph;
- conditional choice probability (CCP) methods that avoid repeated inner solves, and a single-loop estimator with finite-time guarantees [11];
- semiparametric inference for policy-value differences, useful for confidence intervals on counterfactual comparisons [12] (preprint).

The `imitation` library's MCE IRL is explicitly tabular. It requires a fully specified transition and observation model, a finite horizon and one-hot states or occupancy measures [13]. Our floorplan graph can supply that model.

### Why not behaviour cloning or adversarial methods

Behaviour cloning is fully offline but suffers covariate shift: small errors take rollouts into unvisited states. DAgger fixes this but needs an expert who can be queried online [14], which retrospective logs cannot provide. GAIL learns a policy by matching occupancy measures and needs environment rollouts [15]. AIRL recovers a reward, but its "disentangled" (transferable) reward holds only for state-only rewards under a decomposability condition on the dynamics, and its training loop also collects rollouts [16]. Using the AMR-HUB ABM as the environment would be circular unless its dynamics were validated independently. IQ-Learn has an offline mode [17], but its reward is implicit and a neural reward is likely to overfit our data volume.

Lazzati et al. argue that offline IRL should require the expert to be optimal only on the states the data reach [18]. Logs therefore say nothing about rewards in situations staff never encountered, such as a new isolation layout.

## Relevant applications

### Human mobility and pedestrians - first literature I found

- MaxEnt IRL was first applied to Pittsburgh taxi routes, with road segments as states and a reward linear in 22 road and turn features. It beat an action-level (locally normalised) model on path matching (78.79% vs 77.30%) and log-probability (−6.85 vs −7.91) [5]. The authors attribute the action-level model's loss to "label bias", which also affects next-step models of room movement.
- Pedestrian prediction [19] and video activity forecasting [20] learned cost functions over environmental features. Both claim transfer to changed or new environments; in what we retrieved, these claims are qualitative or abstract-level.
- TrajGAIL compared a Markov chain, an LSTM, two MaxEnt IRL variants and GAIL on route-distribution Jensen–Shannon distance (JSD) [1]. On real Seoul taxi data GAIL was best (0.4230 vs 0.4701 for the Markov chain; 0.7098 for state-visitation MaxEnt). On single-origin simulated data the Markov chain was best (0.0038 vs 0.0311). BLEU-type sequence scores exceeded 0.99 for most models and did not separate them.
- Zhao and Liang's route-choice AIRL beat logit models and generalised to unseen destinations with only 100 training trips. Behaviour cloning needed about 10,000 trips to come close [21].
- CAMP-IRL extracted several reward profiles to drive agents in a crowd simulator [22], an analogue for role-specific staff rewards.
- Tran, Bui and Mai (preprint) find the strongest transport evidence for context-dependent rewards and inference from incomplete trajectories. They find it weaker for interventions and cross-network transfer, and note that activity durations need a semi-Markov formulation [2].

### Healthcare

Clinical IRL concerns treatment decisions in intensive care, not movement. Examples are ventilation and sedation [23], scalable offline Bayesian IRL (AVRIL) [24] and interpretable policy learning under partial observability (Interpole) [25]. All are offline by necessity and present themselves as tools to explain behaviour rather than to generate it.

Hospital transmission models use simpler movement:

- Temime et al. used rule-based "assigned" and "peripatetic" staff profiles. Hand-hygiene non-compliance by a single peripatetic worker produced outbreaks comparable to widespread non-compliance [26].
- Hornbeck et al. replayed sensor-recorded contacts in an ICU. Day shifts averaged 80.1 contacts per worker per 12 h, and non-compliance by the most-connected worker caused the most infections [27].
- Vanhems et al. found 6 workers accounted for 42% of contacts involving a patient on a geriatric ward [28]. Duval et al. linked close-proximity contacts to ESBL-K. pneumoniae but not ESBL-E. coli acquisition [29].
- Curtis et al. built contact networks from 19.8 million EMR logins and a room-adjacency graph from architectural drawings. These predicted sensor-measured proximity networks, a result the authors call preliminary [30]. This is the closest precedent to our setting.

The consistent lesson is that heterogeneity in mobility between individual workers drives transmission. A movement model that reproduces only average behaviour, as one shared reward would, is likely to understate super-spreading.

## Issues for our data, bottlenecks on further processing in TRE and recommendations as envisioned

### Partial observability

Our case is closer to IRL under occlusion, where the learner sees only part of the trajectory [31], than to POMDP-IRL, where the expert acts under uncertainty [32]. A practical design, which no paper implements in this exact form, is a hidden-room hidden Markov model (HMM) with event-specific emissions:

- a flowsheet or mapped workstation event emits a known room;
- a door message emits "one of the two rooms adjacent to door d", so direction is resolved by neighbouring latent states;
- an unmapped event is uninformative about location, or weakly informative through workstation identity.

The choice model is then fitted inside expectation–maximisation (EM), using forward–backward posteriors as soft counts. Arcidiacono and Miller's CCP-EM framework supports Markov-evolving unobserved states [33]. Baselines and IRL must be scored on the likelihood of the observed event sequence, marginalising hidden rooms, so they are compared on the same data.

### Irregular timing

The one semi-Markov IRL application we found ignores durations during reward learning. We suggest factorising:

- a choice model (kernel or DDC/IRL) for which room comes next;
- a separate dwell hazard conditioned on role, unit, room type, activity class and time of shift.

A fixed tick with a "stay" action is simpler but implies geometric dwell times unless elapsed dwell enters the state. Explicit-duration HSMM software exists (`hsmmlearn` [34], `pyhsmm` [35]). The factorised design maps onto the ABM's `Task` duration plus next-task choice.

### Offline data and confounding

Movement given the floorplan is close to deterministic, so the transition model is not the main gap. The drivers of movement (patient events, call bells, task arrivals) are not logged, so a reward over locations alone may absorb them and be poorly identified.

### Heterogeneity

Start with observed heterogeneity: reward or kernel parameters interacted with role and roster unit, with staff-level random effects on the shift panel. Add latent classes (EM mixture IRL [36], latent-type CCP [33]) only if held-out likelihood improves. With two roster units, unit-level inference will be limited.

### Identifiability and transfer

Tabular per-room rewards cannot be moved to a new floorplan. Transfer needs feature-based rewards on attributes that exist in any layout. Data from several layouts help identification [7]. If our two units have different layouts, they are an asset; if not, transfer claims rest on assumption.

## Evaluation

Evaluation should be offline, split at the level of whole shifts, staff and units, and always include simple baselines.

- **Splits:** whole-shift 80/20 (as now), held-out staff, and leave-one-roster-unit-out.
- **Baselines:** majority class; first- and second-order Markov kernels by role × unit × time bucket with back-off; semi-Markov with empirical dwell; conditional logit or behaviour cloning.
- **Predictive:** held-out log-likelihood and perplexity of the observed event sequence (hidden rooms marginalised), plus top-k accuracy for next room change.
- **Generative:** roll out full shifts and compare with held-out data by JSD on dwell-time distributions, visits per room per shift, transition matrices, door-event rates and rooms visited per shift. Do not rely on BLEU-type metrics, which saturate [1].
- **Infection-relevant:** per-worker distributions of patient-room visits and co-location with other workers, and the share of contacts held by the most mobile workers. Compare against the logs; use published figures [27, 28] only as plausibility checks.
- **Transfer:** leave-one-unit-out. This is where IRL or RL must beat the kernel to justify itself.
- **Synthetic recovery:** generate logs from the ABM with a known reward, apply our observation process (drop rooms, strip door direction, irregular timestamps), and check reward recovery with EPIC [37] and policy recovery with likelihood.
- **Reporting:** standard errors from DDC estimation, repeated seeds and a fixed tuning budget for every model [2].

Decision rule: if IRL does not beat a second-order kernel on held-out likelihood within a layout, it is justified only by transfer, and that must be shown on held-out units or synthetic layouts.

## Recommendations based on literature

IRL is not recommended at this stage, for four reasons:

1. For next activity class, low-order history explains almost all the measurable structure: top-1 is about 76% for the majority class, 88.6% with current and previous class, and 88.7% with time, role and unit added. The context an IRL reward would weight adds about 0.1 points. This is a result for activity class; next-room results are not yet recorded.
2. Rewards over locations would be poorly identified: workstation mapping is partial (13 of 36), door messages carry no direction and many events have no room.
3. Even with complete data, the reward is identified only up to an equivalence class unless behaviour is seen under different dynamics [7, 8]. Two roster units are not enough to test transfer, which is the main reason to prefer IRL over a transition model.
4. There is no published precedent for hospital staff movement, and in mobility studies simple Markov models match IRL except on complex data [1, 2].

The plan below therefore uses an empirical model for movement and, where behaviour has to respond to new conditions, forward RL with a specified reward. IRL is kept as an optional branch.

| Stage    | Work                                                                                                           | Go / no-go                                                                                                            |
| -------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| 1        | Next-room-change learnability on resolved rooms; staff-held-out test                                           | Is room-level context beyond current/previous room informative?                                                       |
| 2        | Empirical semi-Markov kernel (role × unit × time, back-off) plus dwell hazard; room-change rollouts in the ABM | Do rollouts match dwell, visit and contact distributions?                                                             |
| 3        | Hidden-room HMM with door and workstation emissions, fitted by EM; re-estimate kernel                          | Does likelihood of observed events improve over complete-case fitting?                                                |
| 4        | Forward RL with a specified reward, one shared policy per role (PPO)                                           | Do rollouts match held-out distributions as well as the stage 2 kernel?                                               |
| 5        | Multi-agent training in the ABM (IPPO, then MAPPO)                                                             | Same check, plus contact heterogeneity across staff                                                                   |
| 6        | Counterfactual runs (layouts, staffing, isolation rules), with uncertainty and stated caveats                  | Only if stage 4 or 5 passes                                                                                           |
| Optional | Synthetic recovery study, then linear-feature MCE IRL / logit DDC inside the same EM and dwell model           | Only if door direction, workstation mapping and multi-layout data improve; must beat the kernel on leave-one-unit-out |

### Forward RL with a specified reward

Instead of learning the reward from the logs, specify it and use the logs to check the result. The reward is then explicit and open to review, and the assumptions sit in a few named terms rather than in an unidentified reward.

- State: current room on the floorplan graph, current activity or task and the next task in the queue, time of shift, role, and task demand in nearby rooms (for example patients needing care).
- Actions: move to an adjacent room, stay, or start the next task.
- Reward: task completion minus travel cost, with a small penalty for idle time. Weights are tuned so that rollouts match held-out dwell, visit and transition distributions; this is calibration, not inference of staff preferences.
- Infection outcomes stay out of the reward when the aim is to reproduce current behaviour.
- The specified reward encodes our assumptions about what drives movement. If calibrated rollouts cannot match the held-out distributions, the reward or the state is missing something, and the stage 2 kernel remains the movement model.

### Suggested IRL model design (if revisited)

- **States:** rooms on the ABM floorplan graph, plus activity class and a time-of-shift bin. Keep it tabular.
- **Actions:** move to an adjacent room through a door, or stay. Transitions are deterministic given the floorplan.
- **Reward features:** distance or door hops to likely destinations, room type (bay, side room, nurses' station, medication room, sluice), patient presence or count, time of shift, and interactions with role and unit. Avoid per-room indicators if transfer is the goal.
- **Timing:** a separate dwell hazard, not geometric ticks.
- **Normalisation:** state the reward normalisation and report rewards as one member of an equivalence class [7, 8].

### Software

- A short NumPy implementation of soft value iteration, logit likelihood and forward–backward is probably the easiest option to audit and approve inside the TRE.
- `imitation` (tabular MCE IRL) [13] is useful as a cross-check, but needs a full tabular model and a PyTorch stack.
- `ruspy` (NFXP/MPEC) [38] and `econirl` [39] provide DDC estimators. We could not confirm `econirl`'s authorship, licence or maturity, so vet it before use.
- `hsmmlearn` [34] and `pyhsmm` [35] for dwell modelling; `edhsmm` is archived.

### The gap

We found no IRL study of hospital staff movement or of EHR, login or door-access logs. The work would be novel but unproven, and the case for IRL over a kernel rests on transfer, which is weakly evidenced. IRL is therefore an optional branch with a clear exit, not part of the main plan.

## Multi-agent RL stage

Stage 5 trains staff agents together in the ABM with the specified reward, so that simulated staff respond to changes the logs never show, such as new layouts, staffing levels or isolation rules. Staff share rooms and patients, so one person's movement changes what others face. That makes it a Markov game rather than a single-agent problem.

### Algorithms

- PPO is the single-agent policy-gradient method most multi-agent work builds on. It limits each policy update with a clipped objective [40].
- IPPO runs PPO separately for each agent, with its own value function, and treats the other agents as part of the environment. On the StarCraft Multi-Agent Challenge it matched or beat joint-learning methods with little tuning [41]. With one shared policy per role, it fits staff agents of the same type.
- MAPPO adds a centralised critic that sees the full state during training, while each agent still acts on its own observations at run time. It performed strongly across four cooperative benchmarks, and the authors recommend fewer training epochs per batch than single-agent PPO [42].
- MA-AIRL extends adversarial IRL to Markov games and recovers a reward per agent [43]. Like AIRL it needs environment rollouts, so it only becomes usable once the ABM has been validated against the logs, and only if IRL is revisited.

### PPO with centralised training and decentralised execution

PPO in an actor–critic set-up, trained centrally and run per agent, is the simplest place to start and fits the ABM well.

The actor and the critic:

- The actor is the policy: a network that takes one agent's observation and outputs a probability for each action (move to a neighbouring room, stay, start the next task). Sampling from it keeps behaviour stochastic, which suits staff movement better than a single fixed choice.
- The critic is a value network that estimates the expected future reward from a state. It is used only during training.
- After each batch of simulated shifts, the advantage of each action (how much better it turned out than the critic expected) is estimated, usually with generalised advantage estimation [48]. The actor is updated to make better-than-expected actions more likely, with PPO's clipping limiting how far it moves in one update [40]. The critic is updated to predict returns more accurately.
- The two can share a network body with separate policy and value heads, or be separate networks. A small multi-layer perceptron is enough for a state this size.

Centralised training, decentralised execution (CTDE):

- Decentralised execution means that at run time each staff agent acts only on its own observation, which is how staff behave and how the ABM steps agents.
- Centralised training means that during training the experience of all agents is pooled, and the critic may use information no single agent has, such as the occupancy of every room, where all staff are and the full task queue. Because the critic is discarded after training, this extra information does not leak into behaviour [49].

Two levels, in order of effort:

1. Parameter sharing: one actor–critic per role, trained on the pooled experience of every agent in that role, with each agent's critic seeing only its own observation. This is IPPO with shared parameters [41, 50]; it is quick to set up, and parameter sharing has worked well on cooperative benchmarks [51]. Adding a role indicator or agent index to the observation lets one network behave differently where needed.
2. Centralised critic: the same actors, with a critic that takes the global ward state. This is MAPPO [42]. Move to it if agents need to coordinate (for example covering bays or avoiding the same patient) or if training with independent critics is unstable, since each agent's environment shifts as the others learn.

Practical points:

- If an agent needs memory, for example because the effect of an action shows only later or other staff are out of view, add a recurrent layer (LSTM) to the policy. Recurrent model-free RL is a reasonable baseline for partially observed problems [52].
- Run several copies of the environment in parallel, log per-agent metrics (rewards, rooms visited, contacts) during training, evaluate periodically on held-out scenarios, save checkpoints, and decay the learning rate over training.
- For multi-agent PPO, use fewer epochs per batch than single-agent defaults [42].

### Suggested set-up

- Agents are staff, grouped by role, with parameters shared within a role.
- Observations: current room, next task, time of shift, occupancy of nearby rooms and patient status where the ABM has it.
- Actions: move to an adjacent room, stay, or start the next task, as in the single-agent design.
- Rewards: the specified reward for each role (task completion, travel cost, idle time). If IRL is revisited, a learned reward can replace it. Infection outcomes should stay out of the staff reward if the aim is to reproduce current behaviour; putting them in turns the model into an optimisation of behaviour, which is a separate question.
- Start with IPPO and shared role policies, and move to MAPPO only if coordination between staff, such as covering bays, matters to the results.

### Engine

- Wrap the `amr_hub_abm` `Simulation` as a PettingZoo environment [44], using its parallel API so all staff act at each step. PettingZoo is the standard interface that most MARL libraries accept.
- For level 1, the quickest route is a PettingZoo parallel environment, vectorised with SuperSuit so that all agents share one policy, and trained with Stable-Baselines3 PPO [53] (or `RecurrentPPO` from `sb3-contrib` for the recurrent version).
- For level 2, train with RLlib [45] or BenchMARL [46]. BenchMARL is built on TorchRL, includes IPPO and MAPPO, and is designed for reproducible comparisons between algorithms.
- JaxMARL [47] is much faster because environments run on the GPU in JAX, but it would mean rewriting the ABM step in JAX. It is only worth it if training time becomes the bottleneck. The ABM's existing GPU path uses NVIDIA Warp, so start with the CPU path.
- Policies trained in the ABM are only as good as its dynamics. Before any counterfactual use, check rollouts from trained agents against held-out logs with the same metrics as in the evaluation section.

## References

1. Choi S, Kim J, Yeo H. (2021). TrajGAIL: Generating urban vehicle trajectories using generative adversarial imitation learning. _Transportation Research Part C_ 128:103091. <https://arxiv.org/abs/2007.14189>
2. Tran H, Bui V, Mai T. (2026). Learning sequential mobility choice: A review of route and activity choice through inverse reinforcement learning and imitation learning. arXiv:2608.15339 (preprint). <https://arxiv.org/abs/2608.15339>
3. Ng AY, Russell S. (2000). Algorithms for inverse reinforcement learning. _ICML 2000_, 663–670. <https://mlanthology.org/icml/2000/ng2000icml-algorithms>
4. Abbeel P, Ng AY. (2004). Apprenticeship learning via inverse reinforcement learning. _ICML 2004_. <https://icml.cc/Conferences/2004/proceedings/abstracts/335.htm>
5. Ziebart BD, Maas A, Bagnell JA, Dey AK. (2008). Maximum entropy inverse reinforcement learning. _AAAI 2008_, 1433–1438. <https://www.ri.cmu.edu/publications/maximum-entropy-inverse-reinforcement-learning>
6. Ziebart BD, Bagnell JA, Dey AK. (2010). Modeling interaction via the principle of maximum causal entropy. _ICML 2010_, 1255–1262. <https://ri.cmu.edu/publications/modeling-interaction-via-the-principle-of-maximum-causal-entropy>
7. Cao H, Cohen SN, Szpruch Ł. (2021). Identifiability in inverse reinforcement learning. _NeurIPS 2021_. <https://proceedings.neurips.cc/paper/2021/hash/671f0311e2754fcdd37f70a8550379bc-Abstract.html>
8. Skalse J, Farrugia-Roberts M, Russell S, Abate A, Gleave A. (2023). Invariance in policy optimisation and partial identifiability in reward learning. _ICML 2023_, PMLR 202:32033–32058. <https://proceedings.mlr.press/v202/skalse23a.html>
9. Rust J. (1987). Optimal replacement of GMC bus engines: An empirical model of Harold Zurcher. _Econometrica_ 55(5):999–1033. <https://mail.econometricsociety.org/publications/econometrica/1987/09/01/optimal-replacement-gmc-bus-engines-empirical-model-harold>
10. Rawat P, Rust J. (2026). Dynamic discrete choice and inverse reinforcement learning: Inferring preferences and beliefs from human behavior. arXiv:2608.24362 (preprint). <https://arxiv.org/abs/2608.24362>
11. Zeng S, Hong M, Garcia A. (2025). Structural estimation of Markov decision processes in high-dimensional state space with finite-time guarantees. _Operations Research_ 73(2):720–737. <https://arxiv.org/pdf/2210.01282>
12. van der Laan L, Bibaut A, Kallus N. (2025). Efficient inference for inverse reinforcement learning and dynamic discrete choice models. arXiv:2512.24407 (preprint). <https://arxiv.org/abs/2512.24407>
13. Gleave A, Taufeeque M, Rocamonde J, et al. (2022). imitation: Clean imitation learning implementations. arXiv:2211.11972 (preprint). <https://imitation.readthedocs.io/en/latest/algorithms/mce_irl.html>
14. Ross S, Gordon GJ, Bagnell JA. (2011). A reduction of imitation learning and structured prediction to no-regret online learning. _AISTATS 2011_, 627–635. <https://arxiv.org/pdf/1011.0686>
15. Ho J, Ermon S. (2016). Generative adversarial imitation learning. _NeurIPS 2016_, 4565–4573. <https://papers.neurips.cc/paper/2016/hash/cc7e2b878868cbae992d1fb743995d8f-Abstract.html>
16. Fu J, Luo K, Levine S. (2018). Learning robust rewards with adversarial inverse reinforcement learning. _ICLR 2018_. <https://ar5iv.labs.arxiv.org/html/1710.11248>
17. Garg D, Chakraborty S, Cundy C, Song J, Ermon S. (2021). IQ-Learn: Inverse soft-Q learning for imitation. _NeurIPS 2021_. <https://proceedings.neurips.cc/paper/2021/hash/210f760a89db30aa72ca258a3483cc7f-Abstract.html>
18. Lazzati F, Mutti M, Metelli AM. (2024). Offline inverse RL: New solution concepts and provably efficient algorithms. _ICML 2024_, PMLR 235:26085–26151. <https://proceedings.mlr.press/v235/lazzati24a.html>
19. Ziebart BD, Ratliff N, Gallagher G, et al. (2009). Planning-based prediction for pedestrians. _IROS 2009_, 3931–3936. <https://www.ri.cmu.edu/publications/planning-based-prediction-for-pedestrians>
20. Kitani KM, Ziebart BD, Bagnell JA, Hebert M. (2012). Activity forecasting. _ECCV 2012_, LNCS 7575, 201–214. <https://www.ri.cmu.edu/publications/activity-forecasting>
21. Zhao Z, Liang Y. (2023). A deep inverse reinforcement learning approach to route choice modeling with context-dependent rewards. _Transportation Research Part C_ 149:104079. <https://arxiv.org/abs/2206.10598>
22. Alvarez N, Noda I. (2021). CAMP-IRL agents: Extracting multiple behavior profiles. SciTePress. <https://www.scitepress.org/Papers/2021/102096/pdf/index.html>
23. Yu C, Liu J, Zhao H. (2019). Inverse reinforcement learning for intelligent mechanical ventilation and sedative dosing in intensive care units. _BMC Medical Informatics and Decision Making_ 19(Suppl 2). <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6454602/>
24. Chan AJ, van der Schaar M. (2021). Scalable Bayesian inverse reinforcement learning. _ICLR 2021_. <https://arxiv.org/abs/2102.06483>
25. Hüyük A, Jarrett D, Tekin C, van der Schaar M. (2021). Explaining by imitating: Understanding decisions by interpretable policy learning. _ICLR 2021_. <https://iclr.cc/virtual/2021/poster/2780>
26. Temime L, et al. (2009). Peripatetic health-care workers as potential superspreaders. _PNAS_ 106(43):18420–18425. <https://pmc.ncbi.nlm.nih.gov/articles/PMC2775324>
27. Hornbeck T, Naylor D, Segre AM, Thomas G, Herman T, Polgreen PM. (2012). Using sensor networks to study the effect of peripatetic healthcare workers on the spread of hospital-associated infections. _Journal of Infectious Diseases_ 206(10):1549–1557. <https://pmc.ncbi.nlm.nih.gov/articles/PMC3475631>
28. Vanhems P, et al. (2013). Estimating potential infection transmission routes in hospital wards using wearable proximity sensors. _PLoS ONE_ 8(9):e73970. <https://pmc.ncbi.nlm.nih.gov/articles/PMC3770639>
29. Duval A, et al. (2019). Close proximity interactions support transmission of ESBL-K. pneumoniae but not ESBL-E. coli in healthcare settings. _PLoS Computational Biology_ 15(5):e1006496. <https://doi.org/10.1371/journal.pcbi.1006496>
30. Curtis DE, Hlady CS, Kanade G, Pemmaraju SV, Polgreen PM, Segre AM. (2013). Healthcare worker contact networks and the prevention of hospital-acquired infections. _PLoS ONE_ 8(12):e79906. <https://pmc.ncbi.nlm.nih.gov/articles/PMC3875421/>
31. Bogert K, Doshi P. (2017). Scaling expectation-maximization for inverse reinforcement learning to multiple robots under occlusion. _AAMAS 2017_. <https://ifaamas.csc.liv.ac.uk/Proceedings/aamas2017/pdfs/p522.pdf>
32. Choi J, Kim KE. (2011). Inverse reinforcement learning in partially observable environments. _JMLR_ 12(21):691–730. <https://jmlr.org/papers/v12/choi11a.html>
33. Arcidiacono P, Miller RA. (2011). Conditional choice probability estimation of dynamic discrete choice models with unobserved heterogeneity. _Econometrica_ 79(6):1823–1867. <https://www.econometricsociety.org/doi/10.3982/ECTA7743>
34. hsmmlearn: Explicit-duration hidden semi-Markov models in Python. Software documentation. <https://hsmmlearn.readthedocs.io/en/latest/>
35. Johnson MJ. pyhsmm: Bayesian (HDP-)HMMs and HSMMs in Python. Software repository. <https://github.com/mattjj/pyhsmm>
36. Babeş-Vroman M, Marivate V, Subramanian K, Littman M. (2011). Apprenticeship learning about multiple intentions. _ICML 2011_, 897–904. <https://mlanthology.org/icml/2011/babes2011icml-apprenticeship>
37. Gleave A, Dennis M, Legg S, Russell S, Leike J. (2021). Quantifying differences in reward functions. _ICLR 2021_. <https://arxiv.org/abs/2006.13900>
38. ruspy: Estimation and simulation of dynamic discrete choice models (OpenSourceEconomics). Software documentation. <https://ruspy.readthedocs.io/en/latest/estimation.html>
39. econirl: Structural dynamic discrete choice and IRL estimators in Python. Software documentation; authorship and maturity not confirmed. <https://econirl.readthedocs.io/en/stable/>
40. Schulman J, Wolski F, Dhariwal P, Radford A, Klimov O. (2017). Proximal policy optimization algorithms. arXiv:1707.06347 (preprint). <https://arxiv.org/abs/1707.06347>
41. de Witt CS, Gupta T, Makoviichuk D, Makoviychuk V, Torr PHS, Sun M, Whiteson S. (2020). Is independent learning all you need in the StarCraft multi-agent challenge? arXiv:2011.09533 (preprint). <https://arxiv.org/abs/2011.09533>
42. Yu C, Velu A, Vinitsky E, Gao J, Wang Y, Bayen A, Wu Y. (2022). The surprising effectiveness of PPO in cooperative multi-agent games. _NeurIPS 2022, Datasets and Benchmarks Track_. <https://papers.nips.cc/paper_files/paper/2022/file/9c1535a02f0ce079433344e14d910597-Paper-Datasets_and_Benchmarks.pdf>
43. Yu L, Song J, Ermon S. (2019). Multi-agent adversarial inverse reinforcement learning. _ICML 2019_, PMLR 97:7194–7201. <https://proceedings.mlr.press/v97/yu19e.html>
44. Terry JK, Black B, Grammel N, et al. (2021). PettingZoo: Gym for multi-agent reinforcement learning. _NeurIPS 2021_, 34:15032–15043. <https://proceedings.neurips.cc/paper/2021/hash/7ed2d3454c5eea71148b11d0c25104ff-Abstract.html>
45. Liang E, Liaw R, Nishihara R, et al. (2018). RLlib: Abstractions for distributed reinforcement learning. _ICML 2018_, PMLR 80:3053–3062. <https://proceedings.mlr.press/v80/liang18b.html>
46. Bettini M, Prorok A, Moens V. (2024). BenchMARL: Benchmarking multi-agent reinforcement learning. _JMLR_ 25(217):1–10. <https://jmlr.org/papers/v25/23-1612.html>
47. Rutherford A, Ellis B, Gallici M, et al. (2024). JaxMARL: Multi-agent RL environments and algorithms in JAX. _NeurIPS 2024, Datasets and Benchmarks Track_. <https://proceedings.neurips.cc/paper_files/paper/2024/hash/5aee125f052c90e326dcf6f380df94f6-Abstract.html>
48. Schulman J, Moritz P, Levine S, Jordan MI, Abbeel P. (2016). High-dimensional continuous control using generalized advantage estimation. _ICLR 2016_. <https://arxiv.org/abs/1506.02438>
49. Lowe R, Wu Y, Tamar A, Harb J, Abbeel P, Mordatch I. (2017). Multi-agent actor-critic for mixed cooperative-competitive environments. _NeurIPS 2017_. <https://proceedings.neurips.cc/paper/2017/hash/68a9750337a418a86fe06c1991a1d64c-Abstract.html>
50. Gupta JK, Egorov M, Kochenderfer M. (2017). Cooperative multi-agent control using deep reinforcement learning. _Adaptive and Learning Agents Workshop (ALA), AAMAS 2017_. <https://ala2017.cs.universityofgalway.ie/papers/ALA2017_Gupta.pdf>
51. Terry JK, Grammel N, Son S, Black B, Agrawal A. (2020). Revisiting parameter sharing in multi-agent deep reinforcement learning. arXiv:2005.13625 (preprint). <https://arxiv.org/abs/2005.13625>
52. Ni T, Eysenbach B, Salakhutdinov R. (2022). Recurrent model-free RL can be a strong baseline for many POMDPs. _ICML 2022_, PMLR 162:16691–16723. <https://proceedings.mlr.press/v162/ni22a.html>
53. Raffin A, Hill A, Gleave A, Kanervisto A, Ernestus M, Dormann N. (2021). Stable-Baselines3: Reliable reinforcement learning implementations. _JMLR_ 22(268):1–8. <https://jmlr.org/papers/v22/20-1364.html>
