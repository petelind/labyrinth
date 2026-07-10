"""Tests for turn runner and game orchestration."""

from __future__ import annotations

from pathlib import Path

from labyrinth.domain.entities import GameEvents, StandingOrders
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp
from labyrinth.game import Game, GameConfig
from labyrinth.strategy.base import Strategy
from labyrinth.strategy.gen_alg import GenAlgStrategy


class PassiveStrategy(Strategy):
    """Strategy that issues no weed, send, or reproduce orders."""

    def decide(self, context) -> None:
        self.set_standing_orders(StandingOrders(
            last_updated_turn=context.turn_number,
            current_strategy_sumup="Hold.",
        ))


class SuicideStrategy(Strategy):
    """Weed all alive Rakshas to trigger extinction on turn 1."""

    def decide(self, context) -> None:
        self.set_standing_orders(StandingOrders(
            weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            last_updated_turn=context.turn_number,
        ))


class TestGame:
    def test_next_turn_produces_summaries(self, tmp_db: Path) -> None:
        events = GameEvents()
        fired: list[str] = []

        def on_turn_end(summaries):
            fired.append("turn_end")

        events.on_turn_end = on_turn_end
        game = Game.create(
            [("GenBot", GenAlgStrategy())],
            GameConfig(turns_total=2, db_path=tmp_db, seed=42),
            events=events,
        )
        summaries = game.next_turn()
        assert len(summaries) == 1
        assert summaries[0].turn_number == 1
        assert game.civilizations[0].civilization.soma == 2904
        assert summaries[0].trips_sent == 64
        assert summaries[0].trips_survived == 45
        assert fired == ["turn_end"]

    def test_run_all_completes_all_turns(self, tmp_db: Path) -> None:
        game = Game.create(
            [("GenBot", PassiveStrategy())],
            GameConfig(turns_total=3, db_path=tmp_db, seed=42),
        )
        all_summaries = game.run_all()
        assert len(all_summaries) == 3
        assert game.current_turn == 3
        assert game.finished

    def test_run_all_stops_early_when_all_extinct(self, tmp_db: Path) -> None:
        game = Game.create(
            [("GenBot", SuicideStrategy())],
            GameConfig(turns_total=3, db_path=tmp_db, seed=42),
        )
        all_summaries = game.run_all()
        assert game.finished
        assert game.current_turn == 1
        assert len(all_summaries) == 1
        assert all_summaries[0].went_extinct

    def test_two_civilizations_both_get_summaries(self, tmp_db: Path) -> None:
        game = Game.create(
            [("GenBot", PassiveStrategy()), ("GenBot2", PassiveStrategy())],
            GameConfig(turns_total=2, db_path=tmp_db, seed=42),
        )
        summaries = game.run_all()
        assert len(summaries) == 4
