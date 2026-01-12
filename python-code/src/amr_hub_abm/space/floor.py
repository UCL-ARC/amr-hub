"""Module for Floor class."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from amr_hub_abm.agent import Agent


@dataclass
class Floor:
    """Representation of a floor in a building."""

    floor_number: int
    rooms: list[Room]
    pseudo_rooms: list[Room] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        """Post-initialization to validate floor attributes."""
        room_ids = [room.room_id for room in self.rooms]
        if len(room_ids) != len(set(room_ids)):
            msg = f"Duplicate room IDs found on floor {self.floor_number}."
            raise InvalidRoomError(msg)

    @property
    def room_ids(self) -> list[int]:
        """Get a list of room IDs on the floor."""
        return sorted([room.room_id for room in self.rooms])

    @property
    def room_names(self) -> list[str]:
        """Get a list of room names on the floor."""
        id_name_map = {room.room_id: room.name for room in self.rooms}
        return [id_name_map[room_id] for room_id in self.room_ids]

    @property
    def edge_set(self) -> set[tuple[int, int]]:
        """Get a list of all wall edges on the floor."""
        edges = set()
        for room in self.rooms:
            for door in room.doors:
                edges.add(door.connecting_rooms)
                edges.add((door.connecting_rooms[1], door.connecting_rooms[0]))
        return edges

    @property
    def adjacency_matrix(self) -> np.ndarray:
        """Get the adjacency matrix representing room connections on the floor."""
        n = len(self.rooms)
        room_id_to_index = {
            room_id: index for index, room_id in enumerate(self.room_ids)
        }
        adjacency_matrix = np.zeros((n, n), dtype=int)

        for edge in self.edge_set:
            room1, room2 = edge
            index1 = room_id_to_index[room1]
            index2 = room_id_to_index[room2]
            adjacency_matrix[index1, index2] = 1

        return adjacency_matrix

    def plot(self, ax: Axes, agents: list[Agent] | None = None) -> None:
        """Plot the floor layout including rooms and doors."""
        for room in self.rooms:
            room.plot(ax=ax, agents=agents)

    def add_pseudo_rooms(self) -> None:
        """Add pseudo-rooms to the floor."""
        for existing_room in self.rooms:
            if not existing_room.walls:
                pseudo_room = Floor.create_spatial_room_from_pseudo_room(existing_room)
                self.pseudo_rooms.append(pseudo_room)

    @staticmethod
    def create_spatial_room_from_pseudo_room(room: Room) -> Room:
        """Create a spatial room from a pseudo-room based on area."""
        if not room.area or room.area <= 0:
            msg = "Pseudo-room must have a valid positive area."
            raise InvalidRoomError(msg)
        length = max(room.area**0.5, 2 * len(room.doors) + 2)
        width = room.area / length

        pseudo_doors = room.doors.copy()
        for count, door in enumerate(pseudo_doors):
            door.start = (2 * count + 1, width)
            door.end = (2 * count + 2, width)

        pseudo_walls = [
            Wall((0, width), (0, 0)),
            Wall((0, 0), (length, 0)),
            Wall((length, 0), (length, width)),
        ]

        doorside_walls = [
            Wall((2 * count, width), (2 * count + 1, width))
            for count in range(len(pseudo_doors))
        ]
        doorside_walls.append(Wall((len(pseudo_doors) * 2, width), (length, width)))
        pseudo_walls.extend(doorside_walls)

        return Room(
            room_id=room.room_id,
            name=room.name,
            building=room.building,
            floor=room.floor,
            walls=pseudo_walls,
            doors=pseudo_doors,
            contents=room.contents,
        )

    def find_room_by_location(self, location: tuple[float, float]) -> Room | None:
        """Find the room that contains the given location."""
        for room in self.rooms:
            if room.walls and room.contains_point(location):
                return room
        return None
