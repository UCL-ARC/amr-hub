"""Tests for utility functions in the agent module."""

import logging

import numpy as np
import pytest

from amr_hub_abm.agent.agent import Agent
from amr_hub_abm.agent.enums import AgentType
from amr_hub_abm.agent.utils import add_agent_occupancy, remove_agent_occupancy
from amr_hub_abm.space.content import Content, ContentType
from amr_hub_abm.space.location import Location
from amr_hub_abm.space.room import Room
from amr_hub_abm.space.wall import Wall


@pytest.fixture
def square_room_walls() -> list[Wall]:
    """Create walls for a simple square room."""
    return [
        Wall(start=(0, 0), end=(0, 5)),
        Wall(start=(0, 5), end=(5, 5)),
        Wall(start=(5, 5), end=(5, 0)),
        Wall(start=(5, 0), end=(0, 0)),
    ]


@pytest.fixture
def sample_contents() -> list[Content]:
    """Create sample contents inside the test room."""
    return [
        Content(
            content_type=ContentType.CHAIR,
            location=Location(x=1.0, y=1.0, floor=1, building="Test Building"),
        ),
        Content(
            content_type=ContentType.WORKSTATION,
            location=Location(x=2.0, y=2.0, floor=1, building="Test Building"),
        ),
    ]


@pytest.fixture
def sample_room(square_room_walls: list[Wall], sample_contents: list[Content]) -> Room:
    """Create a room containing the sample contents."""
    return Room(
        room_id=1,
        name="Test Room",
        building="Test Building",
        floor=1,
        walls=square_room_walls,
        doors=[],
        contents=sample_contents,
        rng_generator=np.random.default_rng(42),
    )


@pytest.fixture
def sample_agent(sample_room: Room) -> Agent:
    """Create a sample agent located inside the test room."""
    return Agent(
        idx=1,
        location=Location(x=1.5, y=1.5, floor=1, building="Test Building"),
        heading_rad=0.0,
        rooms=[sample_room],
        rng_generator=np.random.default_rng(42),
    )


def test_remove_agent_occupancy_clears_matching_content(
    sample_agent: Agent,
    sample_room: Room,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test removing occupancy when the agent occupies content in the current room."""
    occupied_content = sample_room.contents[0]
    occupied_content.occupier_id = (sample_agent.idx, sample_agent.agent_type)
    sample_agent.stationary = True

    with caplog.at_level(logging.INFO):
        remove_agent_occupancy(sample_agent, current_time=12)

    assert occupied_content.occupier_id is None
    assert sample_agent.stationary is False
    assert "released content" in caplog.text
    assert sample_room.name in caplog.text


def test_remove_agent_occupancy_without_room_leaves_state_unchanged(
    sample_agent: Agent,
    sample_room: Room,
) -> None:
    """Test removing occupancy when the agent is not located in any tracked room."""
    occupied_content = sample_room.contents[0]
    occupied_content.occupier_id = (sample_agent.idx, sample_agent.agent_type)
    sample_agent.stationary = True
    sample_agent.rooms = []

    remove_agent_occupancy(sample_agent, current_time=12)

    assert occupied_content.occupier_id == (sample_agent.idx, sample_agent.agent_type)
    assert sample_agent.stationary is True


def test_remove_agent_occupancy_without_matching_content_leaves_state_unchanged(
    sample_agent: Agent, sample_room: Room, caplog: pytest.LogCaptureFixture
) -> None:
    """Test removing occupancy when no room content is occupied by the agent."""
    occupied_content = sample_room.contents[0]
    occupied_content.occupier_id = (999, AgentType.PATIENT)
    sample_agent.stationary = True

    with caplog.at_level(logging.INFO):
        remove_agent_occupancy(sample_agent, current_time=12)

    assert occupied_content.occupier_id == (999, AgentType.PATIENT)
    assert sample_agent.stationary is True
    assert "released content" not in caplog.text


def test_add_agent_occupancy_marks_content_and_logs_room_name(
    sample_agent: Agent, sample_room: Room, caplog: pytest.LogCaptureFixture
) -> None:
    """Test adding occupancy for content in the agent's current room."""
    target_content = sample_room.contents[1]

    with caplog.at_level(logging.INFO):
        add_agent_occupancy(sample_agent, target_content, current_time=25)

    assert target_content.occupier_id == (sample_agent.idx, sample_agent.agent_type)
    assert sample_agent.stationary is True
    assert "occupied content" in caplog.text
    assert sample_room.name in caplog.text


def test_add_agent_occupancy_logs_unknown_when_room_is_missing(
    sample_agent: Agent, sample_room: Room, caplog: pytest.LogCaptureFixture
) -> None:
    """Test adding occupancy when the agent cannot be matched to a room."""
    target_content = sample_room.contents[0]
    sample_agent.rooms = []

    with caplog.at_level(logging.INFO):
        add_agent_occupancy(sample_agent, target_content, current_time=30)

    assert target_content.occupier_id == (sample_agent.idx, sample_agent.agent_type)
    assert sample_agent.stationary is True
    assert "unknown" in caplog.text
