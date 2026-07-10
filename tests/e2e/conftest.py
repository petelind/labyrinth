"""E2E GUI test helpers — programmatic Tk control (no pixel automation)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from labyrinth.gui.app import LabyrinthApp


def poll_until(
    predicate: Callable[[], bool],
    app: LabyrinthApp,
    timeout: float = 30.0,
    interval: float = 0.05,
) -> None:
    """
    Pump the Tk event loop until predicate is true or timeout expires.

    :param predicate: Callable returning True when condition met.
    :param app: Tk application root.
    :param timeout: Max seconds to wait.
    :param interval: Sleep between update() calls.
    :raises TimeoutError: When predicate never becomes true.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if hasattr(app, "process_pending"):
            app.process_pending()
        app.update_idletasks()
        app.update()
        if predicate():
            return
        time.sleep(interval)
    raise TimeoutError(f"Condition not met within {timeout}s")


class GuiHarness:
    """Drive LabyrinthApp for E2E tests without widget-tree walking."""

    def __init__(self, app: LabyrinthApp) -> None:
        self._app = app

    def tick(self) -> None:
        """Process pending Tk events once."""
        self._app.process_pending()
        self._app.update_idletasks()
        self._app.update()

    def start(self, turns: int = 5) -> None:
        """Set turn count and start the simulation."""
        self._app.turns_var.set(turns)
        self._app.start_simulation()
        self.tick()

    def next_turn(self) -> None:
        """Trigger one turn via the public API."""
        self._app.next_turn()
        self.tick()

    def enable_auto_advance(self) -> None:
        """Check auto-advance and schedule the next turn if idle."""
        plot = self._app.plot_tab
        if plot is None:
            raise RuntimeError("Plot tab not available — start simulation first")
        plot.auto_advance_var.set(True)
        if not self._app.turn_in_progress:
            plot.schedule_auto_advance()
        self.tick()

    def wait_until_turn(self, turn_number: int, timeout: float = 30.0) -> None:
        """Block until game.current_turn reaches turn_number."""
        poll_until(
            lambda: self._app.game is not None and self._app.game.current_turn >= turn_number,
            self._app,
            timeout=timeout,
        )

    def wait_until_idle(self, timeout: float = 30.0) -> None:
        """Block until no background turn worker is running."""
        poll_until(
            lambda: not self._app.turn_in_progress,
            self._app,
            timeout=timeout,
        )


@pytest.fixture
def gui_app(tmp_path):
    """
    Fast GenAlg-only LabyrinthApp for E2E tests.

    :param tmp_path: pytest temporary directory for SQLite save file.
    :yield: Configured LabyrinthApp instance.
    """
    from labyrinth.gui.app import LabyrinthApp

    db_path = tmp_path / "test.db"
    app = LabyrinthApp(test_mode=True, db_path=db_path)
    yield app
    try:
        app.destroy()
    except Exception:
        pass


@pytest.fixture
def harness(gui_app: LabyrinthApp) -> GuiHarness:
    """GuiHarness bound to the E2E app fixture."""
    return GuiHarness(gui_app)
