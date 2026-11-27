"""Find simple same-floor routes through known door openings."""

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING

from shapely.geometry import LineString, Point

from amr_hub_abm.spatial.location import Location

if TYPE_CHECKING:
    from amr_hub_abm.agent.agent import Agent
    from amr_hub_abm.spatial.door import Door
    from amr_hub_abm.spatial.room import Room
    from amr_hub_abm.spatial.wall import Wall


def _clear_segment(
    start: Location, end: Location, walls: list[Wall], radius: float
) -> bool:
    if start == end:
        return True
    line = LineString([(start.x, start.y), (end.x, end.y)])
    return not any(line.intersects(wall.polygon.buffer(radius)) for wall in walls)


def _door_points(
    door: Door, source: Room, destination: Room, radius: float, walls: list[Wall]
) -> tuple[Location, Location] | None:
    if door.start is None or door.end is None:
        return None
    dx = door.end[0] - door.start[0]
    dy = door.end[1] - door.start[1]
    length = math.hypot(dx, dy)
    if length <= 2 * radius:
        return None
    midpoint_x = (door.start[0] + door.end[0]) / 2
    midpoint_y = (door.start[1] + door.end[1]) / 2
    thickness = max((wall.thickness for wall in walls), default=0.0)
    offset = thickness / 2 + radius + 0.05
    points = [
        Location(
            building=source.building,
            floor=source.floor,
            x=midpoint_x + sign * (-dy / length) * offset,
            y=midpoint_y + sign * (dx / length) * offset,
        )
        for sign in (-1, 1)
    ]
    for first, second in (points, points[::-1]):
        if source.region.contains(
            Point(first.x, first.y)
        ) and destination.region.contains(Point(second.x, second.y)):
            return first, second
    return None


def route_to_facility(
    agent: Agent, source: Room, destination: Room, target: Location, rooms: list[Room]
) -> tuple[Location, ...] | None:
    """Return clear waypoints or None when no modeled same-floor route exists."""
    same_floor = [
        room
        for room in rooms
        if room.building == source.building and room.floor == source.floor
    ]
    by_id = {room.room_id: room for room in same_floor}
    walls = [wall for room in same_floor for wall in room.walls or []]
    if destination.room_id not in by_id:
        return None
    if _clear_segment(agent.location, target, walls, agent.interaction_radius):
        return (target,)

    queue: deque[tuple[Room, Location, tuple[Location, ...]]] = deque(
        [(source, agent.location, ())]
    )
    visited: set[tuple[int, int]] = set()
    while queue:
        room, start, route = queue.popleft()
        if room.room_id == destination.room_id and _clear_segment(
            start, target, walls, agent.interaction_radius
        ):
            return (*route, target)
        for door in room.doors:
            if room.room_id not in door.connecting_rooms:
                continue
            other_id = (
                door.connecting_rooms[1]
                if door.connecting_rooms[0] == room.room_id
                else door.connecting_rooms[0]
            )
            other = by_id.get(other_id)
            if other is None or (other_id, door.door_id) in visited:
                continue
            points = _door_points(door, room, other, agent.interaction_radius, walls)
            if points is None:
                continue
            entrance, exit_point = points
            if not _clear_segment(start, entrance, walls, agent.interaction_radius):
                continue
            if not _clear_segment(
                entrance, exit_point, walls, agent.interaction_radius
            ):
                continue
            visited.add((other_id, door.door_id))
            queue.append((other, exit_point, (*route, entrance, exit_point)))
    return None
