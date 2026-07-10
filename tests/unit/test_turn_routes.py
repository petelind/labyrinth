"""Integration tests for criteria-mapped routes in turn execution."""

from __future__ import annotations

import random
from uuid import uuid4

from labyrinth.domain.entities import (
    Civilization,
    DNA,
    GameEvents,
    Raksha,
    Route,
    StandingOrders,
    TurnContext,
)
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.engine.turn import CivilizationState, run_turn_for_civilization
from labyrinth.strategy.base import Strategy


def _raksha(dominant: GeneType) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(
            dominant=dominant,
            secondary=GeneType.WATER,
            recessive=GeneType.EARTH,
        ),
    )


class RouteStrategy(Strategy):
    """Sends one FIRE Raksha with a prescribed path to center."""

    def __init__(self, path: list[tuple[int, int]]) -> None:
        super().__init__()
        self._path = path

    def decide(self, context: TurnContext) -> None:
        self.set_standing_orders(StandingOrders(
            send_criteria=[
                Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE),
                Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True),
            ],
            routes=[
                Route(
                    criteria=(
                        Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE),
                    ),
                    path=tuple(self._path),
                ),
            ],
            last_updated_turn=context.turn_number,
            current_strategy_sumup="Route FIRE to center.",
        ))


def _left_to_center_path() -> list[tuple[int, int]]:
    return [(0, 49)] + [(x, 49) for x in range(1, 50)]


def _clear_path_traps(lab: Labyrinth, path: list[tuple[int, int]]) -> None:
    for pos in path:
        lab.grid[pos] = None


class TestTurnRoutes:
    def test_standing_orders_routes_wired_to_run_trip(self) -> None:
        rng = random.Random(99)
        labyrinth = Labyrinth.create(rng, dominant=GeneType.FIRE)
        path = _left_to_center_path()
        _clear_path_traps(labyrinth, path)
        fire_raksha = _raksha(GeneType.FIRE)
        water_raksha = _raksha(GeneType.WATER)
        civ = Civilization(
            id="civ-1",
            name="Route Civ",
            soma=100,
            rakshas=[fire_raksha, water_raksha],
        )
        state = CivilizationState(civilization=civ, strategy=RouteStrategy(path))
        state.strategy.decide(TurnContext(
            turn_number=1,
            soma=civ.soma,
            rakshas=list(civ.rakshas),
            recent_travelogs=[],
            known_map={},
            turns_remaining=19,
            civilization_id=civ.id,
            civilization_name=civ.name,
        ))

        summary = run_turn_for_civilization(
            state,
            labyrinth,
            turn_number=1,
            turns_remaining=19,
            rng=rng,
            events=GameEvents(),
            thinking_seconds=0.01,
        )

        assert summary.trips_sent == 1
        assert civ.recent_travelogs
        travelog = civ.recent_travelogs[0]
        assert travelog.path[0] == path[0]
        assert travelog.path[:3] == path[:3]
        assert travelog.soma_gathered >= 1
