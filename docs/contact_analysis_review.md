# Contact analysis review + outsider pointers for the simulation

I looked mainly at `contact_analysis.py`, `simulation.py`, `agent/agent.py`, `agent/internal_state.py` and `run.py` (all under `python-code/src/amr_hub_abm/`). My goal was to get a general sense of the simulation and the current strategy for contact and disease spread.

## Hard coded contacts

I confirm that agents replay a fixed schedule, so HCW–patient contacts are hard-coded and there is no decision-making policy. Also patients have no tasks and never leave their beds.

- Each step the agent picks a task by earliest due time, then priority. Every task has the default priority, so in practice this is log order.
- The input log has exactly 68 attend events.
- The extra time under `fixed` is spent with agents arriving early and waiting at the bed, not extra care time, which I find unintuitive.
- Patient–patient contact is always 0: patients don't move and beds are 1 m apart.

## Movement: speed and stochasticity

Stochasticity is only noise on speed and direction, nothing behavioural. Speed varies in just three ways.

- **`fixed`**: constant base speed, 0.01 units per step.
- **`deadline_paced`**: speed = remaining distance / time left before the task starts, recomputed every step so a late agent can move unrealistically fast.
- **Noise**: one parameter (`agent_stochasticity` = 0.5) is used twice, in `spatial/engine.py` `propose_new_coordinates`:
  - `1 + N(0, 0.5)` drawn separately for the x and y step.
- There is no per-agent speed, no slowing in crowds and no difference by task or role, which will be important to add.

Two movement bugs make this worse:

- When all 5 move attempts fail, `try_move_one_step` returns the last _rejected_ position.
- The wall check only tests the end point of a step, not the path.

## The simulation step and time

In RL terms, `Simulation.step` is a turn-based multi-agent environment (like PettingZoo's AEC style), not a simultaneous one, and its time units need pinning down.

- Agents are shuffled, then act one after another. A later agent sees the world already changed by earlier agents in the same step, which should be addressed since the state is recorded before the agent acts -- it acts as what the agent sees, and the final state is added once at the end.
- Since there no reward, observation space or learned policy, currently the "action" is a scripted step towards the current task. If we plug in RL or IRL later, this is where an observation and action interface would go.

### Time and units

- One step = `length_of_timestep_in_seconds`, currently 1 s, so a 06:55–19:05 day is 43,800 steps.
- Event timestamps are converted using the step length, but task durations (attend patient 15, workstation 30) and speed are counted in steps. Changing the step length silently changes real task durations and walking speed.
- Floorplan units are never stated. The CLI says metres; if so, 0.01 units/step at 1 s is 1 cm/s, about 100× slower than walking.
- The logged event time is treated as the task's end so this needs checking against what the TRE timestamps actually mean.

## The contact definition and agent bodies

A close contact is currently two bodiless points within 10 cm at the same step (based on 0.01 units/step). That is a very strict definition, far from the 1–2 m (plus a minimum duration) typical of contact tracing.

### How `contact_analysis.py` measures contacts today

- Same building and floor, distance ≤ threshold (default 0.1), at the same recorded step. A grid with cell size = threshold keeps this fast.
- If both agents are in different known rooms, the contact is dropped. Agents on a door line or room boundary resolve to no room, so contacts across a doorway are kept.
- Consecutive steps for a pair are merged into an episode; a single missed step splits it. Agents jittering at the threshold therefore fragment into many short episodes.
- Duration is just a step count. There is no weighting by distance, no cumulative dose and no minimum duration.

### What should change (pointers from my past MARL work)

- Agents should have a body (a radius or footprint), so a contact means bodies touching or within a set distance, and agents can't stack on the same spot.
- With bodies, we need a collision/contact tracker in the step loop instead of the post-hoc distance check. It should log agent–agent and agent–object contacts with start, end and duration.
- Existing tools to look at: PettingZoo's multi-particle environments (MPE) give each entity a size and check collisions every step, and the physics engines used with Gymnasium (Box2D, MuJoCo) report contacts directly. (Not checked against their current docs.)
- Agree what "contact" means for the AMR question: proximity, direct care (task-based) or surface-mediated.

## Internal needs

Hunger, toilet need and fatigue (`agent/internal_state.py`) only ever rise, capped at 1, and nothing reads them.

- They need a decay or recovery factor: e.g. fatigue drops while sitting, hunger resets after a restaurant visit, toilet need after a WC visit.
- They need to feed into behaviour (e.g. when an HCW takes a break), otherwise they have no effect on movement or contacts.

## What the disease layer will need - just a few pointers

- **An internal contact tracker.** The disease layer will need its own record of who and what was touched, for how long and when, using the same collision tracker as above.
- **Decay on agents.** Contamination on hands and clothing should decay over time and reset with hand hygiene.
- **Items and surfaces.** Things agents' bodies touch (bed rails, workstations, door handles, chairs) need to be tracked with the same collision tracker and their own decay factor. For AMR organisms this is likely the main route, more than person-to-person proximity.
- **A dose model.** Exposure should build up from contact duration and contamination rather than counting episodes.
