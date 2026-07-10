"""Tests for reproduce logic."""

from __future__ import annotations

import random
from uuid import uuid4

from labyrinth.domain.entities import Civilization, DNA, Raksha
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.engine.reproduce import apply_reproduce


def _raksha(dominant: GeneType) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=GeneType.WATER, recessive=GeneType.EARTH),
    )


class TestApplyReproduce:
    def test_pairs_and_creates_children(self, seeded_rng: random.Random) -> None:
        pool = [_raksha(GeneType.FIRE), _raksha(GeneType.WATER), _raksha(GeneType.EARTH)]
        civ = Civilization(id="civ-1", name="T", soma=100, rakshas=pool)
        criteria = [Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)]
        children = apply_reproduce(civ, criteria, seeded_rng)
        assert len(children) == 1
        assert len(civ.rakshas) == 4

    def test_odd_one_out_skipped(self, seeded_rng: random.Random) -> None:
        pool = [_raksha(GeneType.FIRE), _raksha(GeneType.WATER), _raksha(GeneType.EARTH)]
        civ = Civilization(id="civ-1", name="T", soma=100, rakshas=pool)
        criteria = [Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)]
        children = apply_reproduce(civ, criteria, seeded_rng)
        assert len(children) == 1

    def test_insufficient_pool_returns_empty(self, seeded_rng: random.Random) -> None:
        civ = Civilization(id="civ-1", name="T", soma=100, rakshas=[_raksha(GeneType.FIRE)])
        children = apply_reproduce(civ, [], seeded_rng)
        assert children == []
