"""Tests for LLMStrategy parsing and decide flow."""

from __future__ import annotations

import json
from unittest.mock import patch
from uuid import uuid4

from labyrinth.domain.entities import DNA, Epoch, Raksha, StandingOrders, Travelog, TurnContext
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.narrative import TurnChronicler
from labyrinth.strategy.llm import LLMStrategy
from labyrinth.strategy.llm_prompt import SYSTEM_PROMPT


def _raksha(dominant: GeneType = GeneType.FIRE) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=GeneType.WATER, recessive=GeneType.EARTH),
        alive=True,
    )


def _context(
    turn: int = 1,
    chronicler: TurnChronicler | None = None,
    rakshas: list[Raksha] | None = None,
    travelogs: list[Travelog] | None = None,
) -> TurnContext:
    return TurnContext(
        turn_number=turn,
        soma=1000,
        rakshas=rakshas or [],
        recent_travelogs=travelogs or [],
        known_map={},
        turns_remaining=19,
        chronicler=chronicler,
        civilization_id="qwen",
        civilization_name="Qwen",
    )


class TestLLMParse:
    def test_try_parse_valid_json(self) -> None:
        strategy = LLMStrategy(client=object())
        text = json.dumps({
            "weed_criteria": [{"field": "gene_dominant", "op": "eq", "value": "EARTH"}],
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "reproduce_criteria": [{"field": "trips_survived", "op": "gte", "value": 1}],
            "strategy_sumup": "test",
        })
        result = strategy._try_parse(text, turn_number=1)
        assert result is not None
        assert result.last_updated_turn == 1
        assert result.weed_criteria[0].value == GeneType.EARTH

    def test_try_parse_invalid_retains_none(self) -> None:
        strategy = LLMStrategy(client=object())
        strategy.set_standing_orders(StandingOrders(
            weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            last_updated_turn=0,
        ))
        result = strategy._try_parse("not json at all", turn_number=2)
        assert result is None
        assert strategy.standing_orders.last_updated_turn == 0

    def test_trim_history_keeps_last_three_turns(self) -> None:
        strategy = LLMStrategy(client=object())
        strategy._history = [{"role": "user", "content": str(i)} for i in range(10)]
        strategy._trim_history()
        assert len(strategy._history) == 6

    def test_build_messages_includes_context_fields(self) -> None:
        strategy = LLMStrategy(client=object())
        ctx = _context(turn=3, rakshas=[_raksha()])
        messages = strategy._build_messages(ctx)
        user_msg = messages[-1]["content"]
        data = json.loads(user_msg)
        assert data["turn"] == 3
        assert data["soma"] == 1000
        assert "epoch" not in data
        assert "gene_survival_rates" in data
        assert "gene_counts" in data
        assert "archetype_survival" in data
        assert "clone_counts" in data
        assert "last_travelogs" in data
        assert "soma_bearers" in data
        assert messages[0]["content"] == SYSTEM_PROMPT

    def test_build_messages_includes_prior_blackboard(self) -> None:
        strategy = LLMStrategy(client=object())
        strategy._blackboard = {"phase": "harvest", "current_plan": "FIRE"}
        ctx = _context(turn=2)
        messages = strategy._build_messages(ctx)
        data = json.loads(messages[-1]["content"])
        assert data["prior_blackboard"]["phase"] == "harvest"

    def test_decide_updates_archetype_survival_and_blackboard(self) -> None:
        raksha = _raksha()
        logs = [Travelog(raksha.id, [(0, 0)], {}, 0, True)]
        payload = {
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "weed_criteria": [],
            "reproduce_criteria": [],
            "strategy_sumup": "scout",
            "blackboard": {
                "phase": "scout",
                "hypothesized_trap": "unknown",
                "current_plan": "explore",
                "last_actions": "turn 1 scout",
                "next_intent": "harvest if survival high",
            },
        }
        strategy = LLMStrategy(client=object())
        strategy._stream = lambda _msgs: iter([(json.dumps(payload), "")])

        strategy.set_deadline(__import__("time").time() + 180)
        strategy.decide(_context(rakshas=[raksha], travelogs=logs))

        key = (GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        assert strategy._archetype_survival[key] == 0.75
        assert strategy._blackboard is not None
        assert strategy._blackboard["phase"] == "scout"

    def test_decide_parse_failure_retains_blackboard(self) -> None:
        strategy = LLMStrategy(client=object())
        strategy._blackboard = {"phase": "harvest"}
        strategy._stream = lambda _msgs: iter([("not json", "")])
        strategy.set_deadline(__import__("time").time() + 180)
        strategy.decide(_context())
        assert strategy._blackboard == {"phase": "harvest"}


class TestLLMDecide:
    def test_decide_parses_only_once_after_stream(self) -> None:
        payload = {
            "weed_criteria": [],
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "reproduce_criteria": [],
            "strategy_sumup": "scout",
        }
        chunks = ['{"send_cri', 'teria": [{"field": "alive", "op": "eq", "value": true}], '
                    '"weed_criteria": [], "reproduce_criteria": [], "strategy_sumup": "scout"}']

        strategy = LLMStrategy(client=object())
        strategy._stream = lambda _msgs: ((c, "") for c in chunks)

        with patch.object(strategy, "_try_parse", wraps=strategy._try_parse) as mock_parse:
            strategy.set_deadline(__import__("time").time() + 180)
            strategy.decide(_context())
            assert mock_parse.call_count == 1

    def test_decide_captures_thinking_and_records_narrative(self) -> None:
        payload = {
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "weed_criteria": [],
            "reproduce_criteria": [],
            "reasoning": "Epoch favors FIRE.",
            "strategy_sumup": "Explore.",
        }
        strategy = LLMStrategy(client=object())
        strategy._stream = lambda _msgs: iter([
            ("", "Step 1: check soma."),
            (json.dumps(payload), "Step 2: send scouts."),
        ])

        chronicler = TurnChronicler()
        chronicler.begin_turn(1, 5, Epoch(GeneType.FIRE, 4, 5))
        chronicler.begin_civilization("Qwen", "LLM")

        strategy.set_deadline(__import__("time").time() + 180)
        strategy.decide(_context(chronicler=chronicler))

        assert "Step 1" in strategy.last_thinking
        assert strategy.standing_orders.last_updated_turn == 1
        body = "\n".join(chronicler.civ_chapters[0].lines)
        assert "Internal deliberation:" in body
        assert "Step 1" in body

    @patch("labyrinth.strategy.llm.emit_thinking")
    def test_decide_emits_thinking_block(self, mock_emit) -> None:
        payload = {
            "send_criteria": [{"field": "alive", "op": "eq", "value": True}],
            "weed_criteria": [],
            "reproduce_criteria": [],
            "strategy_sumup": "go",
        }
        strategy = LLMStrategy(client=object())
        strategy._stream = lambda _msgs: iter([(json.dumps(payload), "I should explore east.")])

        strategy.set_deadline(__import__("time").time() + 180)
        strategy.decide(_context())

        mock_emit.assert_called_once_with(1, "Qwen", "I should explore east.")
