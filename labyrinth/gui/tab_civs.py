"""Tkinter Civilizations tab with charts."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from labyrinth.domain.entities import CivilizationStatus, TurnSummary
from labyrinth.domain.types import GeneType


class CivilizationsTab(ttk.Frame):
    """Population and soma charts per civilization."""

    def __init__(self, master, civilizations: list) -> None:
        super().__init__(master)
        self._civ_states = civilizations
        self._history: dict[str, list[TurnSummary]] = {
            s.civilization.id: [] for s in civilizations
        }
        self._turn_selector = tk.IntVar(value=0)
        self._build()

    def _build(self) -> None:
        nav = ttk.Frame(self)
        nav.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(nav, text="Turn:").pack(side=tk.LEFT)
        self._turn_label = ttk.Label(nav, text="0")
        self._turn_label.pack(side=tk.LEFT, padx=4)

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True)
        self._figures: dict[str, Figure] = {}
        self._canvases: dict[str, FigureCanvasTkAgg] = {}

        for state in self._civ_states:
            label = state.civilization.name
            if state.civilization.status == CivilizationStatus.EXTINCT:
                label = f"{label} (EXTINCT)"
            frame = ttk.Frame(self._notebook)
            self._notebook.add(frame, text=label)
            fig = Figure(figsize=(5, 4), dpi=80)
            canvas = FigureCanvasTkAgg(fig, master=frame)
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            self._figures[state.civilization.id] = fig
            self._canvases[state.civilization.id] = canvas

    def on_turn_end(self, summaries: list[TurnSummary]) -> None:
        for summary in summaries:
            self._history.setdefault(summary.civilization_id, []).append(summary)
        if summaries:
            self._turn_label.configure(text=str(summaries[0].turn_number))
        self._redraw_all()

    def reset_view(self, civilizations: list) -> None:
        """Clear chart history and rebind civilization state."""
        self._civ_states = civilizations
        self._history = {s.civilization.id: [] for s in civilizations}
        self._turn_label.configure(text="0")
        for state in self._civ_states:
            civ_id = state.civilization.id
            fig = self._figures[civ_id]
            fig.clear()
            self._canvases[civ_id].draw()

    def _redraw_all(self) -> None:
        for state in self._civ_states:
            civ_id = state.civilization.id
            history = self._history.get(civ_id, [])
            fig = self._figures[civ_id]
            fig.clear()
            if not history:
                self._canvases[civ_id].draw()
                continue

            ax1 = fig.add_subplot(211)
            turns = [h.turn_number for h in history]
            soma = [h.soma_end for h in history]
            ax1.plot(turns, soma, marker="o")
            ax1.set_title("Soma over turns")
            ax1.set_xlabel("Turn")
            ax1.set_ylabel("Soma")

            ax2 = fig.add_subplot(212)
            counts = {g: 0 for g in GeneType}
            for r in state.civilization.rakshas:
                if r.alive:
                    counts[r.dna.dominant] += 1
            genes = [g.name for g in GeneType]
            vals = [counts[g] for g in GeneType]
            ax2.bar(genes, vals)
            ax2.set_title("Gene breakdown (dominant)")
            ax2.set_ylabel("Count")

            fig.tight_layout()
            self._canvases[civ_id].draw()
