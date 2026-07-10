"""Tkinter Commentary tab with strategy decision log."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import scrolledtext, ttk

from labyrinth.domain.entities import TurnSummary


class CommentaryLogHandler(logging.Handler):
    """Route structlog/log records to a tk.Text widget."""

    def __init__(self, text_widget: scrolledtext.ScrolledText) -> None:
        super().__init__()
        self._widget = text_widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self._widget.after(0, self._append, msg)

    def _append(self, msg: str) -> None:
        self._widget.configure(state=tk.NORMAL)
        self._widget.insert(tk.END, msg + "\n")
        self._widget.see(tk.END)
        self._widget.configure(state=tk.DISABLED)


class CommentaryTab(ttk.Frame):
    """Decision-making log from strategies, turn over turn."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self._build()

    def _build(self) -> None:
        nav = ttk.Frame(self)
        nav.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(nav, text="Strategy Commentary").pack(side=tk.LEFT)
        ttk.Button(nav, text="Save Game", command=self._save_placeholder).pack(side=tk.RIGHT)

        self._text = scrolledtext.ScrolledText(self, state=tk.DISABLED, height=30)
        self._text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        handler = CommentaryLogHandler(self._text)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logging.getLogger().addHandler(handler)

    def on_turn_end(self, summaries: list[TurnSummary]) -> None:
        self._text.configure(state=tk.NORMAL)
        for s in summaries:
            self._text.insert(
                tk.END,
                f"[T{s.turn_number}] {s.civilization_id} — "
                f"Soma {s.soma_start}→{s.soma_end}, "
                f"Pop {s.pop_start}→{s.pop_end}, "
                f"Trips {s.trips_sent}/{s.trips_survived} survived\n",
            )
        self._text.see(tk.END)
        self._text.configure(state=tk.DISABLED)

    def on_chapter(self, chapter_text: str) -> None:
        """Append a full turn narrative chapter."""
        self._text.configure(state=tk.NORMAL)
        self._text.insert(tk.END, chapter_text + "\n")
        self._text.see(tk.END)
        self._text.configure(state=tk.DISABLED)

    def reset_view(self) -> None:
        """Clear commentary log."""
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.configure(state=tk.DISABLED)

    def _save_placeholder(self) -> None:
        self._text.configure(state=tk.NORMAL)
        self._text.insert(tk.END, "[Save] Game persisted by engine on each turn.\n")
        self._text.configure(state=tk.DISABLED)
