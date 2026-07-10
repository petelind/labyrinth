"""Tests for Game orchestration."""

from __future__ import annotations

from labyrinth.domain.entities import SquareRecord, StandingOrders, TurnContext
from labyrinth.domain.types import GeneType
from labyrinth.game import Game, GameConfig
from labyrinth.strategy.base import Strategy


class _NullStrategy(Strategy):
    """Strategy that sends no Rakshas and does not mutate standing orders."""

    def decide(self, context: TurnContext) -> None:
        """No-op: orders are pre-set for the current turn."""
        pass


class TestKnownMapClearedOnEpochAdvance:
    """known_map must reset when the labyrinth advances to a new epoch."""

    def test_known_map_cleared_when_epoch_advances(self) -> None:
        """
        Stale map knowledge from the previous epoch must not survive epoch change.

        :raises AssertionError: If known_map is not cleared after tick_epoch advances.
        """
        strategy = _NullStrategy()
        strategy.set_standing_orders(
            StandingOrders(
                send_criteria=[],
                current_strategy_sumup="Test: send nobody.",
                last_updated_turn=1,
            ),
        )
        game = Game.create(
            [("Bot", strategy)],
            GameConfig(turns_total=5, seed=42, thinking_seconds=0.1),
        )
        civ = game.civilizations[0].civilization
        sentinel = (1, 1)
        civ.known_map[sentinel] = SquareRecord(
            x=1,
            y=1,
            trap_type=GeneType.FIRE,
            is_center=False,
        )

        assert game.labyrinth.current_epoch is not None
        game.labyrinth.current_epoch.turns_remaining = 1

        game.next_turn()

        assert sentinel not in civ.known_map
