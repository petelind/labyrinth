"""Tests for turn narrative chronicler."""

from __future__ import annotations

from labyrinth.domain.entities import Epoch, TurnSummary
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.logging_config import emit_thinking
from labyrinth.narrative import TurnChronicler, format_criteria, format_criterion


class TestFormatCriteria:
    def test_single_criterion(self) -> None:
        c = Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE)
        assert format_criterion(c) == "gene dominant is FIRE"

    def test_empty_list(self) -> None:
        assert format_criteria([]) == "none"


class TestTurnChronicler:
    def test_record_thinking_in_chapter(self) -> None:
        chronicler = TurnChronicler()
        epoch = Epoch(dominant_type=GeneType.FIRE, turns_remaining=4, length=5)
        chronicler.begin_turn(1, 20, epoch)
        chronicler.begin_civilization("Qwen", "LLM")
        chronicler.record_thinking("First I check epoch.\nThen I send scouts.")
        body = chronicler.flush()
        assert "Internal deliberation:" in body
        assert "First I check epoch." in body

    def test_flush_produces_chapter_structure(self) -> None:
        chronicler = TurnChronicler()
        epoch = Epoch(dominant_type=GeneType.FIRE, turns_remaining=4, length=5)
        chronicler.begin_turn(1, 20, epoch)
        chronicler.begin_civilization("GenBot", "GenAlg")
        chronicler.record_opening(1000, 100)
        chronicler.record_reasoning("Cull weak EARTH genes.")
        chronicler.record_deliberation("Harvest aggressively.")
        chronicler.record_close(TurnSummary(
            turn_number=1, civilization_id="genbot",
            soma_start=1000, soma_end=950, pop_start=100, pop_end=90,
            deaths=10, trips_sent=70, trips_survived=50, soma_gathered=5,
            strategy_sumup="test",
        ))
        body = chronicler.flush()
        assert "CHAPTER 1" in body
        assert "GenBot (GenAlg)" in body
        assert "Conclusion:" in body
        assert "Cull weak EARTH genes." in body
        assert "Soma 1000 → 950" in body


class TestEmitThinking:
    def test_emit_thinking_prints_deliberation_header(self, capsys) -> None:
        emit_thinking(2, "Qwen", "Analyze epoch shift.")
        out = capsys.readouterr().out
        assert "DELIBERATION" in out
        assert "Turn 2" in out
        assert "Analyze epoch shift." in out

    def test_emit_thinking_skips_empty(self, capsys) -> None:
        emit_thinking(1, "Qwen", "   ")
        assert capsys.readouterr().out == ""
