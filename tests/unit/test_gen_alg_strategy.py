"""Tests for GenAlgStrategy."""

from __future__ import annotations

import random
from uuid import uuid4

from labyrinth.domain.archetypes import all_archetype_dnas
from labyrinth.domain.entities import DNA, Epoch, Raksha, Travelog, TurnContext
from labyrinth.domain.types import CriteriaField, CriteriaOp, GeneType
from labyrinth.game import _create_initial_rakshas
from labyrinth.narrative import TurnChronicler
from labyrinth.strategy.gen_alg import GenAlgStrategy


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


class TestThinkingNarrative:
    """
    Red-phase tests for GenAlgStrategy thinking narrative.

    All tests verify that _build_thinking_narrative emits per-branch prose
    and that decide() routes it through record_thinking() on the chronicler.
    """

    def _make_chronicler(self, turn: int = 1) -> TurnChronicler:
        """Return a TurnChronicler ready to accept GenAlgStrategy records."""
        chronicler = TurnChronicler()
        chronicler.begin_turn(turn, 20, Epoch(GeneType.FIRE, 4, 20))
        chronicler.begin_civilization("AlgoBot", "GenAlg")
        return chronicler

    def _chapter_text(self, chronicler: TurnChronicler) -> str:
        return "\n".join(chronicler.civ_chapters[0].lines)

    # --- Happy-path: chronicler integration ---

    def test_thinking_recorded_to_chronicler(self) -> None:
        """decide() with an attached chronicler must produce 'Internal deliberation:'."""
        rakshas = [_raksha(GeneType.FIRE) for _ in range(20)]
        chronicler = self._make_chronicler(turn=1)
        strategy = GenAlgStrategy()
        strategy.set_deadline(__import__("time").time() + 180)
        ctx = TurnContext(
            turn_number=1, soma=1000, rakshas=rakshas,
            recent_travelogs=[], known_map={}, turns_remaining=19,
            chronicler=chronicler,
        )
        strategy.decide(ctx)
        assert "Internal deliberation:" in self._chapter_text(chronicler)

    # --- Branch coverage: _build_thinking_narrative ---

    def test_narrative_turn_one_says_scout(self) -> None:
        """Turn 1 narrative must mention Turn 1 and scout.

        Uses 80 rakshas (>= CONSERVATION_POP=70) so conservation mode does
        not pre-empt the turn-1 scout branch inside _needs_scout().
        """
        rakshas = [_raksha(GeneType.FIRE) for _ in range(80)]
        strategy = GenAlgStrategy()
        counts = strategy._count_by_gene(rakshas)
        ctx = TurnContext(
            turn_number=1, soma=1000, rakshas=rakshas,
            recent_travelogs=[], known_map={}, turns_remaining=19,
        )
        narrative = strategy._build_thinking_narrative(ctx, counts)
        assert "Turn 1" in narrative
        assert "scout" in narrative.lower()

    def test_narrative_harvest_mode(self) -> None:
        """After initial scout with healthy survival, narrative must say 'harvest'."""
        rakshas = [_raksha(GeneType.FIRE) for _ in range(80)]
        rakshas += [_raksha(GeneType.WATER) for _ in range(80)]
        logs = [Travelog(rakshas[0].id, [(0, 0)], {}, 5, True)]
        strategy = GenAlgStrategy()
        strategy._initial_scout_done = True
        counts = strategy._count_by_gene(rakshas)
        ctx = TurnContext(
            turn_number=2, soma=1000, rakshas=rakshas,
            recent_travelogs=logs, known_map={}, turns_remaining=19,
        )
        narrative = strategy._build_thinking_narrative(ctx, counts)
        assert "harvest" in narrative.lower()

    def test_narrative_conservation_mode_active(self) -> None:
        """Small population with many turns left activates conservation mode in narrative."""
        # alive=40 < CONSERVATION_POP=70, turns_remaining=20 > 15, no mass death
        rakshas = [_raksha(GeneType.FIRE) for _ in range(40)]
        strategy = GenAlgStrategy()
        strategy._initial_scout_done = True
        counts = strategy._count_by_gene(rakshas)
        ctx = TurnContext(
            turn_number=2, soma=1000, rakshas=rakshas,
            recent_travelogs=[], known_map={}, turns_remaining=20,
        )
        narrative = strategy._build_thinking_narrative(ctx, counts)
        assert "conservation mode active" in narrative.lower()

    def test_narrative_mass_death_rescout(self) -> None:
        """Zero survival from recent travelogs must trigger mass-death branch in narrative."""
        rakshas = [_raksha(GeneType.FIRE) for _ in range(80)]
        dead_logs = [Travelog(r.id, [(0, 0)], {}, 0, False) for r in rakshas[:4]]
        strategy = GenAlgStrategy()
        strategy._initial_scout_done = True
        counts = strategy._count_by_gene(rakshas)
        ctx = TurnContext(
            turn_number=2, soma=1000, rakshas=rakshas,
            recent_travelogs=dead_logs, known_map={}, turns_remaining=19,
        )
        narrative = strategy._build_thinking_narrative(ctx, counts)
        assert "mass death" in narrative.lower()

    def test_narrative_repro_paused_low_soma(self) -> None:
        """Soma below alive × REPRO_SOMA_FACTOR must say 'paused' in narrative."""
        # 80 rakshas, threshold = 80 * 1.05 = 84; soma=79 < 84
        rakshas = [_raksha(GeneType.FIRE) for _ in range(80)]
        strategy = GenAlgStrategy()
        counts = strategy._count_by_gene(rakshas)
        ctx = TurnContext(
            turn_number=1, soma=79, rakshas=rakshas,
            recent_travelogs=[], known_map={}, turns_remaining=19,
        )
        narrative = strategy._build_thinking_narrative(ctx, counts)
        assert "paused" in narrative.lower()

    def test_narrative_repro_enabled(self) -> None:
        """Soma well above alive × REPRO_SOMA_FACTOR must say 'enabled' in narrative."""
        rakshas = [_raksha(GeneType.FIRE) for _ in range(10)]
        strategy = GenAlgStrategy()
        counts = strategy._count_by_gene(rakshas)
        ctx = TurnContext(
            turn_number=1, soma=1000, rakshas=rakshas,
            recent_travelogs=[], known_map={}, turns_remaining=19,
        )
        narrative = strategy._build_thinking_narrative(ctx, counts)
        assert "enabled" in narrative.lower()

    # --- Edge case: no chronicler must not raise ---

    def test_narrative_no_chronicler_no_crash(self) -> None:
        """decide() without a chronicler must complete without raising."""
        rakshas = [_raksha(GeneType.FIRE) for _ in range(10)]
        strategy = GenAlgStrategy()
        strategy.set_deadline(__import__("time").time() + 180)
        ctx = TurnContext(
            turn_number=1, soma=1000, rakshas=rakshas,
            recent_travelogs=[], known_map={}, turns_remaining=19,
        )
        strategy.decide(ctx)
        assert strategy.standing_orders is not None
