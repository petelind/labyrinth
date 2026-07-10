"""Weed (kill/sustain) logic for civilizations."""

from __future__ import annotations

from labyrinth.domain.criteria import resolve_criteria
from labyrinth.domain.entities import Civilization, Raksha
from labyrinth.domain.types import Criterion
from labyrinth.logging_config import get_logger

log = get_logger(__name__)


def _kill_value_key(raksha: Raksha) -> tuple[int, int]:
    """Sort key for mandatory kills: lowest trips_survived, then trips_completed."""
    return (raksha.trips_survived, raksha.trips_completed)


def apply_weed(
    civilization: Civilization,
    criteria: list[Criterion],
) -> list[Raksha]:
    """
    Kill Rakshas matching weed criteria.

    :param civilization: Target civilization (mutated in place).
    :param criteria: Weed filter rules.
    :return: List of killed Rakshas.
    """
    targets = resolve_criteria(criteria, civilization.rakshas)
    killed: list[Raksha] = []
    for raksha in targets:
        if raksha.alive:
            raksha.alive = False
            killed.append(raksha)
    log.info(
        "weed.applied",
        civilization=civilization.id,
        criteria_count=len(criteria),
        killed=len(killed),
    )
    return killed


def apply_mandatory_kill(civilization: Civilization, soma: int) -> list[Raksha]:
    """
    Auto-kill lowest-value Rakshas until alive count <= soma.

    :param civilization: Target civilization (mutated in place).
    :param soma: Available soma for sustenance.
    :return: List of additionally killed Rakshas.
    """
    alive = [r for r in civilization.rakshas if r.alive]
    deficit = len(alive) - soma
    if deficit <= 0:
        return []

    to_kill = sorted(alive, key=_kill_value_key)[:deficit]
    for raksha in to_kill:
        raksha.alive = False
    log.warning(
        "weed.mandatory_kill",
        civilization=civilization.id,
        deficit=deficit,
        killed=len(to_kill),
    )
    return to_kill


def sustain_and_weed(
    civilization: Civilization,
    criteria: list[Criterion],
    soma: int,
) -> list[Raksha]:
    """
    Apply strategy weed criteria then mandatory deficit kills.

    :param civilization: Target civilization.
    :param criteria: Strategy weed criteria.
    :param soma: Available soma.
    :return: All killed Rakshas (strategy + mandatory).
    """
    killed = apply_weed(civilization, criteria)
    killed.extend(apply_mandatory_kill(civilization, soma))
    return killed
