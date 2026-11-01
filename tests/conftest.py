import json
import pytest
from pathlib import Path
from typing import Callable, Any, Sequence
import random

# flow imports
from ruleflow.core.topologies.tooling.searcher import VectorRegexSearch, VectorSearch
from ruleflow.core.topologies.nd_space import SpaceState1D
from ruleflow.core.engine import Event


@pytest.fixture
def space_1d_factory() -> Callable[[Sequence[int]], SpaceState1D]:
    """
    Fixture to quickly generate 1D SpaceStates for isolated asm testing.
    Usage: space = space_1d_factory([65, 66, 67])
    """

    def _create(quanta: Sequence[int]) -> SpaceState1D:
        return SpaceState1D(quanta)

    return _create


@pytest.fixture
def snapshot_loader() -> Callable[[str], list[dict[str, Any]]]:
    """
    Loads human-verified JSON snapshots from the test_verified/snapshots directory.
    """

    def _load(filename: str) -> list[dict[str, Any]]:
        # Resolves path relative to this conftest.py file
        snapshot_dir = Path(__file__).parent / "test_verified" / "snapshots"
        file_path = snapshot_dir / filename

        if not file_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {file_path}")

        with open(file_path, "r") as f:
            return json.load(f)

    return _load


@pytest.fixture
def serialize_flow_events() -> Callable[[list[Event]], list[dict[str, Any]]]:
    """
    Serializes live engine events into a dictionary format that directly matches
    the JSON snapshot schema. This carefully avoids circular references
    (like parent_delta) while extracting vital causal data.
    """

    def _serialize(events: list[Event]) -> list[dict[str, Any]]:
        serialized = []
        for event in events:
            e_data = {
                "time": event.time,
                "inert": event.inert,
                "causal_distance": event.causal_distance_to_creation,
                # Convert the generator to a list for JSON serialization
                "causally_connected": list(event.causally_connected_events),
                "spaces": []
            }
            # Extract the raw vector data for comparison
            for space in event.spaces:
                # Assuming 1D SpaceState for our current asm implementations
                if isinstance(space, SpaceState1D):
                    e_data["spaces"].append([int(val) for val in space.vec.data.logical_data])

            serialized.append(e_data)
        return serialized

    return _serialize


@pytest.fixture
def base_rule_dependencies():
    """
    Provides standard searchers and a deterministic random engine for rule instantiation.
    Shared globally across implementation and interpreter tests.
    """
    return VectorRegexSearch(), VectorSearch(), random.Random(42)
