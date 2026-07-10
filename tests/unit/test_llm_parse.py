"""Tests for LLM parse helpers."""

from __future__ import annotations

import json

from labyrinth.strategy.llm_parse import (
    BLACKBOARD_MAX_CHARS,
    extract_blackboard,
    parse_standing_orders,
    truncate_blackboard,
)


class TestBlackboardParse:
    def test_extract_valid_blackboard(self) -> None:
        text = json.dumps({
            "blackboard": {
                "phase": "scout",
                "hypothesized_trap": "FIRE",
                "current_plan": "Full grid scout",
                "last_actions": "Sent all alive",
                "next_intent": "Harvest best gene",
            },
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "weed_criteria": [],
            "reproduce_criteria": [],
        })
        board = extract_blackboard(text)
        assert board is not None
        assert board["phase"] == "scout"
        assert board["hypothesized_trap"] == "FIRE"

    def test_extract_missing_blackboard_returns_none(self) -> None:
        assert extract_blackboard('{"send_criteria": []}') is None

    def test_orders_parse_unchanged_with_blackboard(self) -> None:
        text = json.dumps({
            "blackboard": {"phase": "harvest", "current_plan": "go"},
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "weed_criteria": [],
            "reproduce_criteria": [],
            "strategy_sumup": "harvest",
        })
        orders = parse_standing_orders(text, turn_number=5)
        assert orders is not None
        assert orders.last_updated_turn == 5

    def test_truncate_blackboard(self) -> None:
        board = {
            "phase": "harvest",
            "current_plan": "x" * 400,
            "next_intent": "y" * 200,
        }
        trimmed = truncate_blackboard(board, max_chars=BLACKBOARD_MAX_CHARS)
        assert len(json.dumps(trimmed)) <= BLACKBOARD_MAX_CHARS
