"""Tests for epoch shock detection."""

from __future__ import annotations

from labyrinth.strategy.epoch_shock import detect_epoch_shock


class TestDetectEpochShock:
    def test_detect_shock_on_counter_reset(self) -> None:
        assert detect_epoch_shock(
            epoch_turns_remaining=8,
            last_epoch_turns_remaining=1,
            known_map_size=100,
            had_known_map=True,
        ) is True

    def test_detect_shock_on_known_map_clear(self) -> None:
        assert detect_epoch_shock(
            epoch_turns_remaining=3,
            last_epoch_turns_remaining=4,
            known_map_size=0,
            had_known_map=True,
        ) is True

    def test_no_shock_on_first_turn_empty_map(self) -> None:
        assert detect_epoch_shock(
            epoch_turns_remaining=5,
            last_epoch_turns_remaining=None,
            known_map_size=0,
            had_known_map=False,
        ) is False

    def test_no_shock_on_steady_epoch_countdown(self) -> None:
        assert detect_epoch_shock(
            epoch_turns_remaining=4,
            last_epoch_turns_remaining=5,
            known_map_size=50,
            had_known_map=True,
        ) is False
