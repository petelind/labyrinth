"""E2E GUI tests for simulation start, turns, auto-advance, and save export."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from labyrinth.persistence.repo import GameRepository
@pytest.mark.gui
def test_start_sets_turn_zero(gui_app, harness) -> None:
    """Starting simulation shows Turn 0 and creates a save file."""
    harness.start(turns=5)
    assert gui_app.plot_tab is not None
    assert gui_app.plot_tab.turn_label.get() == "Turn 0"
    assert gui_app.save_path is not None
    assert gui_app.save_path.exists()


@pytest.mark.gui
def test_manual_turn_advances(gui_app, harness) -> None:
    """One manual turn increments current_turn and persists to SQLite."""
    harness.start(turns=5)
    harness.next_turn()
    harness.wait_until_turn(1)
    harness.wait_until_idle()
    assert gui_app.game is not None
    assert gui_app.game.current_turn == 1
    assert gui_app.save_path is not None
    assert GameRepository(gui_app.save_path).turn_count() == 1


@pytest.mark.gui
def test_auto_advance_runs(gui_app, harness) -> None:
    """Auto-advance chains turns without blocking the UI."""
    harness.start(turns=5)
    harness.next_turn()
    harness.wait_until_turn(1)
    harness.wait_until_idle()
    harness.enable_auto_advance()
    harness.wait_until_turn(3, timeout=30)
    harness.wait_until_idle()
    assert gui_app.game is not None
    assert gui_app.game.current_turn >= 3


@pytest.mark.gui
def test_save_export(gui_app, harness, tmp_path: Path) -> None:
    """Save Game exports the auto-save DB to a chosen path."""
    harness.start(turns=3)
    harness.next_turn()
    harness.wait_until_turn(1)
    harness.wait_until_idle()

    export_path = tmp_path / "export.db"

    with patch(
        "labyrinth.gui.app.filedialog.asksaveasfilename",
        return_value=str(export_path),
    ):
        gui_app.save_game()

    assert export_path.exists()
    assert GameRepository(export_path).turn_count() == 1
