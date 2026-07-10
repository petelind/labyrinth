"""Replay engine: drives GameEvents from a list of persisted ReplayFrames."""

from __future__ import annotations

from uuid import uuid4

from labyrinth.domain.entities import (
    Civilization,
    CivilizationStatus,
    DNA,
    Epoch,
    GameEvents,
    Raksha,
    TurnSummary,
)
from labyrinth.domain.types import GeneType
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.logging_config import get_logger
from labyrinth.persistence.repo import ReplayFrame

log = get_logger(__name__)

_DUMMY_DNA = DNA(dominant=GeneType.FIRE, secondary=GeneType.FIRE, recessive=GeneType.FIRE)


class ReplayPlayer:
    """
    Advances a loaded save file turn-by-turn via GameEvents callbacks.

    On each ``advance()`` call the player:

    1. Updates the shared ``Labyrinth`` grid and epoch.
    2. Updates each ``Civilization``'s known_map, soma, status and rakshas count.
    3. Fires ``GameEvents.on_turn_start`` then ``GameEvents.on_turn_end``.

    This lets the existing GUI handlers (PlotTab, CivsTab, CommentaryTab) display
    the replay identically to a live run — without re-simulating anything.

    :param frames: Ordered list of replay frames (one per persisted turn).
    :param labyrinth: Live Labyrinth object shared with the GUI.
    :param civ_map: Mapping of civ_id → Civilization objects shared with the GUI.
    :param events: GameEvents instance wired to the GUI.
    """

    def __init__(
        self,
        frames: list[ReplayFrame],
        labyrinth: Labyrinth,
        civ_map: dict[str, Civilization],
        events: GameEvents,
    ) -> None:
        if not frames:
            raise ValueError("ReplayPlayer requires at least one frame.")
        self._frames = frames
        self._labyrinth = labyrinth
        self._civ_map = civ_map
        self._events = events
        self._current_idx: int = 0

    @property
    def has_next(self) -> bool:
        """True while there are un-replayed turns."""
        return self._current_idx < len(self._frames)

    @property
    def total_turns(self) -> int:
        """Total number of recorded turns available for replay."""
        return len(self._frames)

    @property
    def current_idx(self) -> int:
        """Index of the next frame to be replayed (0-based)."""
        return self._current_idx

    def advance(self) -> list[TurnSummary]:
        """
        Replay the next turn: mutate shared state, fire events.

        :return: Summaries for the replayed turn.
        :raises StopIteration: If all frames have already been replayed.
        """
        if not self.has_next:
            raise StopIteration("All replay frames exhausted.")

        frame = self._frames[self._current_idx]
        self._current_idx += 1

        epoch = self._apply_frame(frame)

        if self._events.on_turn_start:
            self._events.on_turn_start(frame.turn_number, epoch)
        if self._events.on_turn_end:
            self._events.on_turn_end(frame.summaries)

        log.debug("replay.turn_advanced", turn=frame.turn_number, idx=self._current_idx)
        return frame.summaries

    def _apply_frame(self, frame: ReplayFrame) -> Epoch:
        """Mutate labyrinth and civilization objects to match the frame state."""
        epoch = Epoch(
            dominant_type=frame.epoch_dominant,
            turns_remaining=frame.epoch_turns_remaining,
            length=frame.epoch_length,
        )
        self._labyrinth.grid = dict(frame.grid)
        self._labyrinth.current_epoch = epoch

        for summary in frame.summaries:
            civ = self._civ_map.get(summary.civilization_id)
            if civ is None:
                continue
            civ.soma = summary.soma_end
            civ.status = (
                CivilizationStatus.EXTINCT
                if summary.went_extinct
                else CivilizationStatus.ACTIVE
            )
            # Replace raksha list with pop_end dummy alive members for stats display.
            civ.rakshas = [
                Raksha(id=uuid4(), civilization_id=civ.id, dna=_DUMMY_DNA)
                for _ in range(summary.pop_end)
            ]

        for civ_id, known_map in frame.known_maps.items():
            civ = self._civ_map.get(civ_id)
            if civ is not None:
                civ.known_map = dict(known_map)

        return epoch
