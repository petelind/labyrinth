"""Tests for strategy thinking on turn summaries."""

from __future__ import annotations

import json

from labyrinth.domain.entities import GameEvents
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.engine.turn import CivilizationState, run_turn_for_civilization
from labyrinth.strategy.llm import LLMStrategy
from unittest.mock import patch


class TestTurnThinkingSummary:
    def test_llm_thinking_stored_on_turn_summary(self, seeded_rng, sample_civilization) -> None:
        strategy = LLMStrategy(client=object())
        state = CivilizationState(civilization=sample_civilization, strategy=strategy)
        lab = Labyrinth.create(seeded_rng)

        payload = {
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "weed_criteria": [],
            "reproduce_criteria": [],
            "strategy_sumup": "hold",
        }

        with patch.object(strategy, "_stream", lambda _m: iter([
            (json.dumps(payload), "Reason about soma."),
        ])):
            summary = run_turn_for_civilization(
                state, lab, 1, 19, seeded_rng, GameEvents(),
                strategy_label="LLM",
            )

        assert summary.strategy_thinking == "Reason about soma."
