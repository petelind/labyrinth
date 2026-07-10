"""Game orchestration — no tkinter imports."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from labyrinth.domain.entities import (
    Civilization,
    CivilizationStatus,
    DNA,
    GameEvents,
    Raksha,
    TurnSummary,
)
from labyrinth.domain.archetypes import (
    INITIAL_RAKSHAS,
    MEMBERS_PER_DOM_SEC,
    STRAY_COUNT,
)
from labyrinth.domain.types import GeneType
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.engine.turn import CivilizationState, run_turn_for_civilization, strategy_label_for
from labyrinth.logging_config import configure_logging, get_logger
from labyrinth.narrative import TurnChronicler
from labyrinth.persistence.repo import GameRepository
from labyrinth.strategy.base import Strategy

log = get_logger(__name__)


def initial_soma(turns_total: int) -> int:
    """
    Compute starting Soma from game length.

    :param turns_total: Total turns configured for the game.
    :return: Soma budget equal to full-population sustenance runway.
    """
    return INITIAL_RAKSHAS * turns_total


@dataclass
class GameConfig:
    """Configuration for a new game."""

    turns_total: int = 20
    db_path: Path | None = None
    seed: int = 42
    thinking_seconds: float = 180


@dataclass
class Game:
    """
    Owns labyrinth, civilizations, and turn progression.

    Integration tests and GUI both drive this class; GUI wires GameEvents.
    """

    civilizations: list[CivilizationState]
    labyrinth: Labyrinth
    turns_total: int
    current_turn: int = 0
    events: GameEvents = field(default_factory=GameEvents)
    db_path: Path | None = None
    _rng: random.Random = field(default_factory=random.Random)
    _summaries: list[TurnSummary] = field(default_factory=list)
    _repo: GameRepository | None = None
    _finished: bool = False
    _thinking_seconds: float = 180

    @classmethod
    def create(
        cls,
        civ_specs: list[tuple[str, Strategy]],
        config: GameConfig | None = None,
        events: GameEvents | None = None,
    ) -> Game:
        """
        Factory to create a new game with initial Rakshas.

        :param civ_specs: List of (name, strategy) pairs.
        :param config: Game configuration.
        :param events: Optional event callbacks.
        :return: Initialized Game.
        """
        configure_logging()
        cfg = config or GameConfig()
        rng = random.Random(cfg.seed)
        labyrinth = Labyrinth.create(rng)
        start_soma = initial_soma(cfg.turns_total)

        states: list[CivilizationState] = []
        for name, strategy in civ_specs:
            civ_id = name.lower().replace(" ", "-")
            rakshas = _create_initial_rakshas(civ_id, rng)
            civ = Civilization(id=civ_id, name=name, soma=start_soma, rakshas=rakshas)
            states.append(CivilizationState(civilization=civ, strategy=strategy))

        repo = GameRepository(cfg.db_path) if cfg.db_path else None
        if repo:
            repo.initialize()
            repo.create_game(cfg.turns_total, [s.civilization for s in states], seed=cfg.seed)

        game = cls(
            civilizations=states,
            labyrinth=labyrinth,
            turns_total=cfg.turns_total,
            events=events or GameEvents(),
            db_path=cfg.db_path,
            _rng=rng,
            _repo=repo,
            _thinking_seconds=cfg.thinking_seconds,
        )
        log.info(
            "game.created",
            turns=cfg.turns_total,
            civilizations=len(states),
            initial_soma=start_soma,
        )
        return game

    @property
    def finished(self) -> bool:
        """Whether the game has ended (turns exhausted or all civs extinct)."""
        return self._finished

    def next_turn(self) -> list[TurnSummary]:
        """
        Advance the game by one turn for all civilizations.

        :return: TurnSummary list (one per civilization).
        :raises StopIteration: If game is already finished.
        """
        if self._finished or self.current_turn >= self.turns_total:
            raise StopIteration("Game is finished")

        self.current_turn += 1
        turns_remaining = self.turns_total - self.current_turn
        epoch = self.labyrinth.current_epoch
        if epoch:
            self.events.on_turn_start(self.current_turn, epoch)

        chronicler = TurnChronicler()
        if epoch:
            chronicler.begin_turn(self.current_turn, self.turns_total, epoch)

        turn_summaries: list[TurnSummary] = []
        for state in self.civilizations:
            summary = run_turn_for_civilization(
                state,
                self.labyrinth,
                self.current_turn,
                turns_remaining,
                self._rng,
                self.events,
                chronicler=chronicler,
                strategy_label=strategy_label_for(state.strategy),
                thinking_seconds=self._thinking_seconds,
            )
            turn_summaries.append(summary)
            self._summaries.append(summary)

        chapter_text = chronicler.flush()
        self.events.on_chapter(chapter_text)

        if self.labyrinth.tick_epoch():
            for state in self.civilizations:
                state.civilization.known_map.clear()
            log.info("epoch.known_maps_cleared", civilizations=len(self.civilizations))

        if self._repo:
            self._repo.save_turn(
                self.current_turn,
                epoch,
                turn_summaries,
                self.civilizations,
                labyrinth=self.labyrinth,
            )

        self.events.on_turn_end(turn_summaries)
        log.info("game.turn_advanced", turn=self.current_turn)

        if self._all_extinct():
            self._finish_game()

        return turn_summaries

    def run_all(self) -> list[TurnSummary]:
        """
        Run all remaining turns until game end.

        :return: All TurnSummary records.
        """
        while self.current_turn < self.turns_total and not self._finished:
            self.next_turn()
        if not self._finished:
            self._finish_game()
        return self._summaries

    def _all_extinct(self) -> bool:
        """Return True when every civilization is extinct."""
        return all(
            s.civilization.status == CivilizationStatus.EXTINCT
            for s in self.civilizations
        )

    def _alive_count(self, civ: Civilization) -> int:
        return len([r for r in civ.rakshas if r.alive])

    def _finish_game(self) -> None:
        """Mark game complete and finalize persistence."""
        if self._finished:
            return
        self._finished = True
        self.events.on_game_end(self._summaries)
        if self._repo:
            winner = self._determine_winner()
            self._repo.finalize_game(winner)
        log.info("game.finished", turns=self.current_turn, all_extinct=self._all_extinct())

    def _determine_winner(self) -> str | None:
        """Return civilization id with highest soma among surviving civs."""
        survivors = [
            s for s in self.civilizations
            if s.civilization.status == CivilizationStatus.ACTIVE
            and self._alive_count(s.civilization) > 0
        ]
        if not survivors:
            return None
        best = max(survivors, key=lambda s: s.civilization.soma)
        return best.civilization.id

    @property
    def summaries(self) -> list[TurnSummary]:
        """All turn summaries recorded so far."""
        return list(self._summaries)


def _create_initial_rakshas(civ_id: str, rng: random.Random) -> list[Raksha]:
    """
    Create a diverse starting population: 96 archetype cohort + 4 strays.

    Cohort = 16 (dominant×secondary) groups × 6 members with varied recessive genes.
    Strays = 4 fully random DNA outliers.
    """
    rakshas: list[Raksha] = []
    recessive_cycle = list(GeneType)
    for dominant in GeneType:
        for secondary in GeneType:
            dom_idx = recessive_cycle.index(dominant)
            sec_idx = recessive_cycle.index(secondary)
            for member_idx in range(MEMBERS_PER_DOM_SEC):
                recessive = recessive_cycle[
                    (member_idx + dom_idx + sec_idx) % len(GeneType)
                ]
                rakshas.append(Raksha(
                    id=uuid4(),
                    civilization_id=civ_id,
                    dna=DNA(dominant=dominant, secondary=secondary, recessive=recessive),
                ))
    for _ in range(STRAY_COUNT):
        genes = [rng.choice(list(GeneType)) for _ in range(3)]
        rakshas.append(Raksha(
            id=uuid4(),
            civilization_id=civ_id,
            dna=DNA(dominant=genes[0], secondary=genes[1], recessive=genes[2]),
        ))
    if len(rakshas) != INITIAL_RAKSHAS:
        raise ValueError(
            f"Expected {INITIAL_RAKSHAS} initial Rakshas, got {len(rakshas)}",
        )
    return rakshas
