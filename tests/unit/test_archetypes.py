"""Tests for DNA archetype helpers."""

from __future__ import annotations

import random

from labyrinth.domain.archetypes import (
    ARCHETYPE_COHORT_SIZE,
    INITIAL_RAKSHAS,
    STRAY_COUNT,
    all_archetype_dnas,
    archetype_similarity,
)
from labyrinth.domain.entities import DNA
from labyrinth.domain.types import GeneType
from labyrinth.game import _create_initial_rakshas


class TestArchetypes:
    def test_full_archetype_grid_is_64(self) -> None:
        assert len(all_archetype_dnas()) == 64

    def test_initial_population_96_plus_4_strays(self) -> None:
        rakshas = _create_initial_rakshas("civ-1", random.Random(42))
        assert len(rakshas) == INITIAL_RAKSHAS
        assert INITIAL_RAKSHAS == ARCHETYPE_COHORT_SIZE + STRAY_COUNT

    def test_similarity_scores_match(self) -> None:
        a = DNA(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        b = DNA(GeneType.FIRE, GeneType.WATER, GeneType.AIR)
        c = DNA(GeneType.EARTH, GeneType.AIR, GeneType.WATER)
        assert archetype_similarity(a, b) == 2
        assert archetype_similarity(a, c) == 0
