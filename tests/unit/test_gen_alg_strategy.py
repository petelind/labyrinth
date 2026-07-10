"""Tests for GenAlgStrategy."""

from __future__ import annotations

from uuid import uuid4

from labyrinth.domain.archetypes import all_archetype_dnas
from labyrinth.domain.entities import DNA, Raksha, Travelog, TurnContext
from labyrinth.domain.types import CriteriaField, CriteriaOp, GeneType
from labyrinth.game import _create_initial_rakshas
from labyrinth.strategy.gen_alg import GenAlgStrategy
import random


def _raksha(dominant: GeneType, secondary: GeneType = GeneType.WATER) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=secondary, recessive=GeneType.EARTH),
        alive=True,
    )


def _context(rakshas: list[Raksha], turn: int = 1, travelogs: list[Travelog] | None = None) -> TurnContext:
    return TurnContext(
        turn_number=turn,
        soma=1000,
        rakshas=rakshas,
        recent_travelogs=travelogs or [],
        known_map={},
        turns_remaining=19,
    )


class TestGenAlgStrategy:
    def test_turn_one_has_no_weed(self) -> None:
        rakshas = _create_initial_rakshas("civ-1", random.Random(42))
        strategy = GenAlgStrategy()
        strategy.set_deadline(__import__("time").time() + 180)
        strategy.decide(_context(rakshas))
        assert strategy.standing_orders.weed_criteria == []

    def test_scout_sends_archetype_cohort(self) -> None:
        rakshas = _create_initial_rakshas("civ-1", random.Random(42))
        strategy = GenAlgStrategy()
        ctx = _context(rakshas)
        selected = strategy.select_send_pool(rakshas, ctx)
        assert len(selected) == len(all_archetype_dnas())
        keys = {(r.dna.dominant, r.dna.secondary, r.dna.recessive) for r in selected}
        assert len(keys) == len(all_archetype_dnas())

    def test_harvest_caps_at_harvest_ratio(self) -> None:
        rakshas = [_raksha(GeneType.FIRE) for _ in range(50)]
        rakshas += [_raksha(GeneType.WATER) for _ in range(50)]
        fire = rakshas[0]
        logs = [Travelog(fire.id, [(0, 0)], {}, 5, True)]
        strategy = GenAlgStrategy()
        strategy._initial_scout_done = True
        strategy._survival_rates[GeneType.FIRE] = 1.0
        strategy._survival_rates[GeneType.WATER] = 0.0
        ctx = _context(rakshas, travelogs=logs, turn=2)
        selected = strategy.select_send_pool(rakshas, ctx)
        assert len(selected) == 8

    def test_mass_death_retriggers_scout(self) -> None:
        rakshas = [_raksha(GeneType.FIRE)]
        dead_log = Travelog(rakshas[0].id, [(0, 0)], {}, 0, False)
        strategy = GenAlgStrategy()
        strategy._initial_scout_done = True
        ctx = _context(rakshas, travelogs=[dead_log], turn=2)
        assert strategy._needs_scout(ctx) is True

    def test_repro_pairs_similar_dna(self) -> None:
        a = Raksha(
            id=uuid4(), civilization_id="civ-1", alive=True, trips_survived=2,
            dna=DNA(GeneType.FIRE, GeneType.WATER, GeneType.EARTH),
        )
        b = Raksha(
            id=uuid4(), civilization_id="civ-1", alive=True, trips_survived=1,
            dna=DNA(GeneType.FIRE, GeneType.WATER, GeneType.AIR),
        )
        c = Raksha(
            id=uuid4(), civilization_id="civ-1", alive=True, trips_survived=1,
            dna=DNA(GeneType.EARTH, GeneType.AIR, GeneType.WATER),
        )
        strategy = GenAlgStrategy()
        pairs = strategy.select_repro_pairs([a, b, c], _context([a, b, c]), random.Random(1))
        assert len(pairs) == 1
        assert {pairs[0][0].id, pairs[0][1].id} == {a.id, b.id}

    def test_strategy_sumup_has_no_oracle_epoch(self) -> None:
        rakshas = [_raksha(GeneType.FIRE) for _ in range(10)]
        strategy = GenAlgStrategy()
        strategy.set_deadline(__import__("time").time() + 180)
        strategy.decide(_context(rakshas))
        sumup = strategy.standing_orders.current_strategy_sumup
        assert "Epoch FIRE" not in sumup
