"""Tests for Labyrinth engine."""

from __future__ import annotations

import random

import pytest

from labyrinth.domain.entities import DNA, Raksha
from labyrinth.domain.types import CENTER_SQUARES, GeneType, TRIP_MAX_STEPS
from labyrinth.engine.labyrinth import DOMINANT_TRAP_RATIO, Labyrinth, TRAP_DENSITY
from uuid import uuid4


def _raksha(dominant: GeneType, secondary: GeneType = GeneType.WATER) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=secondary, recessive=GeneType.EARTH),
    )


class TestLabyrinthGeneration:
    def test_same_seed_same_grid(self, seeded_rng: random.Random) -> None:
        lab1 = Labyrinth.create(seeded_rng, dominant=GeneType.FIRE)
        rng2 = random.Random(42)
        lab2 = Labyrinth.create(rng2, dominant=GeneType.FIRE)
        assert lab1.grid == lab2.grid

    def test_center_squares_are_free(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        for pos in CENTER_SQUARES:
            assert lab.get_trap(*pos) is None

    def test_trap_density_and_dominant_ratio(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng, dominant=GeneType.FIRE)
        total = 100 * 100
        trapped = sum(1 for v in lab.grid.values() if v is not None)
        dominant_traps = sum(1 for v in lab.grid.values() if v == GeneType.FIRE)
        assert trapped == int(total * TRAP_DENSITY)
        assert dominant_traps == int(trapped * DOMINANT_TRAP_RATIO)
        assert trapped / total == pytest.approx(TRAP_DENSITY, abs=0.001)

    def test_grid_fixed_within_epoch(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        snapshot = dict(lab.grid)
        lab.tick_epoch()
        assert lab.grid == snapshot


class TestResolveTrap:
    def test_free_square_always_survives(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        r = _raksha(GeneType.FIRE)
        assert lab.resolve_trap(r, None, seeded_rng) is True

    def test_dominant_resistance_always_survives(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        r = _raksha(GeneType.FIRE)
        assert lab.resolve_trap(r, GeneType.FIRE, seeded_rng) is True

    def test_no_resistance_die_on_low_roll(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        r = _raksha(GeneType.FIRE, GeneType.WATER)

        class FixedRng:
            def random(self) -> float:
                return 0.1

        assert lab.resolve_trap(r, GeneType.EARTH, FixedRng()) is False

    def test_no_resistance_survive_on_high_roll(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        r = _raksha(GeneType.FIRE, GeneType.WATER)

        class FixedRng:
            def random(self) -> float:
                return 0.9

        assert lab.resolve_trap(r, GeneType.EARTH, FixedRng()) is True


class TestRunTrip:
    def test_naive_walk_respects_step_limit(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        r = _raksha(GeneType.FIRE)
        far_path = [(0, 0)] * (TRIP_MAX_STEPS + 50)
        result = lab.run_trip(r, seeded_rng, path=far_path)
        assert len(result.travelog.path) <= TRIP_MAX_STEPS

    def test_center_path_grants_soma(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng)
        r = _raksha(GeneType.FIRE)
        center = next(iter(CENTER_SQUARES))
        result = lab.run_trip(r, seeded_rng, path=[center])
        assert result.travelog.soma_gathered >= 1
        assert result.travelog.survived is True

    def test_step_limit_returns_alive(self, seeded_rng: random.Random) -> None:
        lab = Labyrinth.create(seeded_rng, dominant=GeneType.FIRE)
        r = _raksha(GeneType.FIRE)
        free_pos = next(
            (x, y)
            for x in range(100)
            for y in range(100)
            if lab.get_trap(x, y) is None and (x, y) not in CENTER_SQUARES
        )
        path = [free_pos] * TRIP_MAX_STEPS
        result = lab.run_trip(r, seeded_rng, path=path)
        assert result.travelog.hit_step_limit is True
        assert result.travelog.survived is True
        assert result.died is False
