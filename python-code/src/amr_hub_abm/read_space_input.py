"""Module to import space input data for the AMR Hub ABM simulation."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import]

from amr_hub_abm.exceptions import (
    InvalidDefinitionError,
    InvalidDoorError,
    InvalidRoomError,
)
from amr_hub_abm.space.building import Building
from amr_hub_abm.space.door import DetachedDoor, Door
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SpaceInputReader:
    """Class to read space input data from a YAML file."""

    input_path: Path
    data: dict = field(init=False)

    door_list: list[Door] = field(init=False, default_factory=list)
    wall_list: list[Wall] = field(init=False, default_factory=list)

    room_door_dict: dict[str, list[DetachedDoor]] = field(
        init=False, default_factory=dict
    )

    rooms: list[Room] = field(init=False, default_factory=list)
    buildings: list[Building] = field(init=False, default_factory=list)

    topological: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """Post-initialization to read and validate the YAML file."""
        self.validation()
        self.get_room_name_dict()
        self.create_doors_from_detatched_doors()
        self.create_rooms_from_data()

        for room in self.rooms:
            msg = f"Room '{room.name} (id {room.room_id})' created."
            logger.info(msg)

        self.buildings = self.organise_rooms_into_floors_and_buildings(self.rooms)

    def get_room_name_dict(self) -> None:
        """Extract room names and their corresponding detatched doors."""
        for building_data in [self.data["building"]]:
            for floor_data in building_data["floors"]:
                for room_data in floor_data["rooms"]:
                    self.topological = "area" in room_data
                    room_name = room_data["name"]
                    doors: list[DetachedDoor] = []

                    if not self.topological:
                        for door_data in room_data.get("doors", []):
                            door = DetachedDoor(
                                is_open=False,
                                access_control=(False, False),
                                start=(door_data[0], door_data[1]),
                                end=(door_data[2], door_data[3]),
                            )
                            doors.append(door)
                        self.room_door_dict[room_name] = doors

                    else:
                        for door_name in room_data.get("doors", []):
                            door = DetachedDoor(
                                is_open=False,
                                access_control=(False, False),
                                name=door_name,
                            )
                            doors.append(door)
                        self.room_door_dict[room_name] = doors

    def create_doors_from_detatched_doors(self) -> None:
        """Create Door instances from detatched doors."""
        detatced_door_list = [
            door for doors in self.room_door_dict.values() for door in doors
        ]
        unique_detatched_doors = set(detatced_door_list)
        sorted_unique_detatched_doors = sorted(
            unique_detatched_doors, key=lambda d: (d.start, d.end)
        )

        sorted_room_names = sorted(room_name for room_name in self.room_door_dict)

        for detatched_door in sorted_unique_detatched_doors:
            connecting_rooms = [
                sorted_room_names.index(room_name)
                for room_name, doors in self.room_door_dict.items()
                if detatched_door in doors
            ]

            if len(connecting_rooms) != 2:
                msg = (
                    f"Door at {detatched_door.start}-{detatched_door.end} must connect "
                    f"exactly two rooms. Found {len(connecting_rooms)}."
                )
                logger.error(msg)
                raise InvalidDoorError(msg)

            if self.topological:
                door = Door(
                    is_open=detatched_door.is_open,
                    access_control=detatched_door.access_control,
                    name=detatched_door.name,
                    connecting_rooms=(connecting_rooms[0], connecting_rooms[1]),
                    door_id=sorted_unique_detatched_doors.index(detatched_door),
                )
            else:
                door = Door(
                    is_open=detatched_door.is_open,
                    access_control=detatched_door.access_control,
                    start=detatched_door.start,
                    end=detatched_door.end,
                    connecting_rooms=(connecting_rooms[0], connecting_rooms[1]),
                    door_id=sorted_unique_detatched_doors.index(detatched_door),
                )

            self.door_list.append(door)

    @staticmethod
    def organise_rooms_into_floors_and_buildings(rooms: list[Room]) -> list[Building]:
        """Organize rooms into floors and buildings."""
        all_buildings = {room.building for room in rooms}
        buildings: list[Building] = []
        for building_name in all_buildings:
            building_rooms = [room for room in rooms if room.building == building_name]
            all_floors = {room.floor for room in building_rooms}
            floors: list[Floor] = []
            for floor_number in all_floors:
                floor_rooms = [
                    room for room in building_rooms if room.floor == floor_number
                ]
                floor = Floor(floor_number=floor_number, rooms=floor_rooms)
                msg = (
                    f"Floor {floor.floor_number} created with {len(floor.rooms)} rooms."
                )
                logger.info(msg)
                floors.append(floor)
            building = Building(name=building_name, floors=floors)
            msg = f"Building '{building.name}' created with {len(floors)} floors."
            logger.info(msg)
            buildings.append(building)

        return buildings

    def create_rooms_from_data(self) -> None:
        """Create Room instances from the validated data."""
        sorted_room_names = sorted(room_name for room_name in self.room_door_dict)

        for index, name in enumerate(sorted_room_names):
            for building_data in [self.data["building"]]:
                for floor_data in building_data["floors"]:
                    floor_level = floor_data["level"]
                    for room_data in floor_data["rooms"]:
                        if room_data["name"] == name:
                            room = self.create_room(
                                room_data, index, building_data["name"], floor_level
                            )
                            self.rooms.append(room)

    def validation(self) -> None:
        """Validate the space input data from the YAML file."""
        with self.input_path.open("r", encoding="utf-8") as file:
            self.data = yaml.safe_load(file)

        msg = f"Loaded space input data from {self.input_path}"
        logger.info(msg)

        if "building" not in self.data:
            msg = "The input data must contain a 'building' key."
            logger.error(msg)
            raise KeyError(msg)

        building_data = self.data["building"]
        self.validate_building_data(building_data)

        floors_data = building_data["floors"]
        for floor_data in floors_data:
            self.validate_floor_data(floor_data)
            rooms_data = floor_data["rooms"]
            for room_data in rooms_data:
                self.validate_room_data(room_data)

    def create_room(
        self, room_data: dict, room_id: int, building_name: str, floor_level: int
    ) -> Room:
        """Create a Room instance from room data."""
        if self.topological:
            return self.create_topological_room(
                room_data, room_id, building_name, floor_level
            )
        return self.create_spatial_room(room_data, room_id, building_name, floor_level)

    def create_topological_room(
        self, room_data: dict, room_id: int, building_name: str, floor_level: int
    ) -> Room:
        """Create a topological Room instance from room data."""
        room_doors = [
            door for door in self.door_list if door.name in room_data["doors"]
        ]

        return Room(
            room_id=room_id,
            name=room_data["name"],
            building=building_name,
            floor=floor_level,
            walls=None,
            doors=room_doors,
            contents=room_data.get("contents", []),
            area=room_data["area"],
        )

    def create_spatial_room(
        self, room_data: dict, room_id: int, building_name: str, floor_level: int
    ) -> Room:
        """Create a spatial Room instance from room data."""
        room_doors = [
            door for door in self.door_list if room_id in door.connecting_rooms
        ]

        room_walls: list[Wall] = []
        for wall_data in room_data.get("walls", []):
            wall = Wall(
                start=(wall_data[0], wall_data[1]),
                end=(wall_data[2], wall_data[3]),
            )
            self.wall_list.append(wall)
            room_walls.append(wall)

        return Room(
            room_id=room_id,
            name=room_data["name"],
            building=building_name,
            floor=floor_level,
            walls=room_walls,
            doors=room_doors,
            contents=room_data.get("contents", []),
        )

    @staticmethod
    def validate_building_data(building_data: dict) -> None:
        """Validate the building data structure."""
        if "name" not in building_data:
            msg = "The 'building' data must contain a 'name' key."
            logger.error(msg)
            raise KeyError(msg)

        if "address" not in building_data:
            msg = "The 'building' data must contain an 'address' key."
            logger.error(msg)
            raise KeyError(msg)

        if "floors" not in building_data:
            msg = "The 'building' data must contain a 'floors' key."
            logger.error(msg)
            raise KeyError(msg)

    @staticmethod
    def validate_floor_data(floor_data: dict) -> None:
        """Validate the floor data structure."""
        if "level" not in floor_data:
            msg = "Each floor must have a 'level' defined."
            logger.error(msg)
            raise KeyError(msg)

        if "rooms" not in floor_data:
            msg = "Each floor must contain a 'rooms' key."
            logger.error(msg)
            raise KeyError(msg)

    @staticmethod
    def validate_room_data(room_data: dict) -> None:
        """Validate the room data structure."""
        if "name" not in room_data:
            msg = "Each room must have a 'name' defined."
            logger.error(msg)
            raise KeyError(msg)

        if "doors" not in room_data:
            msg = "Each room must have a 'doors' key."
            logger.error(msg)
            raise KeyError(msg)

        if "walls" not in room_data and "area" not in room_data:
            msg = "Each room must have either 'walls' or 'area' defined."
            logger.error(msg)
            raise KeyError(msg)

        topological = room_data.get("area", False)

        if topological and "walls" in room_data:
            msg = "A topological room cannot have walls defined."
            logger.error(msg)
            raise KeyError(msg)

        if not topological:
            walls: list[Wall] = []
            walls_data: list[list[float]] = room_data["walls"]
            for wall in walls_data:
                SpaceInputReader.check_tuple_length(wall, 4, "wall")
                walls.append(Wall(start=(wall[0], wall[1]), end=(wall[2], wall[3])))

            msg = f"Room '{room_data['name']}' walls validated successfully."
            logger.info(msg)

            doors_data: list[list[float]] = room_data["doors"]
            for door in doors_data:
                SpaceInputReader.check_tuple_length(door, 4, "door")

        else:
            doors_names: list[str] = room_data["doors"]
            for name in doors_names:
                if not isinstance(name, str):
                    msg = "In topological mode, doors must be defined by their names."
                    logger.error(msg)
                    raise InvalidDoorError(msg)

    @staticmethod
    def check_tuple_length(
        data_tuple: list[float], expected_length: int, data_type: str
    ) -> None:
        """Check if a data tuple has the expected length."""
        if data_type not in {"wall", "door"}:
            msg = f"data_type must be either 'wall' or 'door'. Got '{data_type}'."
            raise InvalidDefinitionError(msg)

        if len(data_tuple) != expected_length:
            msg = f"Each {data_type} must be defined by {expected_length} values."
            logger.error(msg)
            if data_type == "wall":
                raise InvalidRoomError(msg)
            raise InvalidDoorError(msg)
