"""Module for Floor class."""

from dataclasses import dataclass

import numpy as np

from amr_hub_abm.exceptions import InvalidRoomError
from amr_hub_abm.space.room import Room


@dataclass
class Floor:
    """Representation of a floor in a building."""

    floor_number: int
    rooms: list[Room]

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
