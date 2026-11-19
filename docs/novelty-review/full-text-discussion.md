# Full-text discussion: proposed revisions to the novelty review

This is a discussion of possible changes, not a revision of the
[original review](../amr-hub-novelty-and-publication-review.md). Source IDs
match its references; page numbers below are **PDF pages**, not necessarily
journal page numbers. Local PDF links work only where the separately held
papers are available; the original review provides DOI links.

## Scope and conclusion

The main article text of all 29 locally available PDFs, R01-R27 and R29-R30,
was read using page-numbered text extraction. Extraction can distort figures,
tables, equations and reading order, and R25's numerical characters in particular
are poorly extracted. Supplementary files were not systematically obtained or
appraised. R28 was unavailable and is not assessed here; R31-R36 are project
or editorial sources, not part of this full-text exercise. This is a targeted
appraisal, not a systematic review or formal risk-of-bias assessment.

**Recommendation: retain the overall verdict, but strengthen and qualify
several comparisons.** The most consequential change is that R11 is closer
prior art for reconstructing contacts and reallocating staff than the existing
brief description suggests. R10 is also a stronger multi-organism and
resistance-mechanism precedent. R13's calibration design can now be described,
and R03's preliminary validation needs more precise wording. None of these
findings proves that the planned AMR-Hub programme cannot contribute; they
raise the standard for demonstrating what it adds.

No new code audit or assessment of clinical data was undertaken. Statements
about the implementation remain those of the original review and its audit at
revision `dc3b0d620025211232f39e535e45792363a91af2`, not verification of the
current checkout. The UCLH data descriptions remain investigator-provided
context, not independently verified evidence.

## Prioritised proposed changes

### 1. Treat R11 as a principal methods comparator

**Where:** sections 4.1, 6, 7 routes B and C, and 7A.

[R11](../novelty-review-pdfs/R11.pdf), pp. 4-8 and 16-18, combines
long-term-care-facility proximity observations and weekly MRSA swabs with
stochastically generated contacts. It reconstructs missing contacts using
observed ward- and category-specific patterns, compares simulated contact
patterns and incidence with the source study, and tests staff reallocations
while retaining specified care-contact needs. This is more direct prior art
than simply modelling interventions on a recorded temporal network.

The simulated comparisons use data from the same observational study that
informed the model; they should not be called independent validation. A
dedicated sensor study in one long-term-care facility is also not equivalent to
routine operational events in an acute ward.

**Suggested wording:**

> Leclerc and colleagues already used observed proximity data to construct
> stochastic contact networks and compare staff-reallocation scenarios while
> maintaining specified care contacts. A routine-event reconstruction study
> must show which uncertainty, observation or decision problem it resolves
> beyond that precedent, and test its conclusions against independent data
> where feasible.

**Design implication:** add a contact-network reconstruction/reallocation
baseline inspired by R11 to the proposed comparison, alongside simpler
room-level and aggregate approaches. Compare identical observable endpoints,
care-demand assumptions and missing-data scenarios. A synthetic recovery
experiment alone should not be presented as evidence that real unobserved
contacts were recovered.

### 2. Narrow claims about routine records and independent validation

**Where:** sections 4.1-4.2, 6 and route C.

[R03](../novelty-review-pdfs/R03.pdf), pp. 2-4 and 8-9, combines a
room-adjacency graph derived from architectural drawings with electronic
medical record login events. Its preliminary sensor comparison uses
**synthetic logins derived from the sensor data**, rather than a simultaneous
comparison of real logins with independently recorded contacts. This is still
important prior art for routine-event reconstruction, but the present phrase
“sensor-based validation” should not imply a stronger test.

[R02](../novelty-review-pdfs/R02.pdf), pp. 2-3 and 8, replays selected
12-hour sensor-observed shifts repeatedly rather than measuring 360
independent hours of actual contact. [R04](../novelty-review-pdfs/R04.pdf),
pp. 1-2 and 7-8, measures short-range face-to-face proximity, not touch or
observed pathogen transfer. [R12](../novelty-review-pdfs/R12.pdf), pp. 2-4
and 8-9, models staff/device exposure from a short observed shift extended
synthetically; it does not establish patient infection predictions.

**Suggested wording:**

> Routine clinical logins and floorplan-derived adjacency have already been
> used to infer staff contact networks. The published sensor comparison was
> preliminary and used sensor-derived synthetic logins. A stronger evaluation
> would compare actual operational events with independently collected
> observations using explicitly matched spatial and temporal definitions.

