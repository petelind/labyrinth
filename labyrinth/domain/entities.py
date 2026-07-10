"""Domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from labyrinth.domain.types import Criterion, GeneType

if TYPE_CHECKING:
    from labyrinth.narrative import TurnChronicler


class CivilizationStatus(Enum):
    """Lifecycle state of a civilization."""

    ACTIVE = "active"
    EXTINCT = "extinct"


@dataclass
class DNA:
    """Three-gene resistance profile for a Raksha."""

    dominant: GeneType
    secondary: GeneType
    recessive: GeneType


@dataclass
class Raksha:
    """A single member of a Civilization."""

    id: UUID
    civilization_id: str
    dna: DNA
    alive: bool = True
    trips_completed: int = 0
    trips_survived: int = 0
    parent_a_id: UUID | None = None
    parent_b_id: UUID | None = None


@dataclass
class SquareRecord:
    """What a Civilization knows about one labyrinth square."""

    x: int
    y: int
    trap_type: GeneType | None
    is_center: bool = False


@dataclass
class Travelog:
    """Record of a single labyrinth trip."""

    raksha_id: UUID
    path: list[tuple[int, int]]
    squares: dict[tuple[int, int], SquareRecord]
    soma_gathered: int
    survived: bool
    hit_step_limit: bool = False


@dataclass
class Epoch:
    """Current labyrinth epoch with dominant trap type."""

    dominant_type: GeneType
    turns_remaining: int
    length: int


@dataclass(frozen=True)
class Route:
    """
    Criteria-mapped path for labyrinth trips.

    First matching route wins when resolving send pool members.

    :param criteria: AND-ed filter rules; must be non-empty.
    :param path: Validated cardinal path starting on the perimeter.
    """

    criteria: tuple[Criterion, ...]
    path: tuple[tuple[int, int], ...]


@dataclass
class StandingOrders:
    """
    Orders the game engine executes at the turn boundary.

    Safe fallback: if ``last_updated_turn`` does not match the current turn,
    Game re-uses the previous turn's orders verbatim.
    """

    weed_criteria: list[Criterion] = field(default_factory=list)
    send_criteria: list[Criterion] = field(default_factory=list)
    reproduce_criteria: list[Criterion] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    current_strategy_sumup: str = ""
    last_updated_turn: int = -1


@dataclass
class TurnContext:
    """Read-only snapshot passed to Strategy.decide() each turn."""

    turn_number: int
    soma: int
    rakshas: list[Raksha]
    recent_travelogs: list[Travelog]
    known_map: dict[tuple[int, int], SquareRecord]
    turns_remaining: int
    chronicler: TurnChronicler | None = None
    civilization_id: str = ""
    civilization_name: str = ""


@dataclass
class TurnSummary:
    """Per-civilization summary recorded at end of each turn."""

    turn_number: int
    civilization_id: str
    soma_start: int
    soma_end: int
    pop_start: int
    pop_end: int
    deaths: int
    trips_sent: int
    trips_survived: int
    soma_gathered: int
    strategy_sumup: str
    strategy_thinking: str = ""
    went_extinct: bool = False


@dataclass
class TripResult:
    """Outcome of a single Raksha labyrinth trip."""

    raksha_id: UUID
    travelog: Travelog
    died: bool


@dataclass
class Civilization:
    """A competing civilization with strategy, soma, and Rakshas."""

    id: str
    name: str
    soma: int
    rakshas: list[Raksha]
    known_map: dict[tuple[int, int], SquareRecord] = field(default_factory=dict)
    recent_travelogs: list[Travelog] = field(default_factory=list)
    status: CivilizationStatus = CivilizationStatus.ACTIVE
    extinct_turn: int | None = None


@dataclass
class GameEvents:
    """Callback hooks decoupling engine from GUI."""

    on_turn_start: object = None
    on_trip_result: object = None
    on_turn_end: object = None
    on_game_end: object = None
    on_chapter: object = None
    on_civilization_extinct: object = None

    def __post_init__(self) -> None:
        if self.on_turn_start is None:
            self.on_turn_start = lambda *_: None
        if self.on_trip_result is None:
            self.on_trip_result = lambda *_: None
        if self.on_turn_end is None:
            self.on_turn_end = lambda *_: None
        if self.on_game_end is None:
            self.on_game_end = lambda *_: None
        if self.on_chapter is None:
            self.on_chapter = lambda *_: None
        if self.on_civilization_extinct is None:
            self.on_civilization_extinct = lambda *_: None
