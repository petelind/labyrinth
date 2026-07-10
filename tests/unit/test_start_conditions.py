"""Tests for game start conditions."""

from __future__ import annotations

from pathlib import Path

from labyrinth.domain.types import GeneType
from labyrinth.domain.archetypes import INITIAL_RAKSHAS
from labyrinth.game import Game, GameConfig, initial_soma
from labyrinth.strategy.gen_alg import GenAlgStrategy


class TestInitialSoma:
    def test_initial_soma_scales_with_turns(self) -> None:
        assert initial_soma(20) == 2000
        assert initial_soma(5) == 500
        assert initial_soma(2) == 200

    def test_game_create_uses_scaled_soma(self, tmp_db: Path) -> None:
        game = Game.create(
            [("GenBot", GenAlgStrategy())],
            GameConfig(turns_total=20, db_path=tmp_db, seed=42),
        )
        assert game.civilizations[0].civilization.soma == 2000

    def test_initial_rakshas_diverse_archetype_cohort(self, tmp_db: Path) -> None:
        game = Game.create(
            [("GenBot", GenAlgStrategy())],
            GameConfig(turns_total=5, db_path=tmp_db, seed=42),
        )
        rakshas = game.civilizations[0].civilization.rakshas
        assert len(rakshas) == INITIAL_RAKSHAS
        dom_sec_pairs = {
            (r.dna.dominant, r.dna.secondary) for r in rakshas[:96]
        }
        assert len(dom_sec_pairs) == 16
