"""Tkinter Commentary tab with strategy decision log."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import scrolledtext, ttk

from labyrinth.domain.entities import TurnSummary


class CommentaryLogHandler(logging.Handler):
    """Route structlog/log records to a tk.Text widget."""

    def __init__(
        self,
        text_widget: scrolledtext.ScrolledText,
        dispatch: object | None = None,
    ) -> None:
        super().__init__()
        self._widget = text_widget
        self._dispatch = dispatch

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        if self._dispatch is not None:
            self._dispatch(self._append, msg)
        else:
            self._widget.after(0, self._append, msg)

    def _append(self, msg: str) -> None:
        self._widget.configure(state=tk.NORMAL)
        self._widget.insert(tk.END, msg + "\n")
        self._widget.see(tk.END)
        self._widget.configure(state=tk.DISABLED)


class CommentaryTab(ttk.Frame):
    """Decision-making log from strategies, turn over turn."""

    def __init__(
        self,
        master,
        log_dispatch: object | None = None,
        enable_log_handler: bool = True,
    ) -> None:
        super().__init__(master)
        self._log_dispatch = log_dispatch
        self._enable_log_handler = enable_log_handler
        self._build()

    def _build(self) -> None:
        nav = ttk.Frame(self)
        nav.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(nav, text="Strategy Commentary").pack(side=tk.LEFT)
        self._save_btn = ttk.Button(nav, text="Save Game")
        self._save_btn.pack(side=tk.RIGHT)
        self._load_btn = ttk.Button(nav, text="Load Game")
        self._load_btn.pack(side=tk.RIGHT, padx=(0, 4))

        self._text = scrolledtext.ScrolledText(self, state=tk.DISABLED, height=30)
        self._text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        handler = CommentaryLogHandler(self._text, dispatch=self._log_dispatch)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        if self._enable_log_handler:
            logging.getLogger().addHandler(handler)

    def bind_save(self, callback) -> None:
        """Wire Save Game button to an export callback."""
        self._save_btn.configure(command=callback)

    def bind_load(self, callback) -> None:
        """Wire Load Game button to an import/replay callback."""
        self._load_btn.configure(command=callback)

    @property
    def save_button(self) -> ttk.Button:
        """Save Game button widget."""
        return self._save_btn

    @property
    def load_button(self) -> ttk.Button:
        """Load Game button widget."""
        return self._load_btn

    def append_message(self, message: str) -> None:
        """Append a line to the commentary log."""
        self._text.configure(state=tk.NORMAL)
        self._text.insert(tk.END, message + "\n")
        self._text.see(tk.END)
        self._text.configure(state=tk.DISABLED)

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
        self.append_message(chapter_text.rstrip("\n"))

    def reset_view(self) -> None:
        """Clear commentary log."""
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.configure(state=tk.DISABLED)
