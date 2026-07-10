"""Emit standalone thinking and chapter blocks."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure structlog for console output with timestamps and event names.

    :param level: Root logging level.
    """
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a bound structlog logger for the given module name.

    :param name: Logger name, typically ``__name__``.
    :return: Configured bound logger.
    """
    return structlog.get_logger(name)


def emit_chapter(text: str) -> None:
    """
    Emit a multi-line turn narrative chapter to the log.

    :param text: Full chapter body to emit.
    """
    print(text, flush=True)


def emit_thinking(turn: int, civilization: str, thinking: str) -> None:
    """
    Emit the model's internal deliberation as a readable block.

    Printed separately from per-event structlog lines so you can study
    how the LLM reasoned before issuing orders.

    :param turn: Turn number.
    :param civilization: Civilization name or id.
    :param thinking: Full thinking text from the model.
    """
    if not thinking.strip():
        return
    header = (
        f"\n{'┄' * 60}\n"
        f"  DELIBERATION — Turn {turn} · {civilization}\n"
        f"{'┄' * 60}"
    )
    body = "\n".join(f"  {line}" if line.strip() else "" for line in thinking.strip().splitlines())
    footer = f"\n{'┄' * 60}\n"
    print(header, flush=True)
    print(body, flush=True)
    print(footer, flush=True)
    structlog.get_logger("labyrinth.thinking").info(
        "strategy.thinking_captured",
        turn=turn,
        civilization=civilization,
        chars=len(thinking),
    )
