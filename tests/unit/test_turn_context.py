"""Tests for TurnContext strategy-facing fields."""

from __future__ import annotations

import dataclasses

from labyrinth.domain.entities import TurnContext


class TestTurnContext:
    def test_has_no_current_epoch_field(self) -> None:
        fields = {f.name for f in dataclasses.fields(TurnContext)}
        assert "current_epoch" not in fields
