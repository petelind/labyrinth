"""Pure helpers for building criteria-mapped routes from survivor travelogs."""

from __future__ import annotations

from labyrinth.domain.archetypes import dna_key
from labyrinth.domain.entities import Raksha, Route, Travelog
from labyrinth.domain.grid import validate_prescribed_path
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.logging_config import get_logger

log = get_logger(__name__)

SOMA_SCORE_BONUS: int = 1_000_000


def _trip_score(travelog: Travelog, path_len: int) -> tuple[int, int]:
    """
    Score a candidate trip for cache ranking.

    :param travelog: Trip record to score.
    :param path_len: Validated path length.
    :return: Sortable score tuple (higher is better).
    """
    soma_score = SOMA_SCORE_BONUS if travelog.soma_gathered > 0 else 0
    return (soma_score + travelog.soma_gathered, path_len)


def _criteria_for_archetype(raksha: Raksha) -> tuple[Criterion, ...]:
    """Build three-gene criteria matching a Raksha DNA triple."""
    return (
        Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, raksha.dna.dominant),
        Criterion(CriteriaField.GENE_SECONDARY, CriteriaOp.EQ, raksha.dna.secondary),
        Criterion(CriteriaField.GENE_RECESSIVE, CriteriaOp.EQ, raksha.dna.recessive),
    )


def _criteria_for_dominant(gene: GeneType) -> tuple[Criterion, ...]:
    """Build dominant-only criteria for a gene."""
    return (Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, gene),)


def route_from_travelog(raksha: Raksha, travelog: Travelog) -> Route | None:
    """
    Build a single archetype route from one survivor travelog.

    :param raksha: Raksha who took the trip.
    :param travelog: Trip record to convert.
    :return: Route or None if trip/path is unusable.
    """
    if not travelog.survived:
        return None
    validated = validate_prescribed_path(travelog.path)
    if validated is None:
        return None
    return Route(
        criteria=_criteria_for_archetype(raksha),
        path=tuple(validated),
    )


def _collect_candidates(
    travelogs: list[Travelog],
    rakshas: list[Raksha],
) -> tuple[list[tuple[tuple[int, int, int], tuple[int, int], tuple[int, int], Raksha]], int]:
    """
    Collect valid trip candidates keyed by archetype.

    :return: Candidate list and count of dropped invalid entries.
    """
    by_id = {r.id: r for r in rakshas}
    candidates: list[tuple[tuple[int, int, int], tuple[int, int], tuple[int, int], Raksha]] = []
    dropped = 0
    for travelog in travelogs:
        raksha = by_id.get(travelog.raksha_id)
        if raksha is None or not travelog.survived:
            dropped += 1
            continue
        validated = validate_prescribed_path(travelog.path)
        if validated is None:
            dropped += 1
            continue
        score = _trip_score(travelog, len(validated))
        candidates.append((dna_key(raksha.dna), score, tuple(validated), raksha))
    return candidates, dropped


def build_route_cache(
    travelogs: list[Travelog],
    rakshas: list[Raksha],
) -> list[Route]:
    """
    Build ordered survivor routes: archetype tier first, dominant fallback second.

    :param travelogs: Recent expedition records.
    :param rakshas: Civilization roster for gene lookup.
    :return: Routes ready for StandingOrders.
    """
    if not travelogs:
        return []

    candidates, dropped = _collect_candidates(travelogs, rakshas)
    tier1: dict[tuple[int, int, int], Route] = {}
    tier1_scores: dict[tuple[int, int, int], tuple[int, int]] = {}

    for key, score, path, raksha in candidates:
        existing = tier1_scores.get(key)
        if existing is None or score > existing:
            tier1[key] = Route(criteria=_criteria_for_archetype(raksha), path=path)
            tier1_scores[key] = score

    tier2: dict[GeneType, Route] = {}
    tier2_scores: dict[GeneType, tuple[int, int]] = {}

    for _key, score, path, raksha in candidates:
        dominant = raksha.dna.dominant
        existing = tier2_scores.get(dominant)
        if existing is None or score > existing:
            tier2[dominant] = Route(criteria=_criteria_for_dominant(dominant), path=path)
            tier2_scores[dominant] = score

    routes = list(tier1.values()) + list(tier2.values())
    log.debug(
        "strategy.route_cache_built",
        archetype_routes=len(tier1),
        dominant_fallback_routes=len(tier2),
        candidates_seen=len(candidates),
        dropped_invalid=dropped,
    )
    return routes
