"""Strategy ABC with thread-safe standing orders."""

from __future__ import annotations

import random
import threading
import time
from abc import ABC, abstractmethod

from labyrinth.domain.entities import Raksha, StandingOrders, TurnContext
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp
from labyrinth.logging_config import get_logger

log = get_logger(__name__)


class Strategy(ABC):
    """
    Abstract base for all Civilization strategies.

    Lifecycle per turn:
      1. Game calls set_deadline(now + 180).
      2. Game launches decide(context) in a daemon thread.
      3. decide() writes to standing_orders at any point.
      4. When thread joins or deadline fires, Game reads standing_orders.
    """

    DEFAULT_ORDERS = StandingOrders(
        send_criteria=[
            Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True),
        ],
        current_strategy_sumup="Default: sustain all, send all alive.",
    )

    def __init__(self) -> None:
        self._standing_orders = StandingOrders(
            weed_criteria=list(self.DEFAULT_ORDERS.weed_criteria),
            send_criteria=list(self.DEFAULT_ORDERS.send_criteria),
            reproduce_criteria=list(self.DEFAULT_ORDERS.reproduce_criteria),
            routes=list(self.DEFAULT_ORDERS.routes),
            current_strategy_sumup=self.DEFAULT_ORDERS.current_strategy_sumup,
            last_updated_turn=self.DEFAULT_ORDERS.last_updated_turn,
        )
        self._lock = threading.RLock()
        self._deadline: float = float("inf")

    @property
    def standing_orders(self) -> StandingOrders:
        """Thread-safe read of current standing orders."""
        with self._lock:
            return StandingOrders(
                weed_criteria=list(self._standing_orders.weed_criteria),
                send_criteria=list(self._standing_orders.send_criteria),
                reproduce_criteria=list(self._standing_orders.reproduce_criteria),
                routes=list(self._standing_orders.routes),
                current_strategy_sumup=self._standing_orders.current_strategy_sumup,
                last_updated_turn=self._standing_orders.last_updated_turn,
            )

    def set_standing_orders(self, orders: StandingOrders) -> None:
        """Thread-safe write of standing orders."""
        with self._lock:
            self._standing_orders = orders
            log.debug(
                "strategy.orders_updated",
                turn=orders.last_updated_turn,
                weed=len(orders.weed_criteria),
                send=len(orders.send_criteria),
                reproduce=len(orders.reproduce_criteria),
                routes=len(orders.routes),
            )

    def set_deadline(self, deadline: float) -> None:
        """Set Unix timestamp after which engine reads standing_orders as-is."""
        self._deadline = deadline
        log.debug("strategy.deadline_set", deadline=deadline)

    @abstractmethod
    def decide(self, context: TurnContext) -> None:
        """Analyze context and update standing_orders."""
        ...

    def time_remaining(self) -> float:
        """Seconds remaining in thinking window."""
        return max(0.0, self._deadline - time.time())

    def should_stop(self) -> bool:
        """True when fewer than 1 second remain."""
        return self.time_remaining() < 1.0

    def select_send_pool(self, candidates: list[Raksha], context: TurnContext) -> list[Raksha]:
        """
        Narrow criteria-matched candidates to the actual trip roster.

        :param candidates: Rakshas matching send_criteria.
        :param context: Current turn context.
        :return: Rakshas to send (default: all candidates).
        """
        return candidates

    def select_repro_pairs(
        self,
        pool: list[Raksha],
        context: TurnContext,
        rng: random.Random,
    ) -> list[tuple[Raksha, Raksha]]:
        """
        Pair eligible parents for reproduction (default: random shuffle).

        :param pool: Parents matching reproduce_criteria.
        :param context: Current turn context.
        :param rng: Injectable RNG.
        :return: Parent pairs to breed.
        """
        if len(pool) < 2:
            return []
        shuffled = list(pool)
        rng.shuffle(shuffled)
        if len(shuffled) % 2 == 1:
            shuffled.pop()
        return [
            (shuffled[i], shuffled[i + 1])
            for i in range(0, len(shuffled), 2)
        ]

    def select_cull_targets(self, context: TurnContext) -> list[Raksha]:
        """
        Optional explicit cull list (overrides weed_criteria when non-empty).

        :param context: Current turn context.
        :return: Rakshas to kill this turn.
        """
        return []
