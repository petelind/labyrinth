"""Criteria resolution and DNA inheritance."""

from __future__ import annotations

import random
from uuid import UUID, uuid4

from labyrinth.domain.entities import DNA, Raksha
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.logging_config import get_logger

log = get_logger(__name__)


def _get_field_value(raksha: Raksha, field: CriteriaField) -> GeneType | int | bool:
    """Extract the comparable value from a Raksha for the given field."""
    if field == CriteriaField.GENE_DOMINANT:
        return raksha.dna.dominant
    if field == CriteriaField.GENE_SECONDARY:
        return raksha.dna.secondary
    if field == CriteriaField.GENE_RECESSIVE:
        return raksha.dna.recessive
    if field == CriteriaField.TRIPS_COMPLETED:
        return raksha.trips_completed
    if field == CriteriaField.TRIPS_SURVIVED:
        return raksha.trips_survived
    if field == CriteriaField.ALIVE:
        return raksha.alive
    raise ValueError(f"Unknown criteria field: {field}")


def _compare(actual: GeneType | int | bool, op: CriteriaOp, expected: GeneType | int | bool) -> bool:
    """Evaluate a single comparison."""
    if op == CriteriaOp.EQ:
        return actual == expected
    if op == CriteriaOp.NEQ:
        return actual != expected
    if op == CriteriaOp.GT:
        return actual > expected  # type: ignore[operator]
    if op == CriteriaOp.GTE:
        return actual >= expected  # type: ignore[operator]
    if op == CriteriaOp.LT:
        return actual < expected  # type: ignore[operator]
    if op == CriteriaOp.LTE:
        return actual <= expected  # type: ignore[operator]
    raise ValueError(f"Unknown criteria op: {op}")


def _matches_criterion(raksha: Raksha, criterion: Criterion) -> bool:
    """Return True if raksha satisfies a single criterion."""
    actual = _get_field_value(raksha, criterion.field)
    return _compare(actual, criterion.op, criterion.value)


def matches_all_criteria(
    raksha: Raksha,
    criteria: tuple[Criterion, ...] | list[Criterion],
) -> bool:
    """
    Return True when a living Raksha satisfies all criteria (AND logic).

    :param raksha: Raksha to evaluate.
    :param criteria: Filter rules to apply.
    :return: True if alive and all criteria match.
    """
    if not raksha.alive:
        return False
    return all(_matches_criterion(raksha, c) for c in criteria)


def resolve_criteria(
    criteria: list[Criterion],
    rakshas: list[Raksha],
    *,
    match_all_alive_if_empty: bool = False,
) -> list[Raksha]:
    """
    Filter rakshas matching all criteria (AND logic).

    :param criteria: List of filter rules.
    :param rakshas: Candidate Rakshas.
    :param match_all_alive_if_empty: If True, empty criteria matches all alive.
    :return: Matching Rakshas in original order.
    """
    if not criteria:
        if match_all_alive_if_empty:
            result = [r for r in rakshas if r.alive]
        else:
            result = []
        log.debug(
            "criteria.resolved",
            criteria_count=0,
            matched=len(result),
            match_all_alive_if_empty=match_all_alive_if_empty,
        )
        return result

    result = [
        r for r in rakshas
        if r.alive and all(_matches_criterion(r, c) for c in criteria)
    ]
    log.debug(
        "criteria.resolved",
        criteria_count=len(criteria),
        candidates=len(rakshas),
        matched=len(result),
    )
    return result


def _parent_gene_pool(parent: Raksha) -> list[GeneType]:
    """Return dominant and secondary genes from a parent."""
    return [parent.dna.dominant, parent.dna.secondary]


def _all_parent_genes(parent_a: Raksha, parent_b: Raksha) -> list[GeneType]:
    """Union of all genes from both parents."""
    return [
        parent_a.dna.dominant,
        parent_a.dna.secondary,
        parent_a.dna.recessive,
        parent_b.dna.dominant,
        parent_b.dna.secondary,
        parent_b.dna.recessive,
    ]


def inherit_dna(
    parent_a: Raksha,
    parent_b: Raksha,
    rng: random.Random,
    civilization_id: str,
) -> Raksha:
    """
    Create a child Raksha with DNA inherited from two parents.

    Child draws one gene from each parent's {dominant, secondary}; assignment
    to child's dominant/secondary is random. Recessive drawn from the union
    of both parents' three genes, excluding the two already assigned.

    :param parent_a: First parent.
    :param parent_b: Second parent.
    :param rng: Injectable RNG for deterministic tests.
    :param civilization_id: Owning civilization id.
    :return: New child Raksha (alive, zero trips).
    """
    gene_a = rng.choice(_parent_gene_pool(parent_a))
    gene_b = rng.choice(_parent_gene_pool(parent_b))
    assigned = [gene_a, gene_b]
    rng.shuffle(assigned)
    dominant, secondary = assigned[0], assigned[1]

    recessive_pool = [
        g for g in _all_parent_genes(parent_a, parent_b)
        if g not in (dominant, secondary)
    ]
    if not recessive_pool:
        recessive_pool = [g for g in GeneType if g not in (dominant, secondary)]
    recessive = rng.choice(recessive_pool)

    child = Raksha(
        id=uuid4(),
        civilization_id=civilization_id,
        dna=DNA(dominant=dominant, secondary=secondary, recessive=recessive),
        alive=True,
        parent_a_id=parent_a.id,
        parent_b_id=parent_b.id,
    )
    log.debug(
        "dna.inherited",
        parent_a=str(parent_a.id),
        parent_b=str(parent_b.id),
        child=str(child.id),
        dominant=dominant.name,
        secondary=secondary.name,
        recessive=recessive.name,
    )
    return child