### 3. Upgrade the multi-organism and calibration comparisons

**Where:** sections 4.1, 6A.1-6A.4 and route H.

[R10](../novelty-review-pdfs/R10.pdf), pp. 3-6 and 11-13, combines
inter-host agent interactions with within-host bacterial populations,
antibiotic treatment and resistance profiles. The framework accommodates
multiple species and resistance profiles, a more substantive precedent than
the current short table entry indicates. Its examples are preliminary, and
parameter estimation and sensitivity analysis remain future work; it is not
evidence of clinical validation or proof that every claimed AMR-Hub feature
combination already exists.

[R13](../novelty-review-pdfs/R13.pdf) describes a patient-only,
toilet-mediated and background-transmission model, two-stage approximate
Bayesian calibration to a published CDI outbreak and posterior predictive
checks against that outbreak; prospective validation and staff pathways
remain future work (pp. 3-8). The original R13 entry's statement that its full
validation design was not appraised is now outdated.

**Suggested wording:**

> Caudill and Lawson model multiple bacterial species and resistance profiles
> alongside treatment and inter-host transfer, although their demonstrations
> are preliminary. Gerada and colleagues calibrate a patient-only CDI model
> to an outbreak and assess posterior predictions against that same outbreak;
> this is not independent prospective validation.

Continue distinguishing separate pathogen-specific runs from simultaneous
multiple strains, competition and co-colonisation. The literature comparison
does not establish that the currently audited AMR-Hub implementation has
those capabilities.

### 4. Make the UCLH evaluation explicitly observation-dependent

**Where:** section 7A and route C.

[R09](../novelty-review-pdfs/R09.pdf), pp. 3-5 and 8-10, compares
hospital-specific simulated CDI trends with historical observations, while
using modelled colonisation pressure as an indirect proxy for network
fidelity. It is not independent contact-network validation.
[R16](../novelty-review-pdfs/R16.pdf), pp. 2-6 and 9-11, combines actual
patient movement records, imperfect tests and genomics; its synthetic-outbreak
tests and retrospective ranking of later detected cases do not independently
verify every latent carrier or intervention effect.

**Suggested addition:** specify the target before selecting a metric:
recorded staff events, sensor proximity, modelled exposure, observed test
result, latent colonisation and acquisition are different quantities.
Compare models on the same held-out observations; preserve the distinction
between a forecast and retrospective replay with subsequently observed staff
events. Where patient stays are inferred from clinical testing, test
alternative occupancy assumptions and prevent future tests from defining
present occupancy in a forecasting evaluation. A conditional prediction for
tested patients does not establish ward-wide incidence.

### 5. Strengthen structural, geometry and reproducibility baselines

**Where:** sections 4.1, 4.3, 7 routes B and D, and 9.

- [R06](../novelty-review-pdfs/R06.pdf), pp. 3-4 and 11-13, already
  varies staff assignment and contact-network structure; HCWs are largely
  implicit in the patient network. [R07](../novelty-review-pdfs/R07.pdf),
  pp. 3-8 and 10-13, is a **compartmental** model comparing interaction
  structures and recalibrating parameters; it is not a spatial ABM and its
  results do not define a universal real-world threshold. Route B needs to
  demonstrate the added value of its spatial assumptions.
- [R21](../novelty-review-pdfs/R21.pdf), pp. 4-5 and 16-21, repairs
  topological inconsistencies after parsing raster floorplan images and tests
  on a floorplan dataset. [R22](../novelty-review-pdfs/R22.pdf), pp. 4-6 and
  13-16, constructs indoor topology from simplified building plans, with
  real and simulated examples. Neither is a direct head-to-head evaluation
  of AMR-Hub's CAD workflow. Compare inputs, annotation, topology errors,
  correction effort and downstream effects rather than asserting identical
  tasks.
- [R25](../novelty-review-pdfs/R25.pdf), pp. 2-3 and 9-14, supports a
  model description linked to purpose, evaluation patterns and code;
  [R26](../novelty-review-pdfs/R26.pdf), pp. 7-8 and 10-12, adds reporting
  of experiments, random sampling, implementation and reproducible test
  data. Neither a checklist nor open code by itself establishes validity.
  [R27](../novelty-review-pdfs/R27.pdf), pp. 2-3, gives software-specific
  FAIR principles, including version identifiers, provenance and licences;
  controlled access can be compatible with accessibility.

