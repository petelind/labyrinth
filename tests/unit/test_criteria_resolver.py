"""Tests for CriteriaResolver."""

from __future__ import annotations

from uuid import uuid4

import pytest

from labyrinth.domain.criteria import inherit_dna, resolve_criteria
from labyrinth.domain.entities import DNA, Raksha
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType


def _raksha(
    dominant: GeneType,
    secondary: GeneType = GeneType.WATER,
    recessive: GeneType = GeneType.EARTH,
    alive: bool = True,
    trips_completed: int = 0,
    trips_survived: int = 0,
) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=secondary, recessive=recessive),
        alive=alive,
        trips_completed=trips_completed,
        trips_survived=trips_survived,
    )


class TestResolveCriteria:
    def test_empty_criteria_matches_none_by_default(self) -> None:
        alive = _raksha(GeneType.FIRE)
        result = resolve_criteria([], [alive])
        assert result == []

    def test_empty_criteria_matches_all_alive_when_flag_set(self) -> None:
        alive = _raksha(GeneType.FIRE)
        dead = _raksha(GeneType.WATER, alive=False)
        result = resolve_criteria([], [alive, dead], match_all_alive_if_empty=True)
        assert result == [alive]

    def test_gene_dominant_eq(self) -> None:
        fire = _raksha(GeneType.FIRE)
        water = _raksha(GeneType.WATER)
        criteria = [Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE)]
        result = resolve_criteria(criteria, [fire, water])
        assert result == [fire]

    def test_trips_survived_lte(self) -> None:
        low = _raksha(GeneType.FIRE, trips_survived=1)
        high = _raksha(GeneType.FIRE, trips_survived=5)
        criteria = [Criterion(CriteriaField.TRIPS_SURVIVED, CriteriaOp.LTE, 1)]
        result = resolve_criteria(criteria, [low, high])
        assert result == [low]

    def test_and_logic_multiple_criteria(self) -> None:
        match = _raksha(GeneType.EARTH, trips_survived=0)
        wrong_gene = _raksha(GeneType.FIRE, trips_survived=0)
        wrong_trips = _raksha(GeneType.EARTH, trips_survived=3)
        criteria = [
            Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.EARTH),
            Criterion(CriteriaField.TRIPS_SURVIVED, CriteriaOp.LTE, 1),
        ]
        result = resolve_criteria(criteria, [match, wrong_gene, wrong_trips])
        assert result == [match]

    def test_alive_false_excluded(self) -> None:
        dead = _raksha(GeneType.FIRE, alive=False)
        criteria = [Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE)]
        result = resolve_criteria(criteria, [dead])
        assert result == []


class TestInheritDna:
    def test_child_has_three_distinct_genes_when_possible(self, seeded_rng) -> None:
        parent_a = _raksha(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        parent_b = _raksha(GeneType.AIR, GeneType.FIRE, GeneType.WATER)
        child = inherit_dna(parent_a, parent_b, seeded_rng, "civ-1")
        assert child.alive is True
        assert child.trips_completed == 0
        assert child.parent_a_id == parent_a.id
        assert child.parent_b_id == parent_b.id
        genes = {child.dna.dominant, child.dna.secondary, child.dna.recessive}
        assert len(genes) == 3

    def test_deterministic_with_seeded_rng(self, seeded_rng) -> None:
        parent_a = _raksha(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        parent_b = _raksha(GeneType.AIR, GeneType.FIRE, GeneType.WATER)
        child1 = inherit_dna(parent_a, parent_b, seeded_rng, "civ-1")
        seeded_rng2 = __import__("random").Random(42)
        child2 = inherit_dna(parent_a, parent_b, seeded_rng2, "civ-1")
        assert child1.dna == child2.dna
