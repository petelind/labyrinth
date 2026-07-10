"""Labyrinth grid generation and trip resolution."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from labyrinth.domain.entities import Epoch, Raksha, SquareRecord, Travelog, TripResult
from labyrinth.domain.grid import (
    is_perimeter_square,
    random_perimeter_start,
    validate_prescribed_path,
)
from labyrinth.domain.types import (
    CENTER_SQUARES,
    GeneType,
    LABYRINTH_SIZE,
    TRIP_MAX_STEPS,
)
from labyrinth.logging_config import get_logger

log = get_logger(__name__)

TRAP_DENSITY = 0.025
DOMINANT_TRAP_RATIO = 0.75
SOMA_REWARD_MIN = 25
SOMA_REWARD_MAX = 100


@dataclass
class Labyrinth:
    """
    100x100 labyrinth with epoch-fixed trap distribution.

    Trap layout is generated at epoch start and remains static until
    ``advance_epoch`` is called.
    """

    grid: dict[tuple[int, int], GeneType | None] = field(default_factory=dict)
    current_epoch: Epoch | None = None
    _rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        """No-op; grid is built by ``create`` or ``advance_epoch``."""

    @classmethod
    def create(cls, rng: random.Random, dominant: GeneType | None = None) -> Labyrinth:
        """
        Create a labyrinth with a new epoch.

        :param rng: Injectable RNG.
        :param dominant: Optional fixed dominant type; random if None.
        :return: Initialized labyrinth.
        """
        if dominant is None:
            dominant = rng.choice(list(GeneType))
        length = rng.randint(5, 10)
        epoch = Epoch(dominant_type=dominant, turns_remaining=length, length=length)
        lab = cls(grid={}, current_epoch=epoch, _rng=rng)
        lab._generate_grid(dominant)
        log.info(
            "labyrinth.created",
            dominant=dominant.name,
            epoch_length=length,
        )
        return lab

    def _generate_grid(self, dominant: GeneType) -> None:
        """
        Generate trap layout fixed for the current epoch.

        ``TRAP_DENSITY`` of all squares hold traps; ``DOMINANT_TRAP_RATIO``
        of those traps match the epoch dominant type. Center squares are
        always free.
        """
        others = [g for g in GeneType if g != dominant]
        total = LABYRINTH_SIZE * LABYRINTH_SIZE
        trap_count = int(total * TRAP_DENSITY)
        dominant_trap_count = int(trap_count * DOMINANT_TRAP_RATIO)
        self.grid = {
            (x, y): None
            for x in range(LABYRINTH_SIZE)
            for y in range(LABYRINTH_SIZE)
        }
        candidates = [
            (x, y)
            for x in range(LABYRINTH_SIZE)
            for y in range(LABYRINTH_SIZE)
            if (x, y) not in CENTER_SQUARES
        ]
        self._rng.shuffle(candidates)
        for i, pos in enumerate(candidates[:trap_count]):
            if i < dominant_trap_count:
                self.grid[pos] = dominant
            else:
                self.grid[pos] = self._rng.choice(others)
        counts: dict[str, int] = {}
        for trap in self.grid.values():
            key = trap.name if trap is not None else "FREE"
            counts[key] = counts.get(key, 0) + 1
        trapped = sum(v for k, v in counts.items() if k != "FREE")
        log.info(
            "labyrinth.grid_generated",
            dominant=dominant.name,
            squares=len(self.grid),
            trap_pct=round(100 * trapped / total, 2),
            free_pct=round(100 * counts.get("FREE", 0) / total, 2),
            dominant_trap_pct_of_traps=round(100 * dominant_trap_count / trap_count, 2) if trap_count else 0,
            breakdown={k: round(100 * v / total, 2) for k, v in sorted(counts.items())},
        )

    def get_trap(self, x: int, y: int) -> GeneType | None:
        """Return trap type at (x,y) or None for free/center."""
        return self.grid.get((x, y))

    def resolve_trap(
        self,
        raksha: Raksha,
        trap: GeneType | None,
        rng: random.Random,
    ) -> bool:
        """
        Resolve trap encounter. Return True if Raksha survives.

        :param raksha: Raksha stepping on the square.
        :param trap: Trap type or None for free passage.
        :param rng: Injectable RNG for die roll.
        :return: True if Raksha survives.
        """
        if trap is None:
            log.debug("trap.resolved", raksha_id=str(raksha.id), trap=None, outcome="free")
            return True

        roll = rng.random()
        if raksha.dna.dominant == trap:
            log.debug(
                "trap.resolved",
                raksha_id=str(raksha.id),
                trap=trap.name,
                resistance="dominant",
                roll=roll,
                outcome="survived",
            )
            return True
        if raksha.dna.secondary == trap:
            survived = roll >= 0.25
            log.debug(
                "trap.resolved",
                raksha_id=str(raksha.id),
                trap=trap.name,
                resistance="secondary",
                roll=roll,
                outcome="survived" if survived else "died",
            )
            return survived
        survived = roll >= 0.50
        log.debug(
            "trap.resolved",
            raksha_id=str(raksha.id),
            trap=trap.name,
            resistance="none",
            roll=roll,
            outcome="survived" if survived else "died",
        )
        return survived

    def _naive_step(
        self,
        x: int,
        y: int,
        rng: random.Random,
    ) -> tuple[int, int]:
        """Move one cardinal step, clamped to grid bounds."""
        dx, dy = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
        nx = max(0, min(LABYRINTH_SIZE - 1, x + dx))
        ny = max(0, min(LABYRINTH_SIZE - 1, y + dy))
        return nx, ny

    def run_trip(
        self,
        raksha: Raksha,
        rng: random.Random,
        path: list[tuple[int, int]] | None = None,
        start: tuple[int, int] | None = None,
    ) -> TripResult:
        """
        Execute a labyrinth trip for one Raksha.

        :param raksha: Raksha to send.
        :param rng: Injectable RNG.
        :param path: Optional explicit path; naive random walk if None.
        :param start: Starting coordinates for random walk; random perimeter if None.
        :return: TripResult with travelog.
        """
        validated_path: list[tuple[int, int]] | None = None
        if path is not None:
            validated_path = validate_prescribed_path(path)
            if validated_path is None:
                log.warning(
                    "trip.invalid_path_fallback",
                    raksha_id=str(raksha.id),
                    path_len=len(path),
                )

        use_path = validated_path is not None
        if not use_path:
            if start is None:
                start = random_perimeter_start(rng)
            start_x, start_y = start
            log.debug(
                "trip.started",
                raksha_id=str(raksha.id),
                has_path=False,
                start_x=start_x,
                start_y=start_y,
                start_on_perimeter=is_perimeter_square(start_x, start_y),
            )
        else:
            first_x, first_y = validated_path[0]
            log.debug(
                "trip.started",
                raksha_id=str(raksha.id),
                has_path=True,
                start_x=first_x,
                start_y=first_y,
                start_on_perimeter=True,
            )

        visited: list[tuple[int, int]] = []
        squares: dict[tuple[int, int], SquareRecord] = {}
        soma_gathered = 0
        survived = True
        hit_step_limit = False

        def _record_step(px: int, py: int) -> None:
            trap = self.get_trap(px, py)
            is_center = (px, py) in CENTER_SQUARES
            squares[(px, py)] = SquareRecord(
                x=px, y=py, trap_type=trap, is_center=is_center
            )
            visited.append((px, py))

        if use_path:
            steps = validated_path[:TRIP_MAX_STEPS]
            for px, py in steps:
                _record_step(px, py)
                if not self.resolve_trap(raksha, self.get_trap(px, py), rng):
                    survived = False
                    break
                if (px, py) in CENTER_SQUARES:
                    soma_gathered = rng.randint(SOMA_REWARD_MIN, SOMA_REWARD_MAX)
                    log.info("trip.center_reached", raksha_id=str(raksha.id), soma=soma_gathered)
                    break
            else:
                hit_step_limit = True
                log.debug("trip.step_limit", raksha_id=str(raksha.id), steps=TRIP_MAX_STEPS)
        else:
            x, y = start
            for step in range(TRIP_MAX_STEPS):
                _record_step(x, y)
                if not self.resolve_trap(raksha, self.get_trap(x, y), rng):
                    survived = False
                    log.debug("trip.died", raksha_id=str(raksha.id), step=step, x=x, y=y)
                    break
                if (x, y) in CENTER_SQUARES:
                    soma_gathered = rng.randint(SOMA_REWARD_MIN, SOMA_REWARD_MAX)
                    log.info("trip.center_reached", raksha_id=str(raksha.id), soma=soma_gathered)
                    break
                if step < TRIP_MAX_STEPS - 1:
                    x, y = self._naive_step(x, y, rng)
            else:
                hit_step_limit = True
                log.debug("trip.step_limit", raksha_id=str(raksha.id), steps=TRIP_MAX_STEPS)

        travelog = Travelog(
            raksha_id=raksha.id,
            path=visited,
            squares=squares,
            soma_gathered=soma_gathered,
            survived=survived,
            hit_step_limit=hit_step_limit,
        )
        return TripResult(raksha_id=raksha.id, travelog=travelog, died=not travelog.survived)

    def advance_epoch(self, rng: random.Random) -> Epoch:
        """
        Start a new epoch with re-rolled trap distribution.

        :param rng: Injectable RNG.
        :return: New epoch.
        """
        dominant = rng.choice(list(GeneType))
        length = rng.randint(5, 10)
        self.current_epoch = Epoch(
            dominant_type=dominant,
            turns_remaining=length,
            length=length,
        )
        self._generate_grid(dominant)
        log.info("epoch.advanced", dominant=dominant.name, length=length)
        return self.current_epoch

    def tick_epoch(self) -> bool:
        """
        Decrement epoch turns; advance epoch when exhausted.

        :return: True if epoch changed this tick.
        """
        if self.current_epoch is None:
            return False
        self.current_epoch.turns_remaining -= 1
        if self.current_epoch.turns_remaining <= 0:
            self.advance_epoch(self._rng)
            return True
        return False
