# Search and evidence notes

Companion to [the critical publication review](../amr-hub-novelty-and-publication-review.md). Research and audit date: 29 October 2026.

## Scope and method

This was a targeted, iterative literature search informed by a source-code audit. It was not a registered systematic review. No exhaustive database export, deduplicated screening count, PRISMA flow diagram, formal risk-of-bias instrument or independent second screening was produced. Absence from this report is not evidence that a publication does not exist.

Web searches located primary publisher pages, PubMed/PMC records, institutional copies, author manuscripts and official software/journal documentation. Follow-up searches used exact article titles and DOIs. Scopus, Web of Science and Embase were not searched through their dedicated database interfaces. Publisher metadata were cross-checked with Crossref for the 29 DOI-bearing research references; the ICML inverse-reinforcement-learning paper is linked to an author-hosted PDF.

The following query families describe the searches and can guide an expanded review. They are a reproducible topic guide, not a complete verbatim query log:

| Topic                        | Representative query terms                                                                            |
| ---------------------------- | ----------------------------------------------------------------------------------------------------- |
| Hospital ABM precedent       | hospital agent based model healthcare worker movement infection transmission                          |
| Heterogeneous workers        | peripatetic healthcare workers superspreaders Temime Hornbeck                                         |
| Routine event reconstruction | electronic medical records healthcare worker contact networks Curtis                                  |
| Empirical contacts           | hospital wearable proximity sensors Vanhems Duval contact duration                                    |
| Structural uncertainty       | ICU population interaction structure colonization Mietchen                                            |
| Pathogen-specific validation | hospital Clostridioides difficile agent based model validation Scaria Barker                          |
| AMR mechanisms               | inter-host in-host antibiotic resistance hospital ward Caudill Lawson                                 |
| Recent movement models       | real time movement agent based biosecurity healthcare Thota 2025                                      |
| Recent AMR calibration       | Gerada model calibration gastrointestinal transmission antimicrobial resistant bacteria 2026          |
| Routine-data exposure        | hospital contact networks potential pathogen risk Madhobi                                             |
| Infection informatics        | SmICS openEHR infection control system; genomic microbiological mobility asymptomatic carriers Pei    |
| Spatial/GPU frameworks       | GAMA spatial models; Menge crowd simulation; Mesa 3; FLAME GPU 2                                      |
| Geometry extraction          | indoor floorplan parsing topology repair; navigation oriented topology complex indoor space           |
| Secure computation           | OpenSAFELY open source secure data; human mobility privacy uniqueness                                 |
| Reporting and publication    | ODD 2020; STRESS simulation reporting; FAIR4RS; JOSS submission requirements; JORS software metapaper |

Selection favoured direct scientific competitors, empirical measurement/validation precedents, established methodological frameworks and recent work that could invalidate a novelty claim. Generic promotional articles and secondary summaries were not used to establish scientific findings. The HDI simulator page is retained explicitly as grey literature because it matters to the software landscape. Journal policies are separately labelled and do not count as peer-reviewed evidence.

## Access and appraisal limits

The main report does not claim complete full-text appraisal of all 30 research publications. Evidence was assembled from accessible abstracts, publisher records, selected full-text/indexed sections and institutional or author copies. Access failures and paywalls were not interpreted as negative scientific evidence.

| References            | Evidence access and intended use                                                                                                                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| R01–R05, R07–R09, R11 | Primary abstracts and selected accessible/indexed article sections; establish the published research question, measurements and modelling scope. This is not a systematic reanalysis of their results.                                           |
| R06, R10              | Primarily bibliographic records and abstracts; used for precedent and scope, not detailed grading of calibration or numerical effects.                                                                                                           |
| R12                   | Primary article material and CDC-hosted author copy; used to compare RTLS, layout, device/staff movement, exposure definition and stated limitations. Publication year is 2025, despite later repository indexing.                               |
| R13                   | Primary indexed abstract/sections and DOI metadata; institutional page access failed. Scope is established, but the full calibration/validation design has not been appraised.                                                                   |
| R14–R15               | Primary article/institutional material and accessible sections; used for contact resolution, interoperability and evaluated deployment scope.                                                                                                    |
| R16                   | Primary indexed abstract and metadata; used for the inference problem and input modalities, not a detailed claim about predictive performance.                                                                                                   |
| R17–R20               | Primary software papers, publisher/author material and documentation; establish framework capabilities, not a head-to-head benchmark against AMR-Hub.                                                                                            |
| R21–R22               | Primary abstracts/publisher sections; establish floorplan/topology prior art. Image parsing and CAD extraction are explicitly different input problems.                                                                                          |
| R23–R30               | Primary research/methods material, selected sections and author copies; support reporting, secure computation, privacy, inference and synthetic-model precedent. No numerical mobility-privacy result is transferred to this hospital simulator. |
| R31                   | Project page only; not peer-reviewed validation.                                                                                                                                                                                                 |
| R32–R34               | Official journal/publisher guidance retrieved during the review. SoftwareX-specific author guidance was not fully accessible, so claims are restricted to official publisher scope.                                                              |
| R35–R36               | Official submission/journal-information pages and indexed guidance; used for technical-validation and scientific-contribution expectations.                                                                                                      |

