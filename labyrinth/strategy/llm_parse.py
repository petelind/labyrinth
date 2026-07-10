"""Pure helpers for parsing LLM strategy responses."""

from __future__ import annotations

import json
import re

from labyrinth.domain.entities import StandingOrders
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType

_THINK_BLOCK_RE = re.compile(
    r"<\s*think\s*>.*?<\s*/\s*think\s*>",
    re.DOTALL | re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

FIELD_MAP = {f.value: f for f in CriteriaField}
OP_MAP = {o.value: o for o in CriteriaOp}
GENE_MAP = {g.name: g for g in GeneType}

BLACKBOARD_KEYS = frozenset({
    "phase",
    "hypothesized_trap",
    "current_plan",
    "last_actions",
    "next_intent",
})
BLACKBOARD_MAX_CHARS = 500


def strip_content_for_parse(text: str) -> str:
    """
    Remove thinking markers and markdown fences before JSON extraction.

    :param text: Raw model content buffer.
    :return: Cleaned text containing JSON payload.
    """
    cleaned = _THINK_BLOCK_RE.sub("", text)
    fence = _FENCE_RE.search(cleaned)
    if fence:
        return fence.group(1).strip()
    return cleaned.strip()


def extract_json_object(text: str) -> dict | None:
    """
    Extract the first JSON object from text.

    :param text: Text potentially containing a JSON object.
    :return: Parsed dict or None.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_criterion(raw: dict) -> Criterion | None:
    """Parse one criterion dict from LLM JSON."""
    field_str = raw.get("field", "")
    op_str = raw.get("op", "")
    value = raw.get("value")
    field = FIELD_MAP.get(field_str)
    op = OP_MAP.get(op_str)
    if field is None or op is None:
        return None
    if isinstance(value, str) and value in GENE_MAP:
        value = GENE_MAP[value]
    if not isinstance(value, (GeneType, int, bool)):
        return None
    return Criterion(field=field, op=op, value=value)


def parse_standing_orders(text: str, turn_number: int) -> StandingOrders | None:
    """
    Parse standing orders from complete model output (post-stream).

    :param text: Full content buffer after stream ends.
    :param turn_number: Current turn for order stamping.
    :return: StandingOrders or None if unparseable.
    """
    cleaned = strip_content_for_parse(text)
    data = extract_json_object(cleaned)
    if data is None:
        return None

    weed = [c for r in data.get("weed_criteria", []) if (c := parse_criterion(r))]
    send = [c for r in data.get("send_criteria", []) if (c := parse_criterion(r))]
    repro = [c for r in data.get("reproduce_criteria", []) if (c := parse_criterion(r))]

    if not any([weed, send, repro]):
        return None

    sumup = data.get("strategy_sumup", "") or data.get("reasoning", "")
    return StandingOrders(
        weed_criteria=weed,
        send_criteria=send,
        reproduce_criteria=repro,
        current_strategy_sumup=str(sumup),
        last_updated_turn=turn_number,
    )


def extract_reasoning_field(text: str) -> str:
    """Extract the reasoning field from model JSON output."""
    cleaned = strip_content_for_parse(text)
    data = extract_json_object(cleaned)
    if data is None:
        return ""
    return str(data.get("reasoning", "")).strip()


def extract_blackboard(text: str) -> dict[str, str] | None:
    """
    Extract and validate blackboard dict from model JSON output.

    :param text: Full model content buffer.
    :return: Sanitized blackboard or None if missing/invalid.
    """
    cleaned = strip_content_for_parse(text)
    data = extract_json_object(cleaned)
    if data is None:
        return None
    raw = data.get("blackboard")
    if not isinstance(raw, dict):
        return None
    board: dict[str, str] = {}
    for key in BLACKBOARD_KEYS:
        value = raw.get(key)
        if value is not None and str(value).strip():
            board[key] = str(value).strip()
    return board or None


def truncate_blackboard(
    board: dict[str, str],
    max_chars: int = BLACKBOARD_MAX_CHARS,
) -> dict[str, str]:
    """
    Trim blackboard strings so total serialized length stays within cap.

    :param board: Blackboard dict to truncate.
    :param max_chars: Maximum total character budget.
    :return: Truncated blackboard copy.
    """
    result = dict(board)
    while len(json.dumps(result)) > max_chars:
        longest_key = max(result, key=lambda k: len(result[k]))
        if len(result[longest_key]) <= 1:
            break
        result[longest_key] = result[longest_key][:-1]
    return result
