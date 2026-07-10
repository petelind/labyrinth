"""Reproduction logic for civilizations."""

from __future__ import annotations

import random

from labyrinth.domain.criteria import inherit_dna, resolve_criteria
from labyrinth.domain.entities import Civilization, Raksha
from labyrinth.domain.types import Criterion
from labyrinth.logging_config import get_logger

log = get_logger(__name__)


def apply_reproduce(
    civilization: Civilization,
    criteria: list[Criterion],
    rng: random.Random,
    pair_selector: object | None = None,
    context: object | None = None,
) -> list[Raksha]:
    """
    Reproduce Rakshas from eligible pool via random pairing.

    Odd one out in the pool is skipped. New Rakshas are available next turn.

    :param civilization: Target civilization (mutated in place).
    :param criteria: Reproduce filter rules.
    :param rng: Injectable RNG.
    :return: List of newborn Rakshas.
    """
    pool = resolve_criteria(criteria, civilization.rakshas, match_all_alive_if_empty=True)
    if len(pool) < 2:
        log.debug("reproduce.skipped", civilization=civilization.id, pool_size=len(pool))
        return []

    if pair_selector is not None and context is not None:
        pairs = pair_selector(pool, context, rng)
    else:
        shuffled = list(pool)
        rng.shuffle(shuffled)
        if len(shuffled) % 2 == 1:
            skipped = shuffled.pop()
            log.debug("reproduce.skipped_odd", raksha_id=str(skipped.id))
        pairs = [
            (shuffled[i], shuffled[i + 1])
            for i in range(0, len(shuffled), 2)
        ]

    children: list[Raksha] = []
    for parent_a, parent_b in pairs:
        child = inherit_dna(parent_a, parent_b, rng, civilization.id)
        civilization.rakshas.append(child)
        children.append(child)
        log.debug(
            "reproduce.paired",
            parent_a=str(parent_a.id),
            parent_b=str(parent_b.id),
            child=str(child.id),
        )

    log.info("reproduce.completed", civilization=civilization.id, children=len(children))
    return children
