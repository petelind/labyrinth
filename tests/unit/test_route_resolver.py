"""Tests for criteria-mapped route resolution."""

from __future__ import annotations

from uuid import uuid4

from labyrinth.domain.criteria import matches_all_criteria
from labyrinth.domain.entities import DNA, Raksha, Route
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.engine.route_resolver import resolve_route_for_raksha


def _raksha(dominant: GeneType, *, alive: bool = True) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(
            dominant=dominant,
            secondary=GeneType.WATER,
            recessive=GeneType.EARTH,
        ),
        alive=alive,
    )


def _fire_route() -> Route:
    return Route(
        criteria=(
            Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE),
        ),
        path=((0, 49), (1, 49), (2, 49)),
    )


def _water_route() -> Route:
    return Route(
        criteria=(
            Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.WATER),
        ),
        path=((0, 50), (1, 50), (2, 50)),
    )


class TestResolveRouteForRaksha:
    def test_first_matching_route_wins(self) -> None:
        raksha = _raksha(GeneType.FIRE)
        routes = [_fire_route(), _water_route()]
        path = resolve_route_for_raksha(raksha, routes)
        assert path == [(0, 49), (1, 49), (2, 49)]

    def test_no_match_returns_none(self) -> None:
        raksha = _raksha(GeneType.EARTH)
        path = resolve_route_for_raksha(raksha, [_fire_route()])
        assert path is None

    def test_dead_raksha_never_gets_route(self) -> None:
        raksha = _raksha(GeneType.FIRE, alive=False)
        path = resolve_route_for_raksha(raksha, [_fire_route()])
        assert path is None

    def test_empty_routes_returns_none(self) -> None:
        raksha = _raksha(GeneType.FIRE)
        assert resolve_route_for_raksha(raksha, []) is None


class TestMatchesAllCriteria:
    def test_alive_required_for_route_matching(self) -> None:
        raksha = _raksha(GeneType.FIRE, alive=False)
        criteria = (
            Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE),
        )
        assert matches_all_criteria(raksha, criteria) is False

    def test_matching_criteria_returns_true(self) -> None:
        raksha = _raksha(GeneType.FIRE)
        criteria = (
            Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, GeneType.FIRE),
        )
        assert matches_all_criteria(raksha, criteria) is True
