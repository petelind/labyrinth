"""Tkinter Plot tab with labyrinth and civilization maps."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from labyrinth.domain.entities import CivilizationStatus, Epoch, TripResult
from labyrinth.domain.types import CENTER_SQUARES, LABYRINTH_SIZE
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.gui.civ_palette import CIV_PALETTES


class _PairedMapCanvases(ttk.Frame):
    """Two labyrinth canvases forced to the same square size."""

    def __init__(self, master, actual_bg: str, overlay_bg: str) -> None:
        super().__init__(master)
        self._actual_canvas = tk.Canvas(self, bg=actual_bg, highlightthickness=0)
        self._overlay_canvas = tk.Canvas(self, bg=overlay_bg, highlightthickness=0)
        self.bind("<Configure>", self._on_resize)

    @property
    def actual_canvas(self) -> tk.Canvas:
        return self._actual_canvas

    @property
    def overlay_canvas(self) -> tk.Canvas:
        return self._overlay_canvas

    def _on_resize(self, event: tk.Event) -> None:
        half_width = max(event.width // 2, 1)
        side = max(min(half_width, event.height), 1)
        y0 = (event.height - side) // 2
        left_x0 = (half_width - side) // 2
        right_x0 = half_width + (half_width - side) // 2
        self._actual_canvas.place(x=left_x0, y=y0, width=side, height=side)
        self._overlay_canvas.place(x=right_x0, y=y0, width=side, height=side)


class PlotTab(ttk.Frame):
    """Spectator plot tab with actual labyrinth and per-civ uncovered maps."""

    def __init__(
        self,
        master,
        labyrinth: Labyrinth,
        civilizations: list,
        auto_advance_ms: int = 1500,
    ) -> None:
        super().__init__(master)
        self._labyrinth = labyrinth
        self._civ_states = civilizations
        self._auto_advance_ms = auto_advance_ms
        self._turn_var = tk.StringVar(value="Turn 0")
        self._epoch_var = tk.StringVar(value="Epoch: —")
        self._status_var = tk.StringVar(value="")
        self._current_epoch: Epoch | None = None
        self._stopped = False
        self._turn_busy = False
        self._is_replay_mode: bool = False
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

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        maps = ttk.Frame(body)
        maps.pack(fill=tk.BOTH, expand=True)
        maps.columnconfigure(0, weight=1, uniform="map")
        maps.columnconfigure(1, weight=1, uniform="map")
        maps.rowconfigure(2, weight=1)

        ttk.Label(maps, text="Actual Labyrinth").grid(row=0, column=0, pady=(0, 4))
        ttk.Label(maps, text="Uncovered Maps (all civilizations)").grid(
            row=0, column=1, pady=(0, 4),
        )

        ttk.Frame(maps).grid(row=1, column=0)

        stats = ttk.Frame(maps)
        stats.grid(row=1, column=1, sticky=tk.W, pady=(0, 4))
        for idx, state in enumerate(self._civ_states):
            palette = CIV_PALETTES[idx % len(CIV_PALETTES)]
            row = ttk.Frame(stats)
            row.pack(side=tk.LEFT, padx=(0, 16))
            ttk.Label(
                row,
                text="■",
                foreground=palette["free"],
                font=("", 14),
            ).pack(side=tk.LEFT)
            label = ttk.Label(row, text=self._stats_text(state))
            label.pack(side=tk.LEFT, padx=4)
            self._civ_stat_labels.append(label)

        self._map_pair = _PairedMapCanvases(maps, actual_bg="#1a1a2e", overlay_bg="#16213e")
        self._map_pair.grid(row=2, column=0, columnspan=2, sticky=tk.NSEW)
        self._actual_canvas = self._map_pair.actual_canvas
        self._overlay_canvas = self._map_pair.overlay_canvas
        self._actual_canvas.bind("<Configure>", self._on_actual_canvas_resize)
        self._overlay_canvas.bind("<Configure>", self._on_overlay_canvas_resize)

        legend = ttk.Frame(maps)
        legend.grid(row=3, column=1, sticky=tk.W, pady=(4, 0))
        ttk.Label(
            legend,
            text="Overlay: each civ uses its own color; shared squares are split.",
        ).pack(anchor=tk.W)

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

    def set_replay_mode(self, is_replay: bool) -> None:
        """Switch the button label between 'Next Turn' and 'Replay Turn'."""
        self._is_replay_mode = is_replay
        label = "Replay Turn" if is_replay else "Next Turn"
        self._next_btn.configure(text=label)

    def bind_next_turn(self, callback) -> None:
        """Wire Next/Replay Turn button to the given callback."""
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
        self._auto_after_id = self.after(self._auto_advance_ms, self._auto_advance_tick)

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
        colors = {"FIRE": "#c0392b", "WATER": "#154360", "EARTH": "#7b4a1e", "AIR": "#aed6f1"}
        for (x, y), trap in self._labyrinth.grid.items():
            if trap is None:
                color = "#ffffff" if (x, y) in CENTER_SQUARES else "#1a1a2e"
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

    @property
    def turn_label(self) -> tk.StringVar:
        """Turn counter label variable (for E2E assertions)."""
        return self._turn_var

    @property
    def epoch_label(self) -> tk.StringVar:
        """Epoch label variable."""
        return self._epoch_var

    @property
    def status_var(self) -> tk.StringVar:
        """In-progress status label variable."""
        return self._status_var

    @property
    def auto_advance_var(self) -> tk.BooleanVar:
        """Auto-advance checkbox variable."""
        return self._auto_var

    @property
    def next_button(self) -> ttk.Button:
        """Next Turn button widget."""
        return self._next_btn

    @property
    def stop_button(self) -> ttk.Button:
        """Stop Simulation button widget."""
        return self._stop_btn

    @property
    def reset_button(self) -> ttk.Button:
        """Reset Simulation button widget."""
        return self._reset_btn

    def _record_color(self, civ_idx: int, record) -> str:
        palette = CIV_PALETTES[civ_idx % len(CIV_PALETTES)]
        if record.is_center:
            return palette["center"]
        if record.trap_type is None:
            return palette["free"]
        return palette["trap"]
