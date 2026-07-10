"""Tkinter Plot tab with labyrinth and civilization maps."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from labyrinth.domain.entities import CivilizationStatus, Epoch, TripResult
from labyrinth.domain.types import CENTER_SQUARES, LABYRINTH_SIZE
from labyrinth.engine.labyrinth import Labyrinth

# Distinct palettes per civilization for the combined overlay map.
CIV_PALETTES: tuple[dict[str, str], ...] = (
    {"free": "#3498db", "trap": "#e74c3c", "center": "#f39c12"},
    {"free": "#2ecc71", "trap": "#9b59b6", "center": "#e67e22"},
)


class PlotTab(ttk.Frame):
    """Spectator plot tab with actual labyrinth and per-civ uncovered maps."""

    def __init__(self, master, labyrinth: Labyrinth, civilizations: list) -> None:
        super().__init__(master)
        self._labyrinth = labyrinth
        self._civ_states = civilizations
        self._turn_var = tk.StringVar(value="Turn 0")
        self._epoch_var = tk.StringVar(value="Epoch: —")
        self._status_var = tk.StringVar(value="")
        self._current_epoch: Epoch | None = None
        self._stopped = False
        self._turn_busy = False
        self._auto_after_id: str | None = None
        self._next_turn_callback = None
        self._civ_stat_labels: list[ttk.Label] = []
        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(header, textvariable=self._turn_var).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self._epoch_var).pack(side=tk.LEFT, padx=12)
        ttk.Label(header, textvariable=self._status_var).pack(side=tk.LEFT, padx=12)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body)
        body.add(left, weight=2)
        ttk.Label(left, text="Actual Labyrinth").pack()
        self._actual_canvas = tk.Canvas(left, bg="#1a1a2e", highlightthickness=0)
        self._actual_canvas.pack(fill=tk.BOTH, expand=True)
        self._actual_canvas.bind("<Configure>", self._on_actual_canvas_resize)

        right = ttk.LabelFrame(body, text="Uncovered Maps (all civilizations)")
        body.add(right, weight=3)

        stats = ttk.Frame(right)
        stats.pack(fill=tk.X, padx=4, pady=4)
        for idx, state in enumerate(self._civ_states):
            palette = CIV_PALETTES[idx % len(CIV_PALETTES)]
            row = ttk.Frame(stats)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(
                row,
                text="■",
                foreground=palette["free"],
                font=("", 14),
            ).pack(side=tk.LEFT)
            label = ttk.Label(row, text=self._stats_text(state))
            label.pack(side=tk.LEFT, padx=4)
            self._civ_stat_labels.append(label)

        self._overlay_canvas = tk.Canvas(right, bg="#16213e", highlightthickness=0)
        self._overlay_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._overlay_canvas.bind("<Configure>", self._on_overlay_canvas_resize)

        legend = ttk.Frame(right)
        legend.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Label(legend, text="Overlay: each civ uses its own color; shared squares are split.").pack(
            anchor=tk.W
        )

        controls = ttk.Frame(self)
        controls.pack(fill=tk.X, padx=4, pady=4)
        self._next_btn = ttk.Button(controls, text="Next Turn")
        self._next_btn.pack(side=tk.LEFT)
        self._auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Auto-advance", variable=self._auto_var).pack(
            side=tk.LEFT, padx=8
        )
        self._stop_btn = ttk.Button(controls, text="Stop Simulation")
        self._stop_btn.pack(side=tk.LEFT, padx=8)
        self._reset_btn = ttk.Button(controls, text="Reset Simulation")
        self._reset_btn.pack(side=tk.LEFT)

    def bind_next_turn(self, callback) -> None:
        """Wire Next Turn button to game.next_turn()."""
        self._next_turn_callback = callback
        self._next_btn.configure(command=self._on_next_turn_clicked)

    def bind_stop(self, callback) -> None:
        """Wire Stop Simulation button."""
        self._stop_btn.configure(command=callback)

    def bind_reset(self, callback) -> None:
        """Wire Reset Simulation button."""
        self._reset_btn.configure(command=callback)

    def set_turn_busy(self, busy: bool, status: str = "") -> None:
        """Lock Next Turn and Reset while a turn runs on a background thread."""
        self._turn_busy = busy
        self._status_var.set(status if busy else "")
        if busy:
            self._next_btn.configure(state=tk.DISABLED)
            self._reset_btn.configure(state=tk.DISABLED)
        elif not self._stopped:
            self._next_btn.configure(state=tk.NORMAL)
            self._reset_btn.configure(state=tk.NORMAL)
        else:
            self._next_btn.configure(state=tk.DISABLED)
            self._reset_btn.configure(state=tk.NORMAL)

    def set_stopped(self, stopped: bool) -> None:
        """Pause turn advancement; Reset stays available when no turn is running."""
        self._stopped = stopped
        if stopped:
            self.cancel_auto_advance()
            self._next_btn.configure(state=tk.DISABLED)
            if not self._turn_busy:
                self._reset_btn.configure(state=tk.NORMAL)
        elif not self._turn_busy:
            self._next_btn.configure(state=tk.NORMAL)
            self._reset_btn.configure(state=tk.NORMAL)

    def cancel_auto_advance(self) -> None:
        """Cancel any scheduled auto-advance turn."""
        if self._auto_after_id is not None:
            self.after_cancel(self._auto_after_id)
            self._auto_after_id = None

    def reset_view(
        self,
        labyrinth: Labyrinth,
        civilizations: list,
    ) -> None:
        """Rebind labyrinth/civ data and clear the plot view."""
        self.cancel_auto_advance()
        self._stopped = False
        self._labyrinth = labyrinth
        self._civ_states = civilizations
        self._current_epoch = None
        self._turn_var.set("Turn 0")
        self._epoch_var.set("Epoch: —")
        self._actual_canvas.delete("all")
        self._overlay_canvas.delete("all")

    def _on_next_turn_clicked(self) -> None:
        if self._stopped or self._turn_busy or not self._next_turn_callback:
            return
        self.cancel_auto_advance()
        self._next_turn_callback()

    def schedule_auto_advance(self) -> None:
        """Schedule the next turn when auto-advance is enabled."""
        self.cancel_auto_advance()
        if (
            self._stopped
            or not self._auto_var.get()
            or not self._next_turn_callback
        ):
            return
        self._auto_after_id = self.after(1500, self._auto_advance_tick)

    def _auto_advance_tick(self) -> None:
        self._auto_after_id = None
        if self._stopped or self._turn_busy or not self._auto_var.get() or not self._next_turn_callback:
            return
        self._next_turn_callback()

    def _stats_text(self, state) -> str:
        civ = state.civilization
        if civ.status == CivilizationStatus.EXTINCT:
            return f"{civ.name}: EXTINCT  Soma: {civ.soma}"
        alive = len([r for r in civ.rakshas if r.alive])
        return f"{civ.name}: Soma {civ.soma}  Rakshas {alive}"

    def draw_initial_state(self) -> None:
        """Draw labyrinth and civ stats before the first turn runs."""
        self._turn_var.set("Turn 0")
        epoch = self._labyrinth.current_epoch
        if epoch:
            self._current_epoch = epoch
            self._epoch_var.set(
                f"Epoch: {epoch.dominant_type.name}  ({epoch.turns_remaining} turns left)"
            )
            self._draw_actual_labyrinth()
        self._refresh_civ_stats()
        self._refresh_overlay_map()

    def on_turn_start(self, turn: int, epoch: Epoch) -> None:
        self._turn_var.set(f"Turn {turn}")
        self._current_epoch = epoch
        self._epoch_var.set(
            f"Epoch: {epoch.dominant_type.name}  ({epoch.turns_remaining} turns left)"
        )
        self._draw_actual_labyrinth()

    def on_trip_result(self, civ_id: str, result: TripResult) -> None:
        self._refresh_overlay_map()

    def on_turn_end(self, summaries) -> None:
        self._refresh_civ_stats()
        self._refresh_overlay_map()

    def _on_actual_canvas_resize(self, _event: tk.Event) -> None:
        if self._current_epoch is not None:
            self._draw_actual_labyrinth()

    def _on_overlay_canvas_resize(self, _event: tk.Event) -> None:
        self._refresh_overlay_map()

    def _cell_size(self, canvas: tk.Canvas) -> float:
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        return min(width, height) / LABYRINTH_SIZE

    def _draw_actual_labyrinth(self) -> None:
        canvas = self._actual_canvas
        canvas.delete("all")
        cell = self._cell_size(canvas)
        colors = {"FIRE": "#e74c3c", "WATER": "#3498db", "EARTH": "#27ae60", "AIR": "#f1c40f"}
        for (x, y), trap in self._labyrinth.grid.items():
            if trap is None:
                color = "#2c3e50" if (x, y) in CENTER_SQUARES else "#1a1a2e"
            else:
                color = colors.get(trap.name, "#888")
            canvas.create_rectangle(
                x * cell,
                y * cell,
                (x + 1) * cell,
                (y + 1) * cell,
                fill=color,
                outline="",
            )

    def _refresh_civ_stats(self) -> None:
        for idx, state in enumerate(self._civ_states):
            if idx < len(self._civ_stat_labels):
                self._civ_stat_labels[idx].configure(text=self._stats_text(state))

    def _refresh_overlay_map(self) -> None:
        canvas = self._overlay_canvas
        canvas.delete("all")
        cell = self._cell_size(canvas)

        square_entries: dict[tuple[int, int], list[tuple[int, object]]] = {}
        for civ_idx, state in enumerate(self._civ_states):
            for coord, record in state.civilization.known_map.items():
                square_entries.setdefault(coord, []).append((civ_idx, record))

        for (x, y), entries in square_entries.items():
            if len(entries) == 1:
                civ_idx, record = entries[0]
                color = self._record_color(civ_idx, record)
                canvas.create_rectangle(
                    x * cell,
                    y * cell,
                    (x + 1) * cell,
                    (y + 1) * cell,
                    fill=color,
                    outline="",
                )
                continue

            slice_width = cell / len(entries)
            for slice_idx, (civ_idx, record) in enumerate(entries):
                color = self._record_color(civ_idx, record)
                x0 = x * cell + slice_idx * slice_width
                canvas.create_rectangle(
                    x0,
                    y * cell,
                    x0 + slice_width,
                    (y + 1) * cell,
                    fill=color,
                    outline="",
                )

    def _record_color(self, civ_idx: int, record) -> str:
        palette = CIV_PALETTES[civ_idx % len(CIV_PALETTES)]
        if record.is_center:
            return palette["center"]
        if record.trap_type is None:
            return palette["free"]
        return palette["trap"]
