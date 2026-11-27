"""Schedule facility-backed needs without discarding recorded tasks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from amr_hub_abm.agent.enums import AgentType
from amr_hub_abm.agent.needs_navigation import route_to_facility
from amr_hub_abm.agent.needs_policy import Need
from amr_hub_abm.spatial.furniture import ContentType
from amr_hub_abm.task.task import TaskProgress, TaskSource
from amr_hub_abm.task.task_need import TaskNeed

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.agent.needs_policy import NeedsPolicy
    from amr_hub_abm.spatial.engine import SpatialQuery
    from amr_hub_abm.spatial.furniture import Content
    from amr_hub_abm.spatial.location import Location
    from amr_hub_abm.spatial.room import Room
    from amr_hub_abm.task.task import Task

logger = logging.getLogger(__name__)


def _find_facility(
    agent: Agent,
    need: Need,
    policy: NeedsPolicy,
    rooms: list[Room],
    engine: SpatialQuery,
) -> tuple[Room, Content, tuple[Location, ...]] | None:
    content_type = ContentType.TOILET if need == Need.TOILET else ContentType.CHAIR
    same_floor = [
        room
        for room in rooms
        if room.building == agent.location.building
        and room.floor == agent.location.floor
    ]
    source = engine.get_room(agent)
    if source is None:
        return None
    candidates: list[tuple[Room, Content, tuple[Location, ...]]] = []
    for room in same_floor:
        if need == Need.HUNGER and (
            room.building != policy.eating_building
            or room.floor != policy.eating_floor
            or room.name != policy.eating_room
        ):
            continue
        for content in room.contents:
            if not (
                content.content_type == content_type
                and not content.reserved
                and content.occupier_id in {None, (agent.idx, agent.agent_type)}
            ):
                continue
            route = route_to_facility(agent, source, room, content.location, same_floor)
            if route is not None:
                candidates.append((room, content, route))
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            sum(
                start.distance_to(end)
                for start, end in zip((agent.location, *item[2]), item[2], strict=False)
            ),
            item[0].name,
            item[1].location.x,
            item[1].location.y,
        ),
    )


def _data_task_due(agent: Agent, current_time: int, duration: int) -> bool:
    return any(
        task.source == TaskSource.LOCATION_DATA
        and task.progress != TaskProgress.COMPLETED
        and (
            task.progress
            in {
                TaskProgress.MOVING_TO_LOCATION,
                TaskProgress.IN_PROGRESS,
                TaskProgress.SUSPENDED,
            }
            or task.time_due - task.time_needed <= current_time + duration
        )
        for task in agent.tasks
    )


def _resume_need(  # noqa: PLR0913
    task: TaskNeed,
    agent: Agent,
    current_time: int,
    engine: SpatialQuery,
    rooms: list[Room],
    policy: NeedsPolicy,
    retry_after: dict[tuple[int, Need], int],
) -> None:
    active = [
        item
        for item in agent.tasks
        if item.progress in {TaskProgress.IN_PROGRESS, TaskProgress.MOVING_TO_LOCATION}
    ]
    if len(active) > 1:
        msg = f"Agent {agent.idx} has multiple active tasks."
        raise RuntimeError(msg)
    current = active[0] if active else None
    if (
        current is not None
        and current.progress == TaskProgress.IN_PROGRESS
        and current.time_spent(current_time) >= current.time_needed
    ):
        return
    key = (agent.idx, task.need)
    if current_time < retry_after.get(key, 0):
        return
    facility = _find_facility(agent, task.need, policy, rooms, engine)
    if facility is None:
        retry_after[key] = current_time + policy.retry_interval
        logger.warning(
            "Agent %s cannot resume its %s need; no reachable facility is available.",
            agent.idx,
            task.need.value,
        )
        return
    room, content, route = facility
    task.room = room
    task.preferred_content = content
    if not task.prepare(agent) or not task.on_dispatch(agent):
        retry_after[key] = current_time + policy.retry_interval
        logger.warning("Agent %s could not reserve its urgent facility.", agent.idx)
        return
    if current is not None:
        current.suspend(current_time, agent, engine)
    task.interrupted_task = current
    task.waypoints = route
    task.travel_steps = 0
    task.progress = TaskProgress.NOT_STARTED


def _handle_existing_need(  # noqa: PLR0913
    agent: Agent,
    current_time: int,
    engine: SpatialQuery,
    rooms: list[Room],
    policy: NeedsPolicy,
    retry_after: dict[tuple[int, Need], int],
    retry_blocked: dict[tuple[int, Need], Task],
) -> bool:
    needs = [
        task
        for task in agent.tasks
        if isinstance(task, TaskNeed) and task.progress != TaskProgress.COMPLETED
    ]
    if not needs:
        return False
    if len(needs) > 1:
        msg = f"Agent {agent.idx} has multiple pending need tasks."
        raise RuntimeError(msg)
    task = needs[0]
    level = getattr(agent.internal_state, task.need.value)
    if task.progress == TaskProgress.SUSPENDED:
        urgent = level is not None and level >= policy.rule(task.need).urgent_threshold
        active = any(
            item.progress in {TaskProgress.IN_PROGRESS, TaskProgress.MOVING_TO_LOCATION}
            for item in agent.tasks
        )
        if urgent or (not active and not _data_task_due(agent, current_time, 0)):
            _resume_need(task, agent, current_time, engine, rooms, policy, retry_after)
        return True
    if (
        task.progress in {TaskProgress.IN_PROGRESS, TaskProgress.MOVING_TO_LOCATION}
        and getattr(agent.internal_state, task.need.value)
        < policy.rule(task.need).urgent_threshold
        and any(
            candidate.source == TaskSource.LOCATION_DATA
            and candidate.progress == TaskProgress.NOT_STARTED
            and candidate.time_due - candidate.time_needed <= current_time
            for candidate in agent.tasks
        )
    ):
        task.suspend(current_time, agent, engine)
        return True
    if (
        task.progress == TaskProgress.MOVING_TO_LOCATION
        and task.travel_steps >= policy.travel_timeout
        and task.location is not None
        and not engine.is_target_reached(
            agent.location, task.location, agent.interaction_radius
        )
    ):
        task.suspend(current_time, agent, engine)
        agent.tasks.remove(task)
        retry_after[(agent.idx, task.need)] = current_time + policy.retry_interval
        if task.interrupted_task is not None:
            retry_blocked[(agent.idx, task.need)] = task.interrupted_task
        logger.warning(
            "Agent %s could not reach its %s facility; retrying after time %s.",
            agent.idx,
            task.need.value,
            retry_after[(agent.idx, task.need)],
        )
    return True


def schedule_need(  # noqa: PLR0913
    agent: Agent,
    current_time: int,
    engine: SpatialQuery,
    rooms: list[Room],
    policy: NeedsPolicy,
    retry_after: dict[tuple[int, Need], int],
    retry_blocked: dict[tuple[int, Need], Task],
) -> None:
    """Schedule an eligible need, preempting only after reserving a facility."""
    if agent.agent_type != AgentType.HEALTHCARE_WORKER or _handle_existing_need(
        agent, current_time, engine, rooms, policy, retry_after, retry_blocked
    ):
        return

    active = [
        task
        for task in agent.tasks
        if task.progress in {TaskProgress.IN_PROGRESS, TaskProgress.MOVING_TO_LOCATION}
    ]
    if len(active) > 1:
        msg = f"Agent {agent.idx} has multiple active tasks."
        raise RuntimeError(msg)
    current: Task | None = active[0] if active else None
    if (
        current is not None
        and current.progress == TaskProgress.IN_PROGRESS
        and current.time_spent(current_time) >= current.time_needed
    ):
        return

    for need in policy.eligible(agent.internal_state):
        key = (agent.idx, need)
        blocked_task = retry_blocked.get(key)
        if blocked_task is not None:
            if blocked_task.progress != TaskProgress.COMPLETED:
                continue
            del retry_blocked[key]
        if current_time < retry_after.get(key, 0):
            continue
        rule = policy.rule(need)
        level = getattr(agent.internal_state, need.value)
        if level < rule.urgent_threshold and _data_task_due(
            agent, current_time, rule.duration
        ):
            continue
        facility = _find_facility(agent, need, policy, rooms, engine)
        if facility is None:
            retry_after[(agent.idx, need)] = current_time + policy.retry_interval
            logger.warning(
                "Agent %s has no available reachable %s facility; "
                "retrying after time %s.",
                agent.idx,
                need.value,
                retry_after[(agent.idx, need)],
            )
            continue
        room, content, route = facility
        task = TaskNeed(
            need=need,
            time_needed=rule.duration,
            time_due=current_time + rule.duration,
            room=room,
            content_type=content.content_type,
            preferred_content=content,
            priority=rule.priority,
            interrupted_task=current,
            waypoints=route,
        )
        if not task.prepare(agent) or not task.on_dispatch(agent):
            retry_after[(agent.idx, need)] = current_time + policy.retry_interval
            logger.warning(
                "Agent %s could not reserve its %s facility.", agent.idx, need
            )
            continue
        if current is not None:
            current.suspend(current_time, agent, engine)
        agent.tasks.append(task)
        return
