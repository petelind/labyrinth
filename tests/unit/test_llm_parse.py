"""Tests for LLM parse helpers."""

from __future__ import annotations

import json

from labyrinth.strategy.llm_parse import (
    BLACKBOARD_MAX_CHARS,
    extract_blackboard,
    parse_route,
    parse_routes,
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


class TestRouteParse:
    def test_parse_route_valid(self) -> None:
        raw = {
            "criteria": [{"field": "gene_dominant", "op": "eq", "value": "FIRE"}],
            "path": [[0, 49], [1, 49], [2, 49]],
        }
        route = parse_route(raw)
        assert route is not None
        assert route.path == ((0, 49), (1, 49), (2, 49))

    def test_parse_route_rejects_empty_criteria(self) -> None:
        raw = {"criteria": [], "path": [[0, 49], [1, 49]]}
        assert parse_route(raw) is None

    def test_parse_route_rejects_non_adjacent_path(self) -> None:
        raw = {
            "criteria": [{"field": "alive", "op": "eq", "value": True}],
            "path": [[0, 0], [2, 0]],
        }
        assert parse_route(raw) is None

    def test_parse_standing_orders_includes_routes(self) -> None:
        text = json.dumps({
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "routes": [{
                "criteria": [{"field": "gene_dominant", "op": "eq", "value": "FIRE"}],
                "path": [[0, 49], [1, 49]],
            }],
            "strategy_sumup": "routed",
        })
        orders = parse_standing_orders(text, turn_number=3)
        assert orders is not None
        assert len(orders.routes) == 1
        assert orders.routes[0].path == ((0, 49), (1, 49))

    def test_parse_routes_counts_dropped(self) -> None:
        data = {
            "routes": [
                {"criteria": [], "path": [[0, 49]]},
                {
                    "criteria": [{"field": "alive", "op": "eq", "value": True}],
                    "path": [[0, 50], [1, 50]],
                },
            ],
        }
        routes, dropped = parse_routes(data)
        assert len(routes) == 1
        assert dropped == 1
