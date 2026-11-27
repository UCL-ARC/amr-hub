"""Timed facility use for healthcare-worker needs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from amr_hub_abm.agent.needs_policy import Need
from amr_hub_abm.exceptions import SimulationModeError
from amr_hub_abm.task.task import TaskOccupyContent, TaskSource

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.engine import SpatialQuery


@dataclass
class TaskNeed(TaskOccupyContent):
    """Spend time at a reserved facility before satisfying one need."""

    need: Need = field(kw_only=True)
    source: TaskSource = field(default=TaskSource.NEED, kw_only=True)

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