**Suggested wording:** “Use ODD to describe the model and its intended
evaluation, STRESS-ABS to report experiments and implementation, and FAIR4RS
to assess software reuse. Separately report verification, independent
validation and restrictions on data release.”

### 6. Qualify deployment, privacy and synthetic-model claims

**Where:** sections 4.4, 7 routes F and G, and 9.

[R23](../novelty-review-pdfs/R23.pdf), pp. 8-10, describes open analytical
code run inside a secure data environment, with manually checked aggregate
outputs. This is a precedent for the governance pattern, not a benchmark of
AMR-Hub's TRE deployment. [R24](../novelty-review-pdfs/R24.pdf), pp. 1-5,
studies uniqueness in mobile-phone traces. Its numerical result cannot be
transferred directly to simulated hospital trajectories; it motivates an
output-specific disclosure assessment rather than proving a particular
re-identification risk.

[R30](../novelty-review-pdfs/R30.pdf), pp. 4-5, 9-11 and 24-25, is a
synthetic hospital COVID-19 ABM with an assumed layout, simulation-based
intervention comparisons and a check of one airborne-transmission calculation.
The authors identify empirical hospital data and validation as future work.
It is a publication precedent, not evidence that synthetic scenarios yield
clinically reliable intervention recommendations.

## Compact evidence ledger

Each entry records the principal implication for the existing review. “Retain”
means the present broad framing is reasonable, not that every numerical or
methodological claim has been independently reproduced.

