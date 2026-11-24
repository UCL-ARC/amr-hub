"""Synthetic metre-based geometry for CPU collision safety specifications."""

from dataclasses import dataclass, replace
from math import atan2, cos, hypot, radians, sin

import numpy as np

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.spatial.building import Building
from amr_hub_abm.spatial.door import Door
from amr_hub_abm.spatial.engine import SpatialQuery
from amr_hub_abm.spatial.floor import Floor
from amr_hub_abm.spatial.location import Location
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.spatial.wall import Wall

BUILDING = "Synthetic collision MRE"


@dataclass
class CollisionScene:
    """Pair production movement objects with their synthetic geometry."""

    engine: SpatialQuery
    agent: Agent
    rooms: list[Room]


def make_room(
    walls: list[Wall],
    *,
    room_id: int = 0,
    doors: list[Door] | None = None,
    building: str = BUILDING,
    floor: int = 0,
) -> Room:
    """Build an empty physical room with a reproducible explicit generator."""
    return Room(
        room_id=room_id,
        name=f"Room {room_id}",
        building=building,
        floor=floor,
        walls=walls,
        contents=[],
        doors=doors or [],
        rng_generator=np.random.default_rng(42),
    )


def make_scene(
    *,
    doorway: bool = False,
    start: tuple[float, float] = (1.5, 1.0),
    end: tuple[float, float] = (2.5, 1.0),
    radius: float = 0.01,
    angle_degrees: float = 0.0,
) -> CollisionScene:
    """Recreate the issue-262 two-room floorplan and one deterministic proposal."""
    angle = radians(angle_degrees)

    def rotate(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle))

    doors = (
        [
            Door(
                start=(2.0, 0.5),
                end=(2.0, 1.5),
                connecting_rooms=(0, 1),
                door_id=0,
                is_open=True,
                access_control=(True, True),
            )
        ]
        if doorway
        else []
    )
    shared = (
        [Wall((2.0, 0.0), (2.0, 0.5)), Wall((2.0, 1.5), (2.0, 2.0))]
        if doorway
        else [Wall((2.0, 0.0), (2.0, 2.0))]
    )
    doors = [
        replace(door, start=rotate((2.0, 0.5)), end=rotate((2.0, 1.5)))
        for door in doors
    ]
    rooms = []
    for room_id, (left, right) in enumerate(((0.0, 2.0), (2.0, 4.0))):
        outer = left if room_id == 0 else right
        rooms.append(
            make_room(
                [
                    Wall(rotate(wall.start), rotate(wall.end))
                    for wall in [
                        Wall((left, 0.0), (right, 0.0)),
                        Wall((left, 2.0), (right, 2.0)),
                        Wall((outer, 0.0), (outer, 2.0)),
                        *shared,
                    ]
                ],
                room_id=room_id,
                doors=doors,
            )
        )
    start, end = rotate(start), rotate(end)
    agent = Agent(
        idx=0,
        location=Location(x=start[0], y=start[1], floor=0, building=BUILDING),
        heading_rad=atan2(end[1] - start[1], end[0] - start[0]),
        movement_speed=hypot(end[0] - start[0], end[1] - start[1]),
        stochasticity=0.0,
        interaction_radius=radius,
        rng_generator=np.random.default_rng(42),
    )
    engine = SpatialQuery([Building(BUILDING, [Floor(0, rooms)])], 5)
    return CollisionScene(engine, agent, rooms)


def make_row_scene(open_joins: tuple[bool, ...]) -> CollisionScene:
    """Build adjacent square rooms with explicitly open or solid shared joins."""
    scene = make_scene()
    scene.rooms.clear()
    doors = {
        index: Door(
            start=(2.0 * (index + 1), 0.5),
            end=(2.0 * (index + 1), 1.5),
            connecting_rooms=(index, index + 1),
            door_id=index,
            is_open=True,
            access_control=(True, True),
        )
        for index, is_open in enumerate(open_joins)
        if is_open
    }
    for room_id in range(len(open_joins) + 1):
        left, right = 2.0 * room_id, 2.0 * (room_id + 1)
        walls = [Wall((left, 0.0), (right, 0.0)), Wall((left, 2.0), (right, 2.0))]
        room_doors = []
        for index, x in ((room_id - 1, left), (room_id, right)):
            if index in doors:
                room_doors.append(doors[index])
                walls.extend([Wall((x, 0.0), (x, 0.5)), Wall((x, 1.5), (x, 2.0))])
            else:
                walls.append(Wall((x, 0.0), (x, 2.0)))
        scene.rooms.append(make_room(walls, room_id=room_id, doors=room_doors))
    return scene
