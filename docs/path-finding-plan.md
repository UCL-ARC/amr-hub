# Infer missing door-access tasks

## Context and scope

This plan addresses inter-room navigation when observed location events omit intermediate door accesses, as required by #226. It also contributes the inter-room component of #46.

Inter-room routing determines which rooms and doors an agent should traverse. Intra-room navigation determines a physically traversable path to the next door or destination. The latter is being developed separately using geometric decomposition, an established approach to motion planning [1]. Initially, this work will assume straight-line travel between navigation targets, consistent with the scope of #226.

## Rationale

- **Represent each floor as a connectivity graph**, with rooms as nodes and doors providing connections between rooms. Curtis et al. [2] used a hospital room-adjacency graph and shortest-path hop distances between recorded login locations to estimate healthcare-worker mobility; this study provides a relevant precedent for this representation.
- **Use `NetworkX` unweighted shortest-path search** to select a route with the fewest door crossings. With no edge weights supplied, each graph edge has unit cost, so the search minimises the number of room transitions.
- **Keep room-level route selection separate from detailed geometric path planning.** Planning through an abstract connectivity representation and subsequently refining the route is an established hierarchical pathfinding principle [3]. This plan adopts that general separation without proposing an implementation of Hierarchical Pathfinding A*(HPA*). Geometric decomposition will provide the finer-scale representation for the separate intra-room navigation component [1].

This provides a simple baseline for connecting observed events; it does not uniquely reconstruct the historical route or establish that staff choose routes with the fewest doors. Minimum door crossings is distinct from minimum walking distance or travel time (both of which can be calculated after selecting a route).

Related project background is available in the [ABM tooling review](abm-tools-review.md) and the [staff-movement research review](irl-research.md), which discuss navigation frameworks, movement modelling and incomplete observations.

## Agreed behaviour

At task dispatch, route from the agent's actual room to the next task's room.
Use NetworkX and the existing floor connectivity to minimise door crossings,
with deterministic room and door ordering. Preserve observed events and times.
Routes are confined to one floor; disconnected and cross-floor/building routes
raise a domain error. Multiple doors between the same rooms use the lowest ID.

Estimate travel using straight-line distances from the current position to the
first door, between doors, and from the last door to the target. Use configured
base speed (distance units per simulation step), round legs up, and include door
service durations and task transition overhead. Work backwards from the task's
scheduled start. Add `pathfinding_buffer_seconds`, default zero. Wait until
needed; if already late, leave when available and report actual late starts.

Inferred door tasks are ordered prerequisites, identified separately from
observations. Recorded doors constrain the route through their source room.
Recompute before departure if the start or target changes. Use fixed speed for
inferred journeys, including the final leg. Existing movement strategy applies
when no crossings are inferred. Do not insert idle tasks that delay departure.

## Implementation sequence

1. Build and test deterministic room graphs, preserving door identities.
2. Add typed journeys and timing calculations.
3. Integrate ordered prerequisites into shared CPU/GPU task dispatch.
4. Verify waiting, delays, fixed speed, and documentation.

## Integration with intra-room navigation

The inter-room planner will select the sequence of rooms and real doors. The intra-room planner will refine travel within each room intro geometric waypoints. This division separates topological connectivity from detailed geometric planning [1] and supports coarse-to-fine route refinement [3].

Plan the integration around the following requirements:

- Provide the intra-room planner with the agent's current position and the next selected door or final destination.
- Ensure that the agent approaches each door from its source room and crosses through the opening to the destination side.
- Treat artificial boundaries introduced by decomposition as navigation portals, not as door-access tasks. Crossing them must not generate inferred door events or incur door-service duration.
- Retain the distinction between recorded events, inferred real-door crossings and geometric waypoints.

## Validation

Test same-room, direct, multi-room, disconnected and cross-floor journeys;
nonconsecutive IDs, ties and parallel doors; timing, rounding and buffers;
partial observed routes, no duplication, delays and endpoint movement. Run a
synthetic end-to-end route and shared GPU dispatch checks where available.
Run the full tests and pre-commit checks and report existing failures separately.

## Limits

Straight-line distances are estimates, not obstacle-aware within-room paths.
Stochastic movement can cause lateness. Door access restrictions retain existing
simulation semantics; this change does not introduce opening/locking policies.

## References

1. LaValle, Steven Michael. Planning algorithms. Vol. 1. Cambridge, UK: Cambridge university press, 2006.
2. Curtis, Donald E., Christopher S. Hlady, Gaurav Kanade, Sriram V. Pemmaraju, Philip M. Polgreen, and Alberto M. Segre. "Healthcare worker contact networks and the prevention of hospital-acquired infections." PloS one 8, no. 12 (2013): e79906.
3. Botea, Adi, Martin Müller and Jonathan Schaeffer. “Near Optimal Hierarchical Path-Finding.” J. Game Dev. 1 (2004): 1-30.
