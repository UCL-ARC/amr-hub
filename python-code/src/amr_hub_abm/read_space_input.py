"""Module to import space input data for the AMR Hub ABM simulation."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import]

from amr_hub_abm.space.building import Building
from amr_hub_abm.space.door import Door
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SpaceInputReader:
    """Class to read space input data from a YAML file."""

    input_path: Path
    data: dict = field(init=False)

    door_list: list[Door] = field(init=False, default_factory=list)
    wall_list: list[Wall] = field(init=False, default_factory=list)

    rooms: list[Room] = field(init=False, default_factory=list)
    floors: list[Floor] = field(init=False, default_factory=list)
    buildings: list[Building] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        """Post-initialization to read and validate the YAML file."""
        self.validation()
        self.create_rooms_from_data()

    def create_rooms_from_data(self) -> None:
        """Create Room instances from the validated data."""
        room_counter = 0

        for building_data in [self.data["building"]]:
            for floor_data in building_data["floors"]:
                for room_data in floor_data["rooms"]:
                    room = self.create_room(
                        room_data,
                        room_counter,
                        building_data["name"],
                        floor_data["level"],
                    )
                    msg = f"Created room: {room.name}"
                    logger.info(msg)
                    self.rooms.append(room)
                    room_counter += 1

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
        room_doors: list[Door] = []
        for door_data in room_data.get("doors", []):
            door = Door(
                door_id=-1,
                open=False,
                connecting_rooms=(-1, -1),
                access_control=(False, False),
                start=(door_data[0], door_data[1]),
                end=(door_data[2], door_data[3]),
            )
            self.door_list.append(door)
            room_doors.append(door)

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
            raise ValueError(msg)

        if not topological and "walls" not in room_data:
            msg = "A non-topological room must have walls defined."
            logger.error(msg)
            raise KeyError(msg)

        if not topological:
            walls: list[Wall] = []
            walls_data: list[list[float]] = room_data["walls"]
            for wall in walls_data:
                if len(wall) != 4:  # noqa: PLR2004
                    msg = (
                        "Each wall must be defined by 4 coordinates: [x1, y1, x2, y2]."
                    )
                    logger.error(msg)
                    raise ValueError(msg)
                walls.append(Wall(start=(wall[0], wall[1]), end=(wall[2], wall[3])))

            msg = f"Room '{room_data['name']}' walls validated successfully."
            logger.info(msg)

            doors: list[Door] = []
            doors_data: list[list[float]] = room_data["doors"]
            for door in doors_data:
                if len(door) != 4:  # noqa: PLR2004
                    msg = (
                        "Each door must be defined by 4 coordinates: [x1, y1, x2, y2]."
                    )
                    logger.error(msg)
                    raise ValueError(msg)
                doors.append(
                    Door(
                        door_id=-1,
                        open=False,
                        connecting_rooms=(-1, -1),
                        access_control=(False, False),
                        start=(door[0], door[1]),
                        end=(door[2], door[3]),
                    )
                )

        else:
            msg = "Topological room validation is not yet implemented."
            raise NotImplementedError(msg)


if __name__ == "__main__":
    # Example usage
    reader = SpaceInputReader(input_path=Path("sample_floor_spatial.yml"))
    logger.info(reader.data)
