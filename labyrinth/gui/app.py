"""Main Tkinter application."""

from __future__ import annotations

import logging
import queue
import shutil
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

from labyrinth.domain.archetypes import INITIAL_RAKSHAS
from labyrinth.domain.entities import Civilization, DNA, Epoch, GameEvents, Raksha
from labyrinth.domain.types import GeneType
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.engine.turn import CivilizationState
from labyrinth.game import Game, GameConfig, initial_soma
from labyrinth.gui.tab_civs import CivilizationsTab
from labyrinth.gui.tab_commentary import CommentaryTab
from labyrinth.gui.tab_plot import PlotTab
from labyrinth.persistence.repo import GameRepository
from labyrinth.replay import ReplayPlayer
from labyrinth.strategy.gen_alg import GenAlgStrategy
from labyrinth.strategy.llm import LLMStrategy

log = logging.getLogger(__name__)

_DUMMY_DNA = DNA(dominant=GeneType.FIRE, secondary=GeneType.FIRE, recessive=GeneType.FIRE)

TEST_THINKING_SECONDS = 0.1
TEST_AUTO_ADVANCE_MS = 100


class LabyrinthApp(tk.Tk):
    """Spectator GUI wired to Game via GameEvents callbacks."""

    def __init__(
        self,
        db_path: Path | None = None,
        test_mode: bool = False,
        game_seed: int | None = None,
    ) -> None:
        super().__init__()
        self.title("Labyrinth Simulation")
        self.geometry("1100x750")
        self.minsize(900, 600)

        self._test_mode = test_mode
        self._game_seed = game_seed
        self._injected_db_path = db_path
        self._save_path: Path | None = None
        self._plot_tab: PlotTab | None = None
        self._civs_tab: CivilizationsTab | None = None
        self._commentary_tab: CommentaryTab | None = None
        self._notebook: ttk.Notebook | None = None
        self._start_screen: ttk.Frame | None = None
        self._simulation_started = False
        self._stopped = False
        self._turn_in_progress = False
        self._is_replay_mode: bool = False
        self._replay_player: ReplayPlayer | None = None
        self._turns_var = tk.IntVar(value=20)
        self._game: Game | None = None
        self._events: GameEvents | None = None
        self._pending_main: queue.Queue[tuple[object, tuple]] = queue.Queue()

        if self._test_mode:
            self.withdraw()

        self._build_start_screen()
        self.after(50, self._pump_main_queue)

    def _pump_main_queue(self) -> None:
        """Drain worker-thread callbacks on the Tk main thread."""
        self.process_pending()
        self.after(50, self._pump_main_queue)

    @property
    def save_path(self) -> Path | None:
        """SQLite path for the current auto-saved game."""
        return self._save_path

    @property
    def game(self) -> Game | None:
        """Active game instance, or None before start."""
        return self._game

    @property
    def plot_tab(self) -> PlotTab | None:
        """Plot tab widget, or None before start."""
        return self._plot_tab

    @property
    def turns_var(self) -> tk.IntVar:
        """Turn-count spinbox variable on the start screen."""
        return self._turns_var

    @property
    def turn_in_progress(self) -> bool:
        """Whether a background turn worker is running."""
        return self._turn_in_progress

    def _civilization_specs(self) -> list[tuple[str, object]]:
        """Return civilization list for normal or test mode."""
        if self._test_mode:
            return [
                ("AlgoBot", GenAlgStrategy()),
                ("BetaBot", GenAlgStrategy()),
            ]
        return [
            ("AlgoBot", GenAlgStrategy()),
            ("Qwen-7B", LLMStrategy()),
        ]

    def _default_save_path(self) -> Path:
        """Generate a timestamped path under saves/."""
        saves_dir = Path("saves")
        saves_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return saves_dir / f"game_{stamp}.db"

    def _resolve_save_path(self) -> Path:
        """Pick save path from injection or auto-generate."""
        if self._injected_db_path is not None:
            self._injected_db_path.parent.mkdir(parents=True, exist_ok=True)
            return self._injected_db_path
        return self._default_save_path()

    def _create_game(self, turns_total: int) -> tuple[Game, GameEvents]:
        events = GameEvents()
        thinking_seconds = TEST_THINKING_SECONDS if self._test_mode else 300
        seed = self._game_seed if self._game_seed is not None else 42
        game = Game.create(
            self._civilization_specs(),
            GameConfig(
                turns_total=turns_total,
                db_path=self._save_path,
                seed=seed,
                thinking_seconds=thinking_seconds,
            ),
            events=events,
        )
        return game, events

    def _build_game_ui(
        self,
        labyrinth: Labyrinth | None = None,
        civilizations: list | None = None,
    ) -> None:
        """
        Build the notebook UI.

        When ``labyrinth`` and ``civilizations`` are given (replay mode) they
        are used directly instead of reading from ``self._game``.
        """
        if labyrinth is None or civilizations is None:
            if self._game is None:
                raise RuntimeError("Game must be created before building the UI")
            labyrinth = self._game.labyrinth
            civilizations = self._game.civilizations

        self._notebook = ttk.Notebook(self)
        auto_ms = TEST_AUTO_ADVANCE_MS if self._test_mode else 1500

        self._plot_tab = PlotTab(
            self._notebook,
            labyrinth,
            civilizations,
            auto_advance_ms=auto_ms,
        )
        self._civs_tab = CivilizationsTab(self._notebook, civilizations)
        self._commentary_tab = CommentaryTab(
            self._notebook,
            log_dispatch=self._dispatch,
            enable_log_handler=not self._test_mode,
        )

        self._notebook.add(self._plot_tab, text="Plot")
        self._notebook.add(self._civs_tab, text="Civilizations")
        self._notebook.add(self._commentary_tab, text="Chronicles")

        self._wire_events()
        self._plot_tab.bind_next_turn(self._advance_turn)
        self._plot_tab.bind_stop(self._stop_simulation)
        self._plot_tab.bind_reset(self._reset_simulation)
        self._commentary_tab.bind_save(self.save_game)
        self._commentary_tab.bind_load(self.load_game)

    def process_pending(self) -> None:
        """Run callbacks queued from background worker threads."""
        while True:
            try:
                fn, args = self._pending_main.get_nowait()
            except queue.Empty:
                break
            fn(*args)

    def _dispatch(self, fn, *args) -> None:
        """Queue a main-thread GUI update from a worker thread."""
        self._pending_main.put((fn, args))

    def _wire_events(self) -> None:
        if self._events is None:
            return
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
            command=self.start_simulation,
        ).pack(pady=20)

        ttk.Button(
            self._start_screen,
            text="Load Game",
            command=self.load_game,
        ).pack(pady=4)

    def _parse_turns_total(self) -> int | None:
        """Validate turns entered on the start screen."""
        try:
            turns = int(self._turns_var.get())
        except (tk.TclError, ValueError):
            if not self._test_mode:
                messagebox.showerror("Invalid turns", "Enter a whole number of turns.")
            return None
        if turns < 1 or turns > 1000:
            if not self._test_mode:
                messagebox.showerror("Invalid turns", "Turns must be between 1 and 1000.")
            return None
        return turns

    def start_simulation(self) -> None:
        """Reveal game tabs and populate initial labyrinth state."""
        turns_total = self._parse_turns_total()
        if turns_total is None:
            return

        self._save_path = self._resolve_save_path()

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

    def save_game(self) -> None:
        """Export the auto-save database via Save As dialog."""
        if self._save_path is None or not self._save_path.exists():
            if not self._test_mode:
                messagebox.showwarning("No save file", "No recorded game to export.")
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite database", "*.db")],
            initialfile=self._save_path.name,
        )
        if not dest:
            return
        shutil.copy2(self._save_path, dest)
        if self._commentary_tab:
            self._commentary_tab.append_message(f"[Save] Exported to {dest}")

    def export_save(self, dest: Path) -> None:
        """
        Copy auto-save DB to dest without a dialog (for E2E tests).

        :param dest: Destination file path.
        """
        if self._save_path is None or not self._save_path.exists():
            raise FileNotFoundError("No save file to export")
        shutil.copy2(self._save_path, dest)

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
        self._save_path = None
        self._simulation_started = False
        self._stopped = False
        self._turn_in_progress = False
        self._is_replay_mode = False
        self._replay_player = None
        self._build_start_screen()

    def load_game(self) -> None:
        """Open a file dialog to pick a save DB and enter replay mode."""
        if self._turn_in_progress:
            if not self._test_mode:
                messagebox.showinfo(
                    "Busy",
                    "Stop simulation to load/start another one.",
                )
            return
        if self._simulation_started and not self._stopped:
            if not self._test_mode:
                messagebox.showinfo(
                    "Simulation Running",
                    "Stop simulation to load/start another one.",
                )
            return

        db_path_str = filedialog.askopenfilename(
            title="Load Game",
            filetypes=[("SQLite database", "*.db")],
        )
        if not db_path_str:
            return
        self._enter_replay_mode(Path(db_path_str))

    def _enter_replay_mode(self, db_path: Path) -> None:
        """
        Tear down any existing UI and rebuild in replay mode from a save file.

        :param db_path: Path to the SQLite save to replay.
        """
        try:
            turns_total, civ_infos, frames = GameRepository.load_replay_data(db_path)
        except Exception as exc:
            log.exception("replay.load_failed", path=str(db_path))
            if not self._test_mode:
                messagebox.showerror("Load Failed", str(exc))
            return

        if not frames:
            if not self._test_mode:
                messagebox.showwarning("Empty Game", "No turns found in the saved game.")
            return

        # Tear down any running UI
        if self._plot_tab is not None:
            self._plot_tab.cancel_auto_advance()
        if self._notebook is not None:
            self._notebook.pack_forget()
            self._notebook.destroy()
            self._notebook = None
        self._plot_tab = None
        self._civs_tab = None
        self._commentary_tab = None
        self._game = None
        if self._start_screen is not None:
            self._start_screen.destroy()
            self._start_screen = None

        # Build shared Civilization objects from saved names
        start_soma = initial_soma(turns_total)
        civ_states: list[CivilizationState] = []
        civ_map: dict[str, Civilization] = {}
        for civ_id, civ_name in civ_infos:
            dummy_rakshas = [
                Raksha(id=uuid4(), civilization_id=civ_id, dna=_DUMMY_DNA)
                for _ in range(INITIAL_RAKSHAS)
            ]
            civ = Civilization(id=civ_id, name=civ_name, soma=start_soma, rakshas=dummy_rakshas)
            civ_states.append(CivilizationState(civilization=civ, strategy=GenAlgStrategy()))
            civ_map[civ_id] = civ

        # Build a Labyrinth shell initialised from the first recorded epoch
        first_frame = frames[0]
        replay_labyrinth = Labyrinth(
            grid=dict(first_frame.grid),
            current_epoch=Epoch(
                dominant_type=first_frame.epoch_dominant,
                turns_remaining=first_frame.epoch_turns_remaining,
                length=first_frame.epoch_length,
            ),
        )

        # Wire events and create the replay player
        self._events = GameEvents()
        self._replay_player = ReplayPlayer(
            frames=frames,
            labyrinth=replay_labyrinth,
            civ_map=civ_map,
            events=self._events,
        )

        # Build UI (reuses existing notebook machinery)
        self._build_game_ui(labyrinth=replay_labyrinth, civilizations=civ_states)

        if self._notebook is not None:
            self._notebook.pack(fill=tk.BOTH, expand=True)

        self._simulation_started = True
        self._stopped = False
        self._turn_in_progress = False
        self._is_replay_mode = True

        if self._plot_tab is not None:
            self._plot_tab.set_replay_mode(True)
            # Replay Turn uses _replay_turn, not _advance_turn
            self._plot_tab.bind_next_turn(self._replay_turn)
            self._plot_tab.set_stopped(False)
            self._plot_tab.draw_initial_state()

        total = self._replay_player.total_turns
        if self._commentary_tab is not None:
            self._commentary_tab.append_message(
                f"[Replay] Loaded {total} turns from {db_path.name}"
            )
        log.info("replay.mode_entered", turns=total, path=str(db_path))

    def _replay_turn(self) -> None:
        """Advance one replay frame synchronously (no background thread)."""
        if self._replay_player is None or not self._replay_player.has_next:
            return

        self._replay_player.advance()

        if not self._replay_player.has_next:
            if self._plot_tab is not None:
                self._plot_tab.set_stopped(True)
            if self._commentary_tab is not None:
                self._commentary_tab.append_message("[Replay] Reached the end of the recording.")
        else:
            if self._plot_tab is not None:
                self._plot_tab.schedule_auto_advance()

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

    def next_turn(self) -> None:
        """Advance the simulation by one turn (public API for tests)."""
        self._advance_turn()

    def _advance_turn(self) -> None:
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
            self._dispatch(self._on_turn_worker_finished, None)
        except StopIteration:
            self._dispatch(self._on_turn_worker_finished, "finished")
        except Exception as exc:
            log.exception("gui.turn_worker_failed")
            self._dispatch(self._on_turn_worker_error, exc)

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
        if not self._test_mode:
            messagebox.showerror("Turn failed", str(exc))


def main() -> None:
    """Launch the spectator GUI."""
    app = LabyrinthApp()
    app.mainloop()


if __name__ == "__main__":
    main()