| Source                                | Full-text observation and proposed treatment                                                                                                                                                |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [R01](../novelty-review-pdfs/R01.pdf) | Hypothetical ICU, heterogeneous staff roles and assumed schedules; retain as heterogeneity precedent, not real-ward validation (pp. 1, 4-6).                                                |
| [R02](../novelty-review-pdfs/R02.pdf) | Selected sensor-observed shifts replayed repeatedly; distinguish observed contact data from synthetic simulation time and outcomes (pp. 2-3, 8).                                            |
| [R03](../novelty-review-pdfs/R03.pdf) | Routine logins plus drawing-derived adjacency; clarify the sensor-derived synthetic-login comparison (pp. 2-4, 8-9).                                                                        |
| [R04](../novelty-review-pdfs/R04.pdf) | Proximity badges measure face-to-face encounters at a defined resolution, not touch or transmission (pp. 1-2, 7-8).                                                                         |
| [R05](../novelty-review-pdfs/R05.pdf) | Four months of rehabilitation-facility proximity with outages and no visitor observations; retain setting and coverage caveats (pp. 2, 5, 8).                                               |
| [R06](../novelty-review-pdfs/R06.pdf) | Patient-network and staff-allocation scenarios provide direct structural precedent; worker interactions are largely implicit (pp. 3-4, 11-13).                                              |
| [R07](../novelty-review-pdfs/R07.pdf) | Compartmental comparison with structure-specific calibration; retain uncertainty precedent, not spatial-ABM equivalence (pp. 3-8, 10-13).                                                   |
| [R08](../novelty-review-pdfs/R08.pdf) | CDI ABM with multiple agent types and environmental transmission; simulated intervention effects are not demonstrated future predictive validity (pp. 1-3, 9).                              |
| [R09](../novelty-review-pdfs/R09.pdf) | Hospital-specific CDI outcomes and indirect network proxy; keep outcome and network validation separate (pp. 3-5, 8-10).                                                                    |
| [R10](../novelty-review-pdfs/R10.pdf) | Inter-host/within-host multi-species and resistance-profile framework; strengthen precedent, qualify preliminary application (pp. 3-6, 11-13).                                              |
| [R11](../novelty-review-pdfs/R11.pdf) | Reconstructed contacts, source-data comparisons and care-constrained reallocation; elevate as a principal comparator without calling it independent validation (pp. 4-8, 16-18).            |
| [R12](../novelty-review-pdfs/R12.pdf) | Dedicated RTLS and a short observed shift support exposure modelling, not observed touch or patient infection prediction (pp. 2-4, 8-9).                                                    |
| [R13](../novelty-review-pdfs/R13.pdf) | Two-stage outbreak calibration and same-outbreak posterior checks; replace the outdated unappraised-design statement (pp. 3-8).                                                             |
| [R14](../novelty-review-pdfs/R14.pdf) | Patient unit-day co-location is an exposure proxy, not necessarily simultaneous or direct contact; retain distinction (pp. 2-3, 10).                                                        |
| [R15](../novelty-review-pdfs/R15.pdf) | Surveillance uses 24-hour co-location slots, including potentially noncontemporaneous stays; usability limitations and timing exclusions matter (pp. 2, 4, 6, 8).                           |
| [R16](../novelty-review-pdfs/R16.pdf) | Actual patient mobility, microbiology and genomics inform latent-carrier inference; distinguish synthetic validation and retrospective detection ranking from latent truth (pp. 2-6, 9-11). |
| [R17](../novelty-review-pdfs/R17.pdf) | GAMA documents GIS, routing and BDI platform capabilities; do not infer that every GAMA hospital model uses them (pp. 8-12).                                                                |
| [R18](../novelty-review-pdfs/R18.pdf) | Modular crowd movement and task machinery are established; the studied version and office example are not a validated hospital infection model (pp. 7-13, 17-20, 28).                       |
| [R19](../novelty-review-pdfs/R19.pdf) | Mesa 3 supports spatial modelling and experimentation; retain as a framework baseline, not a head-to-head hospital comparison (pp. 2-6).                                                    |
| [R20](../novelty-review-pdfs/R20.pdf) | FLAME GPU 2 has published GPU benchmarks under specified conditions; those numbers do not establish comparative AMR-Hub speed (pp. 2, 4, 15-20).                                            |
| [R21](../novelty-review-pdfs/R21.pdf) | Raster parsing and topology repair are relevant prior art but have different inputs from CAD ingestion (pp. 4-5, 16-21).                                                                    |
| [R22](../novelty-review-pdfs/R22.pdf) | Indoor room/door topology is constructed from simplified building plans and tested on limited examples; retain as topology precedent (pp. 4-6, 13-16).                                      |
| [R23](../novelty-review-pdfs/R23.pdf) | Open code, controlled execution and checked aggregate release are established secure-analytics practice (pp. 8-10).                                                                         |
| [R24](../novelty-review-pdfs/R24.pdf) | Mobile-trace uniqueness motivates privacy review, but its results are not hospital-trajectory risk estimates (pp. 1-5).                                                                     |
| [R25](../novelty-review-pdfs/R25.pdf) | Updated ODD connects model purpose, patterns and code; experiment reporting remains a separate concern (pp. 2-3, 9-14).                                                                     |
| [R26](../novelty-review-pdfs/R26.pdf) | STRESS distinguishes model logic, experiments, implementation and code access; explicitly report verification and validation too (pp. 7-8, 10-12).                                          |
| [R27](../novelty-review-pdfs/R27.pdf) | FAIR4RS is an aspirational software framework, not proof of scientific validity or a requirement to expose restricted data (pp. 2-3).                                                       |
| [R29](../novelty-review-pdfs/R29.pdf) | `sbi` is an existing likelihood-free inference toolkit; using it does not itself solve identifiability or validate a hospital model (pp. 1-3).                                              |
| [R30](../novelty-review-pdfs/R30.pdf) | Synthetic hospital epidemic ABM is a publication precedent; its event probabilities and layout are assumed and empirical validation remains future work (pp. 4-5, 9-11, 24-25).             |

## Follow-up before changing the review

1. Read the separate synthetic temporal-contact-network method cited by R11,
   [DOI 10.1371/journal.pcbi.1012227](https://doi.org/10.1371/journal.pcbi.1012227).
   It has **not** been appraised here; check its actual assumptions and
   evaluation before positioning a new reconstruction method against it.
2. Obtain and appraise R28 before relying on its detailed inverse
   reinforcement learning claims. Check relevant supplements, especially
   for R08, R11, R13, R25 and R30, before asserting exact validation or
   implementation details.
3. If the original review is later revised, update its section 2 access
   description and the separate [search and evidence notes](search-and-evidence-notes.md):
   their earlier statements about limited access to R10, R13 and R16 reflect
   the original search, not this later full-text appraisal. Preserve that
   chronology rather than retroactively describing the original search as
   exhaustive.
4. Before manuscript submission, extend the literature search, check
   corrections and current software versions, and validate any proposed
   study against the observations and governance actually available.
