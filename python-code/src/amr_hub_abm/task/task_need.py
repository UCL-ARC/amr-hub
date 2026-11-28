"""Timed facility use for healthcare-worker needs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from amr_hub_abm.agent.needs_policy import Need
from amr_hub_abm.agent.utils import remove_agent_occupancy
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.task.task import Task, TaskOccupyContent, TaskProgress, TaskSource

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.engine import SpatialQuery
    from amr_hub_abm.spatial.location import Location


@dataclass
class TaskNeed(TaskOccupyContent):
    """Spend time at a reserved facility before satisfying one need."""

    need: Need = field(kw_only=True)
    source: TaskSource = field(default=TaskSource.NEED, kw_only=True)
    travel_steps: int = field(default=0, init=False)
    interrupted_task: Task | None = field(default=None, kw_only=True, repr=False)
    waypoints: tuple[Location, ...] = field(default=(), kw_only=True)
    waypoint_index: int = field(default=0, init=False)

    def _occupy(self, agent: Agent) -> None:
        agent_id = (agent.idx, agent.agent_type)
        if (
            self.content is None
            or self.content.reserver_id != agent_id
            or not self.content.try_occupy(agent_id)
        ):
            msg = f"Agent {agent.idx} could not occupy its reserved need facility."
            raise SimulationModeError(msg)
        agent.stationary = True

    def on_started(self, agent: Agent, current_time: int) -> None:  # noqa: ARG002
        """Occupy the facility while the need is being satisfied."""
        self._occupy(agent)

    def on_start_moving(self, agent: Agent, engine: SpatialQuery) -> None:  # noqa: ARG002
        """Count only travel steps, not time spent suspended."""
        if self.waypoints:
            self.waypoint_index = 0
            self.location = self.waypoints[0]
        self.travel_steps += 1

    def _tick_moving(
        self, current_time: int, agent: Agent, engine: SpatialQuery
    ) -> None:
        if (
            self.waypoints
            and self.waypoint_index < len(self.waypoints) - 1
            and self.location is not None
            and engine.is_target_reached(
                agent.location, self.location, agent.interaction_radius
            )
        ):
            self.waypoint_index += 1
            self.location = self.waypoints[self.waypoint_index]
        if self.location is None:
            msg = "Need task has no facility location."
            raise SimulationModeError(msg)
        if engine.is_target_reached(
            agent.location, self.location, agent.interaction_radius
        ):
            self._start(current_time, agent)
            return
        self.travel_steps += 1
        self._move_to_waypoint(current_time, agent, engine)

    def _tick_not_started(
        self, current_time: int, agent: Agent, engine: SpatialQuery
    ) -> None:
        if self.location is None:
            msg = "Need task has no facility location."
            raise SimulationModeError(msg)
        if engine.is_target_reached(
            agent.location, self.location, agent.interaction_radius
        ):
            self._start(current_time, agent)
            return
        self.progress = TaskProgress.MOVING_TO_LOCATION
        self.on_start_moving(agent, engine)
        remove_agent_occupancy(agent, current_time=current_time, engine=engine)
        self._move_to_waypoint(current_time, agent, engine)

    def _move_to_waypoint(
        self, current_time: int, agent: Agent, engine: SpatialQuery
    ) -> None:
        if self.location is None:
            msg = "Need task has no waypoint."
            raise SimulationModeError(msg)
        agent.update_movement_speed_for_task(self, current_time)
        agent.movement_speed = min(
            agent.movement_speed, agent.location.distance_to(self.location)
        )
        engine.head_to_point(agent, (self.location.x, self.location.y))
        engine.move_one_step(agent)

    def on_resumed(self, agent: Agent, current_time: int) -> None:  # noqa: ARG002
        """Reoccupy the facility after an interruption."""
        self._occupy(agent)

    def on_suspended(
        self, agent: Agent, current_time: int, engine: SpatialQuery
    ) -> None:
        """Release both reservation and occupancy on interruption."""
        super().on_suspended(agent, current_time, engine)
        if self.content is not None and self.content.release_occupancy(
            (agent.idx, agent.agent_type)
        ):
            agent.stationary = False

    def on_completed(
        self,
        agent: Agent,
        current_time: int,  # noqa: ARG002
        engine: SpatialQuery,  # noqa: ARG002
    ) -> None:
        """Release the facility and reset only the completed need."""
        if self.content is None or not self.content.release_occupancy(
            (agent.idx, agent.agent_type)
        ):
            msg = f"Agent {agent.idx} no longer occupies its need facility."
            raise SimulationModeError(msg)
        agent.stationary = False
        agent.internal_state.reset(
            fatigue=self.need == Need.FATIGUE,
            hunger=self.need == Need.HUNGER,
            toilet_need=self.need == Need.TOILET,
        )
        agent.tasks[:] = [task for task in agent.tasks if task is not self]
