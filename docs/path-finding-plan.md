# Infer missing door-access tasks

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
