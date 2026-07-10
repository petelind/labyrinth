"""Domain type aliases and enums."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

TRIP_MAX_STEPS: int = 200
LABYRINTH_SIZE: int = 100
CENTER_SQUARES: frozenset[tuple[int, int]] = frozenset(
    {(49, 49), (49, 50), (50, 49), (50, 50)}
)


class GeneType(Enum):
    """Resistance gene types matching labyrinth trap epochs."""

    FIRE = auto()
    WATER = auto()
    EARTH = auto()
    AIR = auto()


class CriteriaField(Enum):
    """Raksha attribute that a Criterion can filter on."""

    GENE_DOMINANT = "gene_dominant"
    GENE_SECONDARY = "gene_secondary"
    GENE_RECESSIVE = "gene_recessive"
    TRIPS_COMPLETED = "trips_completed"
    TRIPS_SURVIVED = "trips_survived"
    ALIVE = "alive"


class CriteriaOp(Enum):
    """Comparison operator for a Criterion."""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


@dataclass(frozen=True)
class Criterion:
    """
    A single filter rule. Multiple Criteria in a list are AND-ed.

    :param field: Raksha attribute to compare.
    :param op: Comparison operator.
    :param value: Expected value (GeneType, int, or bool).
    """

    field: CriteriaField
    op: CriteriaOp
    value: GeneType | int | bool
