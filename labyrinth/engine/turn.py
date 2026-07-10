"""Turn execution orchestration."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass

from labyrinth.domain.criteria import resolve_criteria
from labyrinth.domain.entities import (
    Civilization,
    CivilizationStatus,
    GameEvents,
    StandingOrders,
    TurnContext,
    TurnSummary,
    TripResult,
)
from labyrinth.engine.labyrinth import Labyrinth
from labyrinth.engine.route_resolver import resolve_route_for_raksha
from labyrinth.engine.reproduce import apply_reproduce
from labyrinth.engine.weed import apply_mandatory_kill, apply_weed
from labyrinth.logging_config import get_logger
from labyrinth.narrative import TurnChronicler, aggregate_trip_results
from labyrinth.strategy.base import Strategy

log = get_logger(__name__)

THINKING_SECONDS = 180


@dataclass
class CivilizationState:
    """Runtime state for one civilization in a game."""

    civilization: Civilization
    strategy: Strategy


def _alive_count(civ: Civilization) -> int:
    """Return number of living Rakshas."""
    return len([r for r in civ.rakshas if r.alive])


def _mark_extinct(
    civ: Civilization,
    turn_number: int,
    events: GameEvents,
) -> None:
    """
    Mark civilization extinct and notify listeners.

    :param civ: Civilization to mark.
    :param turn_number: Turn when extinction occurred.
    :param events: Game event callbacks.
    """
    if civ.status == CivilizationStatus.EXTINCT:
        return
    civ.status = CivilizationStatus.EXTINCT
    civ.extinct_turn = turn_number
    log.info("civilization.extinct", civilization=civ.id, turn=turn_number)
    events.on_civilization_extinct(civ.id, turn_number)


def _noop_extinct_summary(
    civ: Civilization,
    turn_number: int,
) -> TurnSummary:
    """Build a zero-activity summary for an already-extinct civilization."""
    return TurnSummary(
        turn_number=turn_number,
        civilization_id=civ.id,
        soma_start=civ.soma,
        soma_end=civ.soma,
        pop_start=0,
        pop_end=0,
        deaths=0,
        trips_sent=0,
        trips_survived=0,
        soma_gathered=0,
        strategy_sumup="",
        strategy_thinking="",
        went_extinct=False,
    )


def _build_summary(
    civ: Civilization,
    turn_number: int,
    soma_start: int,
    pop_start: int,
    killed: list,
    trips_sent: int,
    trips_survived: int,
    soma_gathered: int,
    orders: StandingOrders,
    strategy: Strategy,
    went_extinct: bool,
) -> TurnSummary:
    """Assemble a turn summary from accumulated turn metrics."""
    alive_count = _alive_count(civ)
    return TurnSummary(
        turn_number=turn_number,
        civilization_id=civ.id,
        soma_start=soma_start,
        soma_end=civ.soma,
        pop_start=pop_start,
        pop_end=alive_count,
        deaths=len(killed),
        trips_sent=trips_sent,
        trips_survived=trips_survived,
        soma_gathered=soma_gathered,
        strategy_sumup=orders.current_strategy_sumup,
        strategy_thinking=_strategy_thinking(strategy),
        went_extinct=went_extinct,
    )


def _merge_travelog(civ: Civilization, result: TripResult) -> None:
    """Update civilization map knowledge from a trip result."""
    civ.recent_travelogs.append(result.travelog)
    for pos, record in result.travelog.squares.items():
        civ.known_map[pos] = record
    raksha = next((r for r in civ.rakshas if r.id == result.raksha_id), None)
    if raksha is None:
        return
    raksha.trips_completed += 1
    if result.travelog.survived:
        raksha.trips_survived += 1
    if result.died:
        raksha.alive = False


def _run_strategy_decide(state: CivilizationState, context: TurnContext) -> None:
    """Run strategy.decide in current thread (caller may use daemon thread)."""
    try:
        state.strategy.decide(context)
    except Exception:
        log.exception("strategy.decide_failed", civilization=state.civilization.id)


def _get_orders(state: CivilizationState, turn_number: int) -> tuple[StandingOrders, bool]:
    """Return standing orders and whether fallback was used."""
    orders = state.strategy.standing_orders
    used_fallback = orders.last_updated_turn != turn_number
    if used_fallback:
        log.warning(
            "strategy.deadline_used",
            civilization=state.civilization.id,
            turn=turn_number,
            last_updated=orders.last_updated_turn,
        )
    return orders, used_fallback


def _build_context(
    state: CivilizationState,
    turn_number: int,
    turns_remaining: int,
    chronicler: TurnChronicler | None,
) -> TurnContext:
    """Build read-only turn context for strategy."""
    return TurnContext(
        turn_number=turn_number,
        soma=state.civilization.soma,
        rakshas=list(state.civilization.rakshas),
        recent_travelogs=list(state.civilization.recent_travelogs),
        known_map=dict(state.civilization.known_map),
        turns_remaining=turns_remaining,
        chronicler=chronicler,
        civilization_id=state.civilization.id,
        civilization_name=state.civilization.name,
    )


def _execute_trips(
    civ_state: CivilizationState,
    labyrinth: Labyrinth,
    orders: StandingOrders,
    rng: random.Random,
    events: GameEvents,
    context: TurnContext,
) -> tuple[int, int, int, list[TripResult]]:
    """Run trips in parallel for one civilization."""
    pool = resolve_criteria(orders.send_criteria, civ_state.civilization.rakshas)
    to_send = civ_state.strategy.select_send_pool(pool, context)
    sent = len(to_send)
    survived_count = 0
    soma_gathered = 0
    results: list[TripResult] = []

    for raksha in to_send:
        path = resolve_route_for_raksha(raksha, orders.routes)
        result = labyrinth.run_trip(raksha, rng, path=path)
        results.append(result)
        _merge_travelog(civ_state.civilization, result)
        events.on_trip_result(civ_state.civilization.id, result)
        if result.travelog.survived:
            survived_count += 1
        soma_gathered += result.travelog.soma_gathered
        civ_state.civilization.soma += result.travelog.soma_gathered

    return sent, survived_count, soma_gathered, results


def _deduct_sustenance(civ: Civilization) -> None:
    """Charge 1 soma per surviving Raksha at turn end."""
    alive_count = _alive_count(civ)
    civ.soma -= alive_count
    if civ.soma < 0:
        civ.soma = 0


def run_turn_for_civilization(
    civ_state: CivilizationState,
    labyrinth: Labyrinth,
    turn_number: int,
    turns_remaining: int,
    rng: random.Random,
    events: GameEvents,
    chronicler: TurnChronicler | None = None,
    strategy_label: str = "Strategy",
    thinking_seconds: float = THINKING_SECONDS,
) -> TurnSummary:
    """
    Execute one turn for a single civilization.

    :param civ_state: Civilization + strategy pair.
    :param labyrinth: Shared labyrinth instance.
    :param turn_number: Current turn number (1-based).
    :param turns_remaining: Turns left in game.
    :param rng: Injectable RNG.
    :param events: Game event callbacks.
    :param chronicler: Optional narrative chronicler for this turn.
    :param strategy_label: Human-readable strategy name for the chapter.
    :param thinking_seconds: Strategy thinking budget.
    :return: TurnSummary for this civilization.
    """
    civ = civ_state.civilization
    epoch = labyrinth.current_epoch
    if epoch is None:
        raise ValueError("Labyrinth has no active epoch")

    if civ.status == CivilizationStatus.EXTINCT:
        if chronicler is not None:
            chronicler.begin_civilization(civ.name, strategy_label)
            chronicler.record_opening(civ.soma, 0)
            chronicler.record_extinction(already_extinct=True)
            chronicler.record_close(_noop_extinct_summary(civ, turn_number))
        return _noop_extinct_summary(civ, turn_number)

    pop_start = _alive_count(civ)
    soma_start = civ.soma

    if chronicler is not None:
        chronicler.begin_civilization(civ.name, strategy_label)
        chronicler.record_opening(soma_start, pop_start)

    context = _build_context(
        civ_state, turn_number, turns_remaining, chronicler,
    )
    deadline = time.time() + thinking_seconds
    civ_state.strategy.set_deadline(deadline)

    thread = threading.Thread(
        target=_run_strategy_decide,
        args=(civ_state, context),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=thinking_seconds)

    orders, used_fallback = _get_orders(civ_state, turn_number)
    if chronicler is not None:
        chronicler.record_orders(orders, used_fallback=used_fallback)

    strategy_killed: list[Raksha] = []
    cull_targets = civ_state.strategy.select_cull_targets(context)
    if cull_targets:
        for raksha in cull_targets:
            if raksha.alive:
                raksha.alive = False
                strategy_killed.append(raksha)
        log.info(
            "weed.cull_targets",
            civilization=civ.id,
            killed=len(strategy_killed),
        )
    else:
        strategy_killed = apply_weed(civ, orders.weed_criteria)
    mandatory_killed = apply_mandatory_kill(civ, civ.soma)
    killed = strategy_killed + mandatory_killed

    if chronicler is not None:
        chronicler.record_weeding(
            strategy_killed, mandatory_killed, orders.weed_criteria,
        )

    went_extinct = False
    trips_sent = 0
    trips_survived = 0
    soma_gathered = 0

    if _alive_count(civ) == 0:
        went_extinct = True
        _mark_extinct(civ, turn_number, events)
        if chronicler is not None:
            chronicler.record_extinction()
    else:
        civ.recent_travelogs.clear()
        trips_sent, trips_survived, soma_gathered, trip_results = _execute_trips(
            civ_state, labyrinth, orders, rng, events, context,
        )

        if chronicler is not None:
            stats = aggregate_trip_results(trip_results)
            chronicler.record_labyrinth(**stats)

        if _alive_count(civ) == 0:
            went_extinct = True
            _mark_extinct(civ, turn_number, events)
            if chronicler is not None:
                chronicler.record_extinction()
        else:
            children = apply_reproduce(
                civ,
                orders.reproduce_criteria,
                rng,
                pair_selector=civ_state.strategy.select_repro_pairs,
                context=context,
            )
            if chronicler is not None:
                chronicler.record_reproduction(len(children))

    _deduct_sustenance(civ)

    summary = _build_summary(
        civ, turn_number, soma_start, pop_start, killed,
        trips_sent, trips_survived, soma_gathered, orders,
        civ_state.strategy, went_extinct,
    )

    if chronicler is not None:
        chronicler.record_close(summary)

    log.info(
        "turn.completed",
        civilization=civ.id,
        turn=turn_number,
        soma_end=civ.soma,
        pop_end=summary.pop_end,
        extinct=went_extinct,
    )
    return summary


def _strategy_thinking(strategy: Strategy) -> str:
    """Return captured LLM thinking text if available."""
    from labyrinth.strategy.llm import LLMStrategy

    if isinstance(strategy, LLMStrategy):
        return strategy.last_thinking
    return ""


def strategy_label_for(strategy: Strategy) -> str:
    """Return a display label for a strategy instance."""
    from labyrinth.strategy.gen_alg import GenAlgStrategy
    from labyrinth.strategy.llm import LLMStrategy

    if isinstance(strategy, GenAlgStrategy):
        return "GenAlg"
    if isinstance(strategy, LLMStrategy):
        return f"LLM ({strategy._model})"
    return strategy.__class__.__name__
