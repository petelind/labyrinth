"""Tests for weed logic."""

from __future__ import annotations

from uuid import uuid4

from labyrinth.domain.entities import Civilization, DNA, Raksha
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.engine.weed import apply_mandatory_kill, apply_weed, sustain_and_weed


def _raksha(
    dominant: GeneType,
    trips_survived: int = 0,
    trips_completed: int = 0,
    alive: bool = True,
) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=GeneType.WATER, recessive=GeneType.EARTH),
        alive=alive,
        trips_survived=trips_survived,
        trips_completed=trips_completed,
    )


class TestApplyWeed:
    def test_weed_kills_matching(self) -> None:
        earth = _raksha(GeneType.EARTH)
        fire = _raksha(GeneType.FIRE)
        civ = Civilization(id="civ-1", name="T", soma=100, rakshas=[earth, fire])
        criteria = [Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.EARTH)]
        killed = apply_weed(civ, criteria)
        assert len(killed) == 1
        assert earth.alive is False
        assert fire.alive is True


class TestMandatoryKill:
    def test_kills_lowest_value_first(self) -> None:
        low = _raksha(GeneType.FIRE, trips_survived=0, trips_completed=0)
        high = _raksha(GeneType.FIRE, trips_survived=5, trips_completed=10)
        civ = Civilization(id="civ-1", name="T", soma=1, rakshas=[low, high])
        killed = apply_mandatory_kill(civ, soma=1)
        assert low in killed
        assert high.alive is True

    def test_no_kill_when_sufficient_soma(self) -> None:
        r = _raksha(GeneType.FIRE)
        civ = Civilization(id="civ-1", name="T", soma=10, rakshas=[r])
        killed = apply_mandatory_kill(civ, soma=10)
        assert killed == []


class TestSustainAndWeed:
    def test_strategy_then_mandatory(self) -> None:
        r1 = _raksha(GeneType.EARTH)
        r2 = _raksha(GeneType.FIRE, trips_survived=0)
        r3 = _raksha(GeneType.FIRE, trips_survived=5)
        civ = Civilization(id="civ-1", name="T", soma=1, rakshas=[r1, r2, r3])
        criteria = [Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.EARTH)]
        killed = sustain_and_weed(civ, criteria, soma=1)
        assert r1.alive is False
        alive = [r for r in civ.rakshas if r.alive]
        assert len(alive) <= 1
