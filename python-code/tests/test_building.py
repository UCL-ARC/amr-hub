"""Tests for the Building class."""

import matplotlib.pyplot as plt

from amr_hub_abm.space.building import Building
from amr_hub_abm.space.floor import Floor
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall


def test_building_plotting() -> None:
    """Test plotting a building with no floors."""
    building = Building(name="Test Building", floors=[])
    # Since there are no floors, plotting should not raise an error
    building.plot_building(axes=[])
    # Test passes if no exception is raised


def test_building_with_one_floor() -> None:
    """Test plotting a building with one floor."""
    # Create a simple room with walls
    walls = [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]

    room = Room(
        room_id=1,
        name="Test Room",
        building="Test Building",
        floor=1,
        walls=walls,
        doors=[],
        contents=[],
    )

    floor = Floor(floor_number=1, rooms=[room])
    building = Building(name="Test Building", floors=[floor])

    # Create axes for plotting
    fig, ax = plt.subplots()
    building.plot_building(axes=[ax])
    plt.close(fig)  # Close the plot to avoid displaying during tests

    # Verify building structure
    assert len(building.floors) == 1
    assert building.floors[0].floor_number == 1
    assert len(building.floors[0].rooms) == 1
