"""Tkinter Civilizations tab with charts."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from labyrinth.domain.entities import CivilizationStatus, TurnSummary
from labyrinth.domain.types import GeneType
from labyrinth.gui.civ_palette import CIV_PALETTES

_BAR_WIDTH = 0.35


class CivilizationsTab(ttk.Frame):
    """Combined population and soma charts for all civilizations."""

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

        self._figure = Figure(figsize=(7, 7), dpi=80)
        self._canvas = FigureCanvasTkAgg(self._figure, master=self)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

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
        self._figure.clear()
        self._canvas.draw()

    def _civ_label(self, state) -> str:
        name = state.civilization.name
        if state.civilization.status == CivilizationStatus.EXTINCT:
            return f"{name} (EXTINCT)"
        return name

    def _gene_counts(self, state) -> dict[GeneType, int]:
        counts = {g: 0 for g in GeneType}
        for raksha in state.civilization.rakshas:
            if raksha.alive:
                counts[raksha.dna.dominant] += 1
        return counts

    def _redraw_all(self) -> None:
        self._figure.clear()
        has_history = any(self._history.get(s.civilization.id) for s in self._civ_states)
        has_population = any(
            any(r.alive for r in s.civilization.rakshas) for s in self._civ_states
        )
        if not has_history and not has_population:
            self._canvas.draw()
            return

        ax_soma = self._figure.add_subplot(311)
        for idx, state in enumerate(self._civ_states):
            history = self._history.get(state.civilization.id, [])
            if not history:
                continue
            palette = CIV_PALETTES[idx % len(CIV_PALETTES)]
            ax_soma.plot(
                [h.turn_number for h in history],
                [h.soma_end for h in history],
                marker="o",
                color=palette["chart"],
                label=self._civ_label(state),
            )
        ax_soma.set_title("Soma over turns")
        ax_soma.set_xlabel("Turn")
        ax_soma.set_ylabel("Soma")
        if has_history:
            ax_soma.legend()

        ax_pop = self._figure.add_subplot(312)
        for idx, state in enumerate(self._civ_states):
            history = self._history.get(state.civilization.id, [])
            if not history:
                continue
            palette = CIV_PALETTES[idx % len(CIV_PALETTES)]
            ax_pop.plot(
                [h.turn_number for h in history],
                [h.pop_end for h in history],
                marker="o",
                color=palette["chart"],
                label=self._civ_label(state),
            )
        ax_pop.set_title("Population over turns")
        ax_pop.set_xlabel("Turn")
        ax_pop.set_ylabel("Rakshas")
        if has_history:
            ax_pop.legend()

        ax_genes = self._figure.add_subplot(313)
        genes = list(GeneType)
        gene_labels = [g.name for g in genes]
        x_positions = list(range(len(genes)))
        civ_count = len(self._civ_states)
        offsets = [
            (idx - (civ_count - 1) / 2) * _BAR_WIDTH
            for idx in range(civ_count)
        ]

        for idx, state in enumerate(self._civ_states):
            counts = self._gene_counts(state)
            palette = CIV_PALETTES[idx % len(CIV_PALETTES)]
            positions = [x + offsets[idx] for x in x_positions]
            vals = [counts[g] for g in genes]
            ax_genes.bar(
                positions,
                vals,
                width=_BAR_WIDTH,
                color=palette["chart"],
                label=self._civ_label(state),
            )

        ax_genes.set_title("Gene breakdown (dominant)")
        ax_genes.set_ylabel("Count")
        ax_genes.set_xticks(x_positions)
        ax_genes.set_xticklabels(gene_labels)
        ax_genes.legend()

        self._figure.tight_layout()
        self._canvas.draw()
