"""Shared pytest fixtures."""

from __future__ import annotations

import random
from pathlib import Path
from uuid import uuid4

import pytest

from labyrinth.domain.entities import Civilization, DNA, Raksha
from labyrinth.domain.types import GeneType
from labyrinth.logging_config import configure_logging


@pytest.fixture(scope="session", autouse=True)
def _configure_test_logging() -> None:
    configure_logging()


@pytest.fixture
def seeded_rng() -> random.Random:
    """Deterministic RNG for reproducible tests."""
    return random.Random(42)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Temporary SQLite database path."""
    return tmp_path / "game.db"


@pytest.fixture
def sample_raksha() -> Raksha:
    """Single alive Raksha with FIRE dominant gene."""
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(
            dominant=GeneType.FIRE,
            secondary=GeneType.WATER,
            recessive=GeneType.EARTH,
        ),
        alive=True,
        trips_completed=2,
        trips_survived=1,
    )


@pytest.fixture
def sample_civilization(sample_raksha: Raksha) -> Civilization:
    """Minimal civilization with one Raksha."""
    return Civilization(
        id="civ-1",
        name="TestCiv",
        soma=100,
        rakshas=[sample_raksha],
    )
