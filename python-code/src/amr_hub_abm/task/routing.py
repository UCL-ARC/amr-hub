"""Infer ordered door crossings and nominal travel times within a floor."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

import networkx as nx

from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.task.task import TaskDoorAccess, TaskProgress

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.engine import SpatialQuery
    from amr_hub_abm.spatial.floor import Floor
    from amr_hub_abm.task.task import Task


@dataclass
class Journey:
    """
    A planned sequence of door crossings needed to reach a task on one floor.

    Crossings are inferred prerequisites of the original target task and must
    execute in route order, independently of ordinary task-priority selection.
    The target retains its observed deadline. Timing estimates determine when
    to depart; they do not guarantee arrival on time under stochastic movement.

    Parameters
    ----------
    target : Task
        Original task to execute after all inferred crossings are complete.
    crossings : tuple[TaskDoorAccess, ...]
        Inferred door-access tasks in execution order. Their progress is updated
        during simulation and used by ``next_task`` to select the next action.
    room_ids : tuple[int, ...]
        Ordered room IDs from the starting room to the target's approach room.
        For a recorded door event, the approach room is the room being exited.
    distances : tuple[float, ...]
        Straight-line leg lengths in spatial model units: current position to
        the first crossing target, between successive crossing targets, and
        from the last crossing target to the original task location. Crossing
        targets are offset into their destination rooms.
    travel_steps : int
        Estimated simulation steps until arrival at the target, including each
        travel leg rounded up at the configured base speed, door-task durations,
        and a dispatch step after each crossing. Excludes the departure buffer
        and the original target task's duration.
    departure : int
        Planned departure timestep, calculated by subtracting ``travel_steps``
        and the configured buffer from the target's scheduled start time
        (``time_due - time_needed``). May be negative when the journey would
        need to begin before the simulation starts.

    """

    target: Task
    crossings: tuple[TaskDoorAccess, ...]
    room_ids: tuple[int, ...]
    distances: tuple[float, ...]
    travel_steps: int
    departure: int

    @property
    def next_task(self) -> Task:
        """Return the next unfinished crossing, or the original target."""
        return next(
            (t for t in self.crossings if t.progress != TaskProgress.COMPLETED),
            self.target,
        )


def room_graph(floor: Floor) -> nx.Graph:
    """Build a deterministic room graph using the floor's existing topology."""
    graph = nx.Graph()
    graph.add_nodes_from(floor.room_ids)
    graph.add_edges_from(sorted(floor.edge_set))
    return graph


def plan_journey(agent: Agent, task: Task, engine: SpatialQuery) -> Journey | None:
    """
    Plan missing crossings from the current position to a prepared task.

    Distances are straight-line estimates. The discrete schedule includes one
    dispatch tick after each door completes. Observed timestamps are untouched.
    """
    target = task.location
    if target is None:
        msg = "Routing requires a prepared task location."
        raise SimulationModeError(msg)
    if (target.building, target.floor) != (
        agent.location.building,
        agent.location.floor,
    ):
        msg = f"Agent {agent.idx}: routing across buildings or floors is unsupported."
        raise SimulationModeError(msg)
    source = engine.get_room(agent)
    destination = engine.get_room(agent, coords=(target.x, target.y))
    required_room = task.routing_room_id()
    floor = next(
        (
            f
            for b in engine.space
            if b.name == target.building
            for f in b.floors
            if f.floor_number == target.floor
        ),
        None,
    )
    if required_room is not None and floor is not None:
        destination = next((r for r in floor.rooms if r.room_id == required_room), None)
    if source is None or destination is None or floor is None:
        msg = f"Agent {agent.idx}: cannot resolve routing source or destination room."
        raise SimulationModeError(msg)
    if source.room_id == destination.room_id:
        return None
    try:
        path = nx.shortest_path(room_graph(floor), source.room_id, destination.room_id)
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        msg = (
            f"Agent {agent.idx}: no door route from room {source.room_id} "
            f"to {destination.room_id} on floor {floor.floor_number}."
        )
        raise SimulationModeError(msg) from exc
    speed = agent.base_movement_speed
    if not math.isfinite(speed) or speed <= 0:
        msg = "Routing requires a finite positive base movement speed."
        raise SimulationModeError(msg)
    rooms = {room.room_id: room for room in floor.rooms}
    crossings: list[TaskDoorAccess] = []
    for before, after in pairwise(path):
        door = min(
            (d for d in rooms[before].doors if after in d.connecting_rooms),
            key=lambda d: d.door_id,
        )
        crossing = TaskDoorAccess(
            time_needed=agent.routing_door_duration,
            time_due=task.time_due,
            door=door,
            building=source.building,
            floor=source.floor,
            destination_room=after,
            inferred=True,
            fixed_speed=True,
        )
        crossing.on_start_moving(agent, engine)
        crossings.append(crossing)
    points = [agent.location, *(c.location for c in crossings), target]
    distances = tuple(
        a.distance_to(b) for a, b in pairwise(points) if a is not None and b is not None
    )
    steps = sum(math.ceil(d / speed) for d in distances)
    steps += len(crossings) * (agent.routing_door_duration + 1)
    departure = task.time_due - task.time_needed - steps - agent.routing_buffer_steps
    return Journey(task, tuple(crossings), tuple(path), distances, steps, departure)


def perform_journey(agent: Agent, current_time: int, engine: SpatialQuery) -> bool:
    """Execute an active journey before ordinary task-priority selection."""
    journey = agent.journey
    if journey is None:
        return False
    task = journey.next_task
    if task.progress == TaskProgress.COMPLETED:
        agent.journey = None
        return False
    task.update_progress(current_time=current_time, agent=agent, engine=engine)
    return True
