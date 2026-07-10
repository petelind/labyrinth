"""Main Tkinter application."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from labyrinth.domain.entities import GameEvents
from labyrinth.game import Game, GameConfig
from labyrinth.gui.tab_civs import CivilizationsTab
from labyrinth.gui.tab_commentary import CommentaryTab
from labyrinth.gui.tab_plot import PlotTab
from labyrinth.strategy.gen_alg import GenAlgStrategy
from labyrinth.strategy.llm import LLMStrategy

log = logging.getLogger(__name__)


class LabyrinthApp(tk.Tk):
    """Spectator GUI wired to Game via GameEvents callbacks."""

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.title("Labyrinth Simulation")
        self.geometry("1100x750")
        self.minsize(900, 600)

        self._db_path = db_path
        self._plot_tab: PlotTab | None = None
        self._civs_tab: CivilizationsTab | None = None
        self._commentary_tab: CommentaryTab | None = None
        self._notebook: ttk.Notebook | None = None
        self._start_screen: ttk.Frame | None = None
        self._simulation_started = False
        self._stopped = False
        self._turn_in_progress = False
        self._turns_var = tk.IntVar(value=20)
        self._game: Game | None = None
        self._events: GameEvents | None = None

        self._build_start_screen()

    def _create_game(self, turns_total: int) -> tuple[Game, GameEvents]:
        events = GameEvents()
        game = Game.create(
            [
                ("AlgoBot", GenAlgStrategy()),
                ("Qwen-7B", LLMStrategy()),
            ],
            GameConfig(turns_total=turns_total, db_path=self._db_path),
            events=events,
        )
        return game, events

    def _build_game_ui(self) -> None:
        if self._game is None:
            raise RuntimeError("Game must be created before building the UI")

        self._notebook = ttk.Notebook(self)

        self._plot_tab = PlotTab(self._notebook, self._game.labyrinth, self._game.civilizations)
        self._civs_tab = CivilizationsTab(self._notebook, self._game.civilizations)
        self._commentary_tab = CommentaryTab(self._notebook)

        self._notebook.add(self._plot_tab, text="Plot")
        self._notebook.add(self._civs_tab, text="Civilizations")
        self._notebook.add(self._commentary_tab, text="Commentary")

        self._wire_events()
        self._plot_tab.bind_next_turn(self._next_turn)
        self._plot_tab.bind_stop(self._stop_simulation)
        self._plot_tab.bind_reset(self._reset_simulation)

    def _dispatch(self, fn, *args) -> None:
        """Schedule a main-thread GUI update from a worker thread."""
        self.after(0, lambda: fn(*args))

    def _wire_events(self) -> None:
        self._events.on_turn_start = lambda t, e: self._dispatch(self._apply_turn_start, t, e)
        self._events.on_trip_result = lambda c, r: self._dispatch(self._apply_trip_result, c, r)
        self._events.on_turn_end = lambda s: self._dispatch(self._apply_turn_end, s)
        self._events.on_game_end = lambda s: self._dispatch(self._apply_game_end, s)
        self._events.on_chapter = lambda t: self._dispatch(self._apply_chapter, t)

    def _build_start_screen(self) -> None:
        """Show welcome screen before the game notebook is visible."""
        self._start_screen = ttk.Frame(self)
        self._start_screen.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            self._start_screen,
            text="Labyrinth Simulation",
            font=("", 24),
        ).pack(pady=60)

        settings = ttk.Frame(self._start_screen)
        settings.pack(pady=12)
        ttk.Label(settings, text="Number of turns:").pack(side=tk.LEFT)
        ttk.Spinbox(
            settings,
            from_=1,
            to=1000,
            textvariable=self._turns_var,
            width=8,
        ).pack(side=tk.LEFT, padx=8)

        ttk.Button(
            self._start_screen,
            text="Start Simulation",
            command=self._start_simulation,
        ).pack(pady=20)

    def _parse_turns_total(self) -> int | None:
        """Validate turns entered on the start screen."""
        try:
            turns = int(self._turns_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Invalid turns", "Enter a whole number of turns.")
            return None
        if turns < 1:
            messagebox.showerror("Invalid turns", "Turns must be at least 1.")
            return None
        if turns > 1000:
            messagebox.showerror("Invalid turns", "Turns must be at most 1000.")
            return None
        return turns

    def _start_simulation(self) -> None:
        """Reveal game tabs and populate initial labyrinth state."""
        turns_total = self._parse_turns_total()
        if turns_total is None:
            return

        if self._start_screen is not None:
            self._start_screen.destroy()
            self._start_screen = None

        self._game, self._events = self._create_game(turns_total)
        self._build_game_ui()

        if self._notebook is not None:
            self._notebook.pack(fill=tk.BOTH, expand=True)
        self._simulation_started = True
        self._stopped = False
        self._turn_in_progress = False
        if self._plot_tab:
            self._plot_tab.set_stopped(False)
            self._plot_tab.draw_initial_state()

    def _stop_simulation(self) -> None:
        """Pause after the current turn; soft stop (no mid-turn cancellation)."""
        if not self._simulation_started:
            return
        self._stopped = True
        if self._plot_tab:
            self._plot_tab.set_stopped(True)

    def _reset_simulation(self) -> None:
        """Create a fresh game and return to the start screen."""
        if self._turn_in_progress:
            return
        if self._plot_tab:
            self._plot_tab.cancel_auto_advance()
            self._plot_tab.set_stopped(False)
            self._plot_tab.set_turn_busy(False)

        if self._notebook is not None:
            self._notebook.pack_forget()
            self._notebook.destroy()
            self._notebook = None

        self._plot_tab = None
        self._civs_tab = None
        self._commentary_tab = None
        self._game = None
        self._events = None
        self._simulation_started = False
        self._stopped = False
        self._turn_in_progress = False
        self._build_start_screen()

    def _apply_turn_start(self, turn: int, epoch) -> None:
        if self._plot_tab:
            self._plot_tab.on_turn_start(turn, epoch)

    def _apply_trip_result(self, civ_id: str, result) -> None:
        if self._plot_tab:
            self._plot_tab.on_trip_result(civ_id, result)

    def _apply_turn_end(self, summaries) -> None:
        if self._plot_tab:
            self._plot_tab.on_turn_end(summaries)
        if self._civs_tab:
            self._civs_tab.on_turn_end(summaries)
        if self._commentary_tab:
            self._commentary_tab.on_turn_end(summaries)

    def _apply_game_end(self, summaries) -> None:
        if self._commentary_tab:
            self._commentary_tab.on_turn_end(summaries)
        if self._plot_tab:
            self._plot_tab.set_stopped(True)

    def _apply_chapter(self, chapter_text: str) -> None:
        if self._commentary_tab:
            self._commentary_tab.on_chapter(chapter_text)

    def _next_turn(self) -> None:
        if self._stopped or self._turn_in_progress or self._game is None:
            return
        next_turn_num = self._game.current_turn + 1
        self._turn_in_progress = True
        if self._plot_tab:
            self._plot_tab.set_turn_busy(True, f"Turn {next_turn_num} in progress…")
        threading.Thread(target=self._run_turn_worker, daemon=True).start()

    def _run_turn_worker(self) -> None:
        if self._game is None:
            return
        try:
            self._game.next_turn()
            self.after(0, self._on_turn_worker_finished, None)
        except StopIteration:
            self.after(0, self._on_turn_worker_finished, "finished")
        except Exception as exc:
            log.exception("gui.turn_worker_failed")
            self.after(0, self._on_turn_worker_error, exc)

    def _on_turn_worker_finished(self, reason: str | None) -> None:
        self._turn_in_progress = False
        if self._plot_tab is None:
            return
        if reason == "finished" or (self._game is not None and self._game.finished):
            self._plot_tab.set_turn_busy(False)
            self._plot_tab.set_stopped(True)
        elif self._stopped:
            self._plot_tab.set_turn_busy(False)
            self._plot_tab.set_stopped(True)
        else:
            self._plot_tab.set_turn_busy(False)
            self._plot_tab.schedule_auto_advance()

    def _on_turn_worker_error(self, exc: Exception) -> None:
        self._turn_in_progress = False
        if self._plot_tab:
            self._plot_tab.set_turn_busy(False)
        messagebox.showerror("Turn failed", str(exc))


def main() -> None:
    """Launch the spectator GUI."""
    app = LabyrinthApp()
    app.mainloop()


if __name__ == "__main__":
    main()