Journal recommendations are editorial judgments, not predictions of acceptance. Fees, indexing, impact factors and detailed word limits were not comprehensively checked. Policies may change after the audit date. The review does not establish freedom from retraction or corrections for every cited item; authors should perform a final bibliographic and full-text check before submission.

One search result attached an unrelated veterinary-journal DOI to the Ng–Russell ICML paper. That identifier was excluded; R28 uses the author-hosted paper. Crossref metadata also corrected several draft author initials. Metadata corroborate identity and publication dates; they do not validate scientific claims.

## Code audit and diagnostic evidence

The main checkout revision and SHA-256 fingerprints for 15 inspected files are in [code-audit-manifest.json](code-audit-manifest.json). The audit followed CPU and GPU movement/transmission paths, contact construction, task dispatch, event-analysis features and splits, geometry documentation/implementation and TRE packaging. File inspection was read-only. The running stochasticity worktree was inspected separately; its code, configurations, inputs and experiment manifest were not changed.

[code-probes.json](code-probes.json) records two minimal diagnostic probes:

1. Construct a CPU `SpatialQuery` with five movement attempts and a synthetic agent at `(0, 0)`, heading zero, speed one and stochasticity zero. Mock every `get_room` lookup to return `None`. The method makes five queries and returns `(1, 0)`, demonstrating its exhausted-retry return contract. This establishes a reachable failure behaviour, not its frequency in the full sweep.
2. Construct two co-located `AgentTrack` instances with samples at times 0 and 1. Run contact detection at threshold 0.1 and episode construction. The episode has two observations and duration 2, although the timestamps span one unit. This establishes a sample-count convention. Whether it overcounts physical exposure depends on the time interval assigned to each sample, especially terminal samples.

Neither probe is a clinical validation experiment or a GPU hardware execution test. GPU parity criticisms are based on source-level differences, not a measured distributional comparison. Coordinate-axis dependence and component reversal probabilities are mathematical consequences of the inspected proposal mechanism; observed reversal/collision frequencies were not measured here.

No sensitive hospital or patient dataset was required for this review. No sweep outcome, effect size, completed-run count or inferred clinical benefit is reported as a research result. The planned 2,100 simulations are discussed as a conditional sensitivity experiment whose interpretation depends on model validity.

## Evidence package and next review step

- [Main draft](../amr-hub-novelty-and-publication-review.md): critical synthesis, novelty assessment, eight candidate publication routes, study designs and reviewer objections.
- [DOI metadata](reference-metadata.json): 29 Crossref records supporting bibliographic identity.
- [Code fingerprints](code-audit-manifest.json): audit provenance.
- [Probe outputs](code-probes.json): the two executed diagnostic results.

Before turning a selected route into a manuscript, extend that route's search with database-specific syntax, citation chaining and full-text extraction. Record study setting, observation process, contact definition, transmission mechanism, calibration data, validation split, uncertainty treatment, released code/data and reproducibility evidence in a structured comparison table. That deeper appraisal is necessary for a defensible systematic comparison; the present targeted review is sufficient to reject broad unsupported novelty claims and choose the next experiments.

## Investigator clarification after the initial draft

The investigator clarified that the public fixture is a toy problem and the planned clinical application covers one year in a UCLH ward. Confirmed streams are routine staff location/activity records, CAD floorplans and organism-specific testing time series. Patient movement data are unavailable. These statements are project context supplied by the investigator, not findings from repository inspection or independent data assessment. The revised report distinguishes restricted data from missing observations and includes a proposed UCLH evaluation design. No clinical data were requested for upload or inspected. A targeted follow-up search on hospital validation and testing observation models supported the distinction between observed test results and latent acquisition; the revision cites existing references R03, R09 and R16.

Further investigator clarification: testing data contain patient-linked positive and negative clinical tests, not systematic screening. Direct ward admission/discharge records are unavailable; stay intervals are inferred from testing timelines. The report now treats presence as latent, identifies test-derived roster selection and future-information leakage, and distinguishes prediction conditional on testing from ward-wide acquisition or incidence. These are methodological implications, not observed biases or validated results.
