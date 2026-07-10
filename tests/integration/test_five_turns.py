"""Integration test: 5 turns with SQLite (LLM optional)."""

from __future__ import annotations

import socket

import pytest

from labyrinth.domain.entities import CivilizationStatus, GameEvents
from labyrinth.game import Game, GameConfig, initial_soma
from labyrinth.persistence.repo import GameRepository
from labyrinth.strategy.gen_alg import GenAlgStrategy
from labyrinth.strategy.llm import LLMStrategy

# Set False to run GenAlg-only (faster CI). True requires ollama serve + qwen3:14b.
INCLUDE_LLM = True


def _ollama_available(host: str = "localhost", port: int = 11434) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _civilizations() -> list[tuple[str, object]]:
    civs: list[tuple[str, object]] = [("GenBot", GenAlgStrategy())]
    if INCLUDE_LLM:
        civs.append(("Qwen", LLMStrategy()))
    return civs


@pytest.mark.integration
def test_five_turns(tmp_path) -> None:
    """
    Ultimate success measure: 5 turns, no mocks.

    When ``INCLUDE_LLM`` is True, requires ``ollama serve`` and ``ollama pull qwen3:14b``.
    """
    if INCLUDE_LLM and not _ollama_available():
        pytest.skip("OLLAMA not running at localhost:11434")

    db_path = tmp_path / "game.db"
    game = Game.create(
        _civilizations(),
        GameConfig(turns_total=5, db_path=db_path, seed=42),
        GameEvents(),
    )
    civ_count = len(game.civilizations)
    assert all(s.civilization.soma == initial_soma(5) for s in game.civilizations)
    summaries = game.run_all()
    assert all(s.soma_end >= 0 for s in summaries)
    assert any(s.trips_sent > 0 for s in summaries)

    repo = GameRepository(db_path)
    if game.finished and game.current_turn < 5:
        assert repo.turn_count() == game.current_turn
        assert all(
            s.civilization.status == CivilizationStatus.EXTINCT
            for s in game.civilizations
        )
    else:
        assert len(summaries) == 5 * civ_count
        assert repo.turn_count() == 5

    if INCLUDE_LLM:
        extinct_turns = [
            s for s in summaries
            if s.civilization_id == "qwen" and s.turn_number > 1
        ]
        for summary in extinct_turns:
            if game.civilizations[1].civilization.status == CivilizationStatus.EXTINCT:
                if summary.turn_number > game.civilizations[1].civilization.extinct_turn:
                    assert summary.trips_sent == 0
                    assert summary.strategy_thinking == ""


@pytest.mark.integration
def test_hundred_turns(tmp_path) -> None:
    """GenAlg-only endurance run: 100 turns, seed 42."""
    turns_total = 100
    db_path = tmp_path / "game.db"
    game = Game.create(
        _civilizations(),
        GameConfig(turns_total=turns_total, db_path=db_path, seed=42),
        GameEvents(),
    )
    assert all(s.civilization.soma == initial_soma(turns_total) for s in game.civilizations)
    summaries = game.run_all()
    assert all(s.soma_end >= 0 for s in summaries)
    assert any(s.trips_sent > 0 for s in summaries)

    repo = GameRepository(db_path)
    civ = game.civilizations[0].civilization
    if game.finished and game.current_turn < turns_total:
        assert repo.turn_count() == game.current_turn
        assert civ.status == CivilizationStatus.EXTINCT
    else:
        assert len(summaries) == turns_total
        assert repo.turn_count() == turns_total
        assert civ.status == CivilizationStatus.ACTIVE
        assert game.finished
        assert summaries[-1].pop_end >= 80
        assert summaries[24].pop_end >= summaries[0].pop_end
