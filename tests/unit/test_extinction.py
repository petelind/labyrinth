"""Tests for civilization extinction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from labyrinth.domain.entities import (
    Civilization,
    CivilizationStatus,
    DNA,
    GameEvents,
    Raksha,
    StandingOrders,
    TurnContext,
)
from labyrinth.domain.types import CriteriaField, CriteriaOp, GeneType
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.engine.turn import CivilizationState, run_turn_for_civilization
from labyrinth.game import Game, GameConfig
from labyrinth.strategy.base import Strategy
from labyrinth.strategy.gen_alg import GenAlgStrategy


class MockStrategy(Strategy):
    """Strategy stub for extinction tests."""

    def __init__(self, orders: StandingOrders | None = None) -> None:
        super().__init__()
        self.decide_calls = 0
        if orders is not None:
            self._standing_orders = orders

    def decide(self, context: TurnContext) -> None:
        self.decide_calls += 1


def _raksha(civ_id: str = "civ-1", gene: GeneType = GeneType.FIRE) -> Raksha:
    others = [g for g in GeneType if g != gene]
    return Raksha(
        id=uuid4(),
        civilization_id=civ_id,
        dna=DNA(dominant=gene, secondary=others[0], recessive=others[1]),
        alive=True,
    )


def _civ_state(
    rakshas: list[Raksha],
    strategy: Strategy | None = None,
    soma: int = 100,
) -> CivilizationState:
    civ = Civilization(id="civ-1", name="TestCiv", soma=soma, rakshas=rakshas)
    return CivilizationState(civilization=civ, strategy=strategy or MockStrategy())


class TestExtinctAfterWeed:
    def test_extinct_after_weed(self, seeded_rng) -> None:
        from labyrinth.domain.types import Criterion

        orders = StandingOrders(
            weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            send_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            last_updated_turn=1,
        )
        strategy = MockStrategy(orders)
        state = _civ_state([_raksha(), _raksha()], strategy=strategy)
        labyrinth = Labyrinth.create(seeded_rng)
        events = GameEvents()

        summary = run_turn_for_civilization(
            state, labyrinth, 1, 4, seeded_rng, events,
        )

        assert state.civilization.status == CivilizationStatus.EXTINCT
        assert state.civilization.extinct_turn == 1
        assert summary.went_extinct is True
        assert summary.trips_sent == 0
        assert summary.pop_end == 0


class TestExtinctAfterTrips:
    def test_extinct_after_trips(self, seeded_rng) -> None:
        from labyrinth.domain.types import Criterion

        orders = StandingOrders(
            send_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            last_updated_turn=1,
        )
        strategy = MockStrategy(orders)
        state = _civ_state([_raksha()], strategy=strategy)
        labyrinth = Labyrinth.create(seeded_rng)
        events = GameEvents()

        with patch.object(labyrinth, "run_trip") as mock_trip:
            from labyrinth.domain.entities import SquareRecord, Travelog, TripResult

            raksha = state.civilization.rakshas[0]
            mock_trip.return_value = TripResult(
                raksha_id=raksha.id,
                travelog=Travelog(
                    raksha_id=raksha.id,
                    path=[(0, 0)],
                    squares={(0, 0): SquareRecord(0, 0, GeneType.FIRE)},
                    soma_gathered=0,
                    survived=False,
                ),
                died=True,
            )
            summary = run_turn_for_civilization(
                state, labyrinth, 1, 4, seeded_rng, events,
            )

        assert state.civilization.status == CivilizationStatus.EXTINCT
        assert summary.went_extinct is True
        assert summary.trips_sent == 1


class TestExtinctSkipsStrategy:
    def test_extinct_civ_skips_strategy(self, seeded_rng) -> None:
        from labyrinth.domain.types import Criterion

        orders = StandingOrders(
            weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            last_updated_turn=1,
        )
        strategy = MockStrategy(orders)
        state = _civ_state([_raksha()], strategy=strategy)
        state.civilization.status = CivilizationStatus.EXTINCT
        state.civilization.extinct_turn = 1
        labyrinth = Labyrinth.create(seeded_rng)

        summary = run_turn_for_civilization(
            state, labyrinth, 2, 3, seeded_rng, GameEvents(),
        )

        assert strategy.decide_calls == 0
        assert summary.trips_sent == 0
        assert summary.went_extinct is False


class TestAlreadyExtinctNoop:
    def test_already_extinct_noop_summary(self, seeded_rng) -> None:
        strategy = MockStrategy()
        state = _civ_state([_raksha()], strategy=strategy)
        state.civilization.status = CivilizationStatus.EXTINCT
        state.civilization.extinct_turn = 1
        state.civilization.rakshas[0].alive = False
        soma_before = state.civilization.soma
        labyrinth = Labyrinth.create(seeded_rng)

        summary = run_turn_for_civilization(
            state, labyrinth, 3, 1, seeded_rng, GameEvents(),
        )

        assert strategy.decide_calls == 0
        assert summary.deaths == 0
        assert summary.trips_sent == 0
        assert summary.pop_end == 0
        assert state.civilization.soma == soma_before


class TestGameExtinction:
    def test_all_extinct_ends_game_early(self, tmp_db: Path) -> None:
        from labyrinth.domain.types import Criterion

        weed_all = StandingOrders(
            weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            last_updated_turn=1,
        )

        class WeedAllStrategy(MockStrategy):
            def decide(self, context: TurnContext) -> None:
                super().decide(context)
                self.set_standing_orders(StandingOrders(
                    weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
                    last_updated_turn=context.turn_number,
                ))

        game = Game.create(
            [("CivA", WeedAllStrategy()), ("CivB", WeedAllStrategy())],
            GameConfig(turns_total=5, db_path=tmp_db, seed=42),
        )
        summaries = game.run_all()

        assert game.current_turn == 1
        assert game.finished is True
        assert len(summaries) == 2
        assert all(s.went_extinct for s in summaries)

    def test_winner_none_when_all_extinct(self, tmp_db: Path) -> None:
        from labyrinth.domain.types import Criterion

        class WeedAllStrategy(MockStrategy):
            def decide(self, context: TurnContext) -> None:
                self.set_standing_orders(StandingOrders(
                    weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
                    last_updated_turn=context.turn_number,
                ))

        game = Game.create(
            [("CivA", WeedAllStrategy())],
            GameConfig(turns_total=3, db_path=tmp_db, seed=42),
        )
        game.run_all()
        assert game._determine_winner() is None

    def test_winner_excludes_extinct_civ(self) -> None:
        alive_civ = Civilization(id="alive", name="Alive", soma=500, rakshas=[_raksha("alive")])
        extinct_civ = Civilization(
            id="extinct", name="Extinct", soma=2000, rakshas=[],
            status=CivilizationStatus.EXTINCT, extinct_turn=1,
        )
        game = Game(
            civilizations=[
                CivilizationState(civilization=alive_civ, strategy=GenAlgStrategy()),
                CivilizationState(civilization=extinct_civ, strategy=GenAlgStrategy()),
            ],
            labyrinth=Labyrinth.create(__import__("random").Random(42)),
            turns_total=5,
        )
        assert game._determine_winner() == "alive"

    def test_on_civilization_extinct_fires(self, seeded_rng) -> None:
        from labyrinth.domain.types import Criterion

        orders = StandingOrders(
            weed_criteria=[Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)],
            last_updated_turn=1,
        )
        strategy = MockStrategy(orders)
        state = _civ_state([_raksha()], strategy=strategy)
        labyrinth = Labyrinth.create(seeded_rng)
        fired: list[tuple[str, int]] = []
        events = GameEvents()
        events.on_civilization_extinct = lambda civ_id, turn: fired.append((civ_id, turn))

        run_turn_for_civilization(state, labyrinth, 1, 4, seeded_rng, events)

        assert fired == [("civ-1", 1)]
