"""LLM-based strategy using local OLLAMA Qwen."""

from __future__ import annotations

import json
from typing import Any

from labyrinth.domain.entities import StandingOrders, TurnContext
from labyrinth.logging_config import emit_thinking, get_logger
from labyrinth.narrative import format_criteria
from labyrinth.strategy.base import Strategy
from labyrinth.strategy.empirical import (
    ArchetypeSurvivalMap,
    build_strategy_snapshot,
    update_archetype_survival,
)
from labyrinth.strategy.llm_parse import (
    extract_blackboard,
    extract_reasoning_field,
    parse_standing_orders,
    truncate_blackboard,
)
from labyrinth.strategy.llm_prompt import SYSTEM_PROMPT

log = get_logger(__name__)


class LLMStrategy(Strategy):
    """OLLAMA + Qwen strategy with end-of-stream parse and thinking capture."""

    DEFAULT_MODEL = "qwen3:14b"
    HISTORY_TURNS = 3

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        ollama_host: str = "http://localhost:11434",
        client: Any | None = None,
    ) -> None:
        super().__init__()
        self._model = model
        self._host = ollama_host
        self._client = client
        self._history: list[dict[str, str]] = []
        self._archetype_survival: ArchetypeSurvivalMap = {}
        self._blackboard: dict[str, str] | None = None
        self.last_reasoning: str = ""
        self.last_thinking: str = ""

    def decide(self, context: TurnContext) -> None:
        self._archetype_survival = update_archetype_survival(
            self._archetype_survival,
            context.recent_travelogs,
            context.rakshas,
        )
        messages = self._build_messages(context)
        content_buffer = ""
        thinking_buffer = ""
        try:
            for chunk, thinking in self._stream(messages):
                if thinking:
                    thinking_buffer += thinking
                if chunk:
                    content_buffer += chunk
                if self.should_stop():
                    break
        except Exception:
            log.exception("llm.decide_failed")
            return

        self.last_thinking = thinking_buffer.strip()
        parsed_orders = self._try_parse(content_buffer, context.turn_number)

        if parsed_orders:
            self.set_standing_orders(parsed_orders)
            self.last_reasoning = extract_reasoning_field(content_buffer) or parsed_orders.current_strategy_sumup
            board = extract_blackboard(content_buffer)
            if board is not None:
                self._blackboard = truncate_blackboard(board)
        else:
            self.last_reasoning = ""
            log.warning("strategy.parse_failed", reason="no_valid_orders_after_stream")

        civ_name = context.civilization_name or context.civilization_id or "LLM"
        emit_thinking(context.turn_number, civ_name, self.last_thinking)
        self._record_narrative(context, thinking_buffer, content_buffer, parsed_orders)

        if parsed_orders is not None:
            log.info(
                "strategy.llm_decided",
                turn=context.turn_number,
                civilization=civ_name,
                weed=format_criteria(parsed_orders.weed_criteria),
                send=format_criteria(parsed_orders.send_criteria),
                routes=len(parsed_orders.routes),
                thinking_chars=len(self.last_thinking),
                reasoning=self.last_reasoning[:200],
                blackboard=self._blackboard,
            )

        self._history.append({"role": "assistant", "content": content_buffer})
        self._trim_history()

    def _record_narrative(
        self,
        context: TurnContext,
        thinking: str,
        content: str,
        orders: StandingOrders | None,
    ) -> None:
        if context.chronicler is None:
            return
        if thinking.strip():
            context.chronicler.record_thinking(thinking.strip())
        reasoning = extract_reasoning_field(content)
        if reasoning:
            context.chronicler.record_reasoning(reasoning)
        if orders and orders.current_strategy_sumup:
            context.chronicler.record_deliberation(orders.current_strategy_sumup)

    def _get_client(self):
        if self._client is not None:
            return self._client
        import ollama
        return ollama.Client(host=self._host)

    def _stream(self, messages: list[dict[str, str]]):
        client = self._get_client()
        response = client.chat(model=self._model, messages=messages, stream=True)
        for part in response:
            message = part.get("message", {})
            content = message.get("content", "")
            thinking = message.get("thinking", "")
            if content or thinking:
                yield content, thinking

    def _build_messages(self, context: TurnContext) -> list[dict[str, str]]:
        snapshot = build_strategy_snapshot(
            context,
            self._archetype_survival,
            prior_blackboard=self._blackboard,
        )
        user_content = json.dumps(snapshot)
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self._history[-self.HISTORY_TURNS * 2:])
        messages.append({"role": "user", "content": user_content})
        self._history.append({"role": "user", "content": user_content})
        return messages

    def _try_parse(self, text: str, turn_number: int) -> StandingOrders | None:
        """Parse standing orders once from the complete stream buffer."""
        return parse_standing_orders(text, turn_number)

    def _trim_history(self) -> None:
        max_messages = self.HISTORY_TURNS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
