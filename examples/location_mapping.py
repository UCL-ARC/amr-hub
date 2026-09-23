"""Inspect model locations used by the event-location mapping workflow."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np

from amr_hub_abm.data_ingestion import build_synthetic_location_inputs
from amr_hub_abm.location_resolution import (
    DoorLocationResolution,
    RoomLocationResolution,
    resolve_door_location,
    resolve_room_location,
)
from amr_hub_abm.read_space_input import SpaceInputReader
from amr_hub_abm.spatial.room import Room

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse floorplan and canonical room selections."""
    parser = argparse.ArgumentParser(
        description="Inspect event-location targets in a loaded spatial model.",
    )
    parser.add_argument(
        "--space-yaml",
        type=Path,
        required=True,
        help="Building YAML consumed by SpaceInputReader.",
    )
    parser.add_argument(
        "--building",
        required=True,
        help="Canonical model building name.",
    )
    parser.add_argument(
        "--floor",
        type=int,
        required=True,
        help="Canonical model floor number.",
    )
    parser.add_argument(
        "--patient-room",
        required=True,
        help="Room code used for representative patient-event placement.",
    )
    parser.add_argument(
        "--door-room",
        required=True,
        help="Room code used for door-event placement.",
    )
    parser.add_argument(
        "--ambiguous-door-room",
        help="Optional room code expected to contain multiple candidate doors.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed supplied while loading model rooms (default: %(default)s).",
    )
    return parser.parse_args()


def load_model_rooms(space_yaml: Path, seed: int) -> list[Room]:
    """
    Load spatial model rooms from the standard building YAML.

    Parameters
    ----------
    space_yaml : pathlib.Path
        Building YAML consumed by the simulation spatial input reader.
    seed : int
        Seed for the random generator threaded through loaded rooms.

    Returns
    -------
    list[Room]
        Rooms created by ``SpaceInputReader``.

    """
    reader = SpaceInputReader(
        input_path=space_yaml,
        rng_generator=np.random.default_rng(seed),
    )
    return reader.rooms


def log_room_resolution(label: str, resolution: RoomLocationResolution) -> None:
    """Log one room-resolution outcome and its representative coordinate."""
    if resolution.location is None:
        logger.info("%s: %s", label, resolution.status)
        return
    logger.info(
        "%s: %s at (%.3f, %.3f)",
        label,
        resolution.status,
        resolution.location.x,
        resolution.location.y,
    )


def log_door_resolution(label: str, resolution: DoorLocationResolution) -> None:
    """Log one door-resolution outcome and available model details."""
    if resolution.location is None:
        logger.info(
            "%s: %s (%s candidate doors)",
            label,
            resolution.status,
            resolution.candidate_door_count,
        )
        return
    logger.info(
        "%s: %s, model door %s at (%.3f, %.3f)",
        label,
        resolution.status,
        resolution.door.door_id if resolution.door is not None else None,
        resolution.location.x,
        resolution.location.y,
    )


def main() -> None:
    """Load the configured model and report selected mapping targets."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("amr_hub_abm.read_space_input").setLevel(logging.WARNING)
    args = parse_args()
    rooms = load_model_rooms(args.space_yaml, args.seed)
    logger.info("Loaded %s model rooms from %s", len(rooms), args.space_yaml)
    synthetic_inputs = build_synthetic_location_inputs(
        building=args.building,
        floor=args.floor,
        patient_room=args.patient_room,
        door_room=args.door_room,
        ambiguous_door_room=args.ambiguous_door_room,
    )
    logger.info("Constructed %s synthetic source events", len(synthetic_inputs.events))

    patient_resolution = resolve_room_location(
        args.building,
        args.floor,
        args.patient_room,
        rooms,
    )
    log_room_resolution("Patient room", patient_resolution)

    door_resolution = resolve_door_location(
        args.building,
        args.floor,
        args.door_room,
        rooms,
    )
    log_door_resolution("Door room", door_resolution)

    if args.ambiguous_door_room is not None:
        ambiguous_resolution = resolve_door_location(
            args.building,
            args.floor,
            args.ambiguous_door_room,
            rooms,
        )
        log_door_resolution("Ambiguous door room", ambiguous_resolution)


if __name__ == "__main__":
    main()
