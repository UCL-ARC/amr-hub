"""Module for testing the simulation factory."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from amr_hub_abm.agent.kinematics import AgentKinematicsConfig, MovementStrategy
from amr_hub_abm.agent.needs_policy import NeedRule, NeedsPolicy
from amr_hub_abm.config import sim_config
from amr_hub_abm.exceptions import InvalidDefinitionError, SimulationModeError
from amr_hub_abm.simulation_factory import create_simulation, parse_location_timeseries
from amr_hub_abm.spatial.room import Room
from amr_hub_abm.task.task import TaskProgress, TaskSource
from amr_hub_abm.task.task_need import TaskNeed


def test_successful_simulation_creation() -> None:
    """Test successful creation of a simulation instance."""
    simulation = create_simulation(sim_config)
    assert simulation is not None
    tasks = [task for agent in simulation.agents for task in agent.tasks]
    assert tasks
    assert all(task.source == TaskSource.LOCATION_DATA for task in tasks)


def test_factory_enables_configured_needs_policy() -> None:
    """Parse and attach opt-in policy from the actual simulation configuration."""
    rule = {"threshold": 0.5, "urgent_threshold": 0.9, "duration": 3, "priority": 5}
    policy = {
        "enabled": True,
        "eating_room": {
            "building": "Sample Hospital",
            "floor": 0,
            "name": "Restaurant",
        },
        "travel_timeout": 100,
        "retry_interval": 10,
        "fatigue": rule,
        "hunger": rule,
        "toilet_need": rule,
    }
    config = replace(
        sim_config, config_data={**sim_config.config_data, "needs_policy": policy}
    )
    simulation = create_simulation(config)
    assert simulation.needs_policy is not None
    assert all(agent.retry_data_tasks for agent in simulation.agents)

    policy["eating_room"] = {"building": "Sample Hospital", "floor": 0, "name": "X"}
    with pytest.raises(InvalidDefinitionError, match="eating room"):
        create_simulation(config)


@pytest.mark.parametrize("use_gpu", [False, True])
@pytest.mark.parametrize(
    ("need", "room_name"), [("hunger", "Restaurant"), ("toilet_need", "WC")]
)
def test_hcw_can_reach_facilities_via_doors(
    use_gpu: bool,  # noqa: FBT001
    need: str,
    room_name: str,
) -> None:
    """An HCW reaches a sample facility via the corridor."""
    if use_gpu:
        import warp as wp  # noqa: PLC0415

        if not wp.is_cuda_available():
            pytest.skip("CUDA device is not available")
    simulation = create_simulation(sim_config, use_gpu=use_gpu)
    worker = next(agent for agent in simulation.agents if agent.tasks)
    simulation.agents[:] = [worker]
    simulation.internal_state_config = None
    worker.tasks.clear()
    setattr(worker.internal_state, need, 0.9)
    worker.movement_speed = 0.2
    worker.base_movement_speed = 0.2
    worker.movement_strategy = MovementStrategy.FIXED
    worker.stochasticity = 0
    worker.retry_data_tasks = True
    rule = NeedRule(0.5, 0.9, 2, 1)
    simulation.needs_policy = NeedsPolicy(
        fatigue=rule,
        hunger=rule,
        toilet_need=rule,
        eating_building="Sample Hospital",
        eating_floor=0,
        eating_room="Restaurant",
        travel_timeout=200,
        retry_interval=10,
    )
    task = None
    for _ in range(150):
        simulation.step()
        if task is None:
            task = next(
                (task for task in worker.tasks if isinstance(task, TaskNeed)), None
            )
        if getattr(worker.internal_state, need) == 0:
            break
    assert task is not None
    assert task.progress == TaskProgress.COMPLETED
    assert getattr(worker.internal_state, need) == 0
    assert simulation.spatial_engine.get_room(worker).name == room_name


@pytest.fixture
def sample_room() -> Room:
    """Create a sample Room for testing."""
    return Room(
        room_id=101,
        name="Room101",
        building="BuildingA",
        floor=1,
        contents=[],
        doors=[],
        walls=[],
        area=100.0,
        rng_generator=np.random.default_rng(),
    )


@pytest.fixture
def location_timeseries_df() -> pd.DataFrame:
    """Create a sample location timeseries DataFrame for testing."""
    return pd.DataFrame(
        {
            "hcw_id": [1],
            "timestamp": ["2023-01-01 08:00:00"],
            "location": ["BuildingA:1:Room101"],
            "patient_id": ["-"],
            "event_type": ["attend_patient"],
            "door_id": ["-"],
        }
    )


def test_missing_patient_id_in_location_timeseries(
    sample_room: Room, location_timeseries_df: pd.DataFrame
) -> None:
    """Test that error is raised for a missing patient ID in location timeseries."""
    df = location_timeseries_df.copy()
    with pytest.raises(SimulationModeError) as exc_info:
        parse_location_timeseries(
            timeseries_data=df,
            rooms=[sample_room],
            start_time=pd.Timestamp("2023-01-01 08:00:00"),
            total_time_steps=4,
            time_scaling_factor=60,
            rng_generator=np.random.default_rng(),
            agent_kinematics=AgentKinematicsConfig(
                movement_speed=0.001,
                stochasticity=0.0,
                interaction_radius=0.01,
                max_movement_attempts=5,
            ),
            task_durations=sim_config.task_durations,
        )

    assert "Patient ID must be provided" in str(exc_info.value)


def test_location_timeseries_invalid_event_type(
    sample_room: Room, location_timeseries_df: pd.DataFrame
) -> None:
    """Test that error is raised for an invalid event type in location timeseries."""
    df = location_timeseries_df.copy()
    df.loc[0, "event_type"] = "invalid_event"

    with pytest.raises(SimulationModeError) as exc_info:
        parse_location_timeseries(
            timeseries_data=df,
            rooms=[sample_room],
            start_time=pd.Timestamp("2023-01-01 08:00:00"),
            total_time_steps=4,
            time_scaling_factor=60,
            rng_generator=np.random.default_rng(),
            agent_kinematics=AgentKinematicsConfig(
                movement_speed=0.001,
                stochasticity=0.0,
                interaction_radius=0.01,
                max_movement_attempts=5,
            ),
            task_durations=sim_config.task_durations,
        )

    assert "Unknown event type" in str(exc_info.value)
