"""Tests for persistence."""

from __future__ import annotations

from pathlib import Path

from labyrinth.domain.entities import Civilization, Epoch, TurnSummary
from labyrinth.persistence.repo import GameRepository


class TestGameRepository:
    def test_save_and_turn_count(self, tmp_db: Path) -> None:
        repo = GameRepository(tmp_db)
        repo.initialize()
        civ = Civilization(id="genbot", name="GenBot", soma=1000, rakshas=[])
        repo.create_game(5, [civ])
        summary = TurnSummary(
            turn_number=1,
            civilization_id="genbot",
            soma_start=1000,
            soma_end=950,
            pop_start=100,
            pop_end=95,
            deaths=5,
            trips_sent=70,
            trips_survived=60,
            soma_gathered=10,
            strategy_sumup="test",
        )
        from labyrinth.engine.turn import CivilizationState
        from labyrinth.strategy.gen_alg import GenAlgStrategy
        state = CivilizationState(civilization=civ, strategy=GenAlgStrategy())
        epoch = Epoch(dominant_type=__import__("labyrinth.domain.types", fromlist=["GeneType"]).GeneType.FIRE,
                      turns_remaining=5, length=5)
        repo.save_turn(1, epoch, [summary], [state])
        assert repo.turn_count() == 1

    def test_load_summaries_roundtrip(self, tmp_db: Path) -> None:
        repo = GameRepository(tmp_db)
        repo.initialize()
        civ = Civilization(id="genbot", name="GenBot", soma=1000, rakshas=[])
        repo.create_game(1, [civ])
        summary = TurnSummary(
            turn_number=1, civilization_id="genbot",
            soma_start=1000, soma_end=900, pop_start=100, pop_end=90,
            deaths=10, trips_sent=50, trips_survived=40, soma_gathered=5,
            strategy_sumup="harvest",
        )
        from labyrinth.engine.turn import CivilizationState
        from labyrinth.strategy.gen_alg import GenAlgStrategy
        from labyrinth.domain.types import GeneType
        state = CivilizationState(civilization=civ, strategy=GenAlgStrategy())
        epoch = Epoch(dominant_type=GeneType.FIRE, turns_remaining=5, length=5)
        repo.save_turn(1, epoch, [summary], [state])
        loaded = repo.load_summaries()
        assert len(loaded) == 1
        assert loaded[0].strategy_sumup == "harvest"

    def test_save_and_load_strategy_thinking(self, tmp_db: Path) -> None:
        from labyrinth.domain.types import GeneType
        from labyrinth.engine.turn import CivilizationState
        from labyrinth.strategy.gen_alg import GenAlgStrategy

        repo = GameRepository(tmp_db)
        repo.initialize()
        civ = Civilization(id="qwen", name="Qwen", soma=1000, rakshas=[])
        repo.create_game(1, [civ])
        summary = TurnSummary(
            turn_number=1, civilization_id="qwen",
            soma_start=1000, soma_end=900, pop_start=100, pop_end=90,
            deaths=10, trips_sent=50, trips_survived=40, soma_gathered=5,
            strategy_sumup="explore",
            strategy_thinking="Epoch shift soon — keep WATER genes.",
        )
        state = CivilizationState(civilization=civ, strategy=GenAlgStrategy())
        epoch = Epoch(dominant_type=GeneType.FIRE, turns_remaining=5, length=5)
        repo.save_turn(1, epoch, [summary], [state])
        loaded = repo.load_summaries()
        assert loaded[0].strategy_thinking == "Epoch shift soon — keep WATER genes."

    def test_save_and_load_extinction_fields(self, tmp_db: Path) -> None:
        from labyrinth.domain.entities import CivilizationStatus
        from labyrinth.domain.types import GeneType
        from labyrinth.engine.turn import CivilizationState
        from labyrinth.strategy.gen_alg import GenAlgStrategy

        repo = GameRepository(tmp_db)
        repo.initialize()
        civ = Civilization(
            id="genbot", name="GenBot", soma=1000, rakshas=[],
            status=CivilizationStatus.EXTINCT, extinct_turn=2,
        )
        repo.create_game(5, [civ])
        summary = TurnSummary(
            turn_number=2, civilization_id="genbot",
            soma_start=1000, soma_end=1000, pop_start=10, pop_end=0,
            deaths=10, trips_sent=5, trips_survived=0, soma_gathered=0,
            strategy_sumup="extinct", went_extinct=True,
        )
        state = CivilizationState(civilization=civ, strategy=GenAlgStrategy())
        epoch = Epoch(dominant_type=GeneType.FIRE, turns_remaining=3, length=5)
        repo.save_turn(2, epoch, [summary], [state])
        loaded = repo.load_summaries()
        assert loaded[0].went_extinct is True
        status, extinct_turn = repo.load_civilization_status("genbot")
        assert status == CivilizationStatus.EXTINCT
        assert extinct_turn == 2
