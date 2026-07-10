"""Tests for survivor route cache builder."""

from __future__ import annotations

from uuid import uuid4

from labyrinth.domain.entities import DNA, Raksha, Travelog
from labyrinth.domain.types import CriteriaField, CriteriaOp, GeneType
from labyrinth.strategy.route_cache import build_route_cache, route_from_travelog


def _raksha(
    dominant: GeneType,
    secondary: GeneType = GeneType.WATER,
    recessive: GeneType = GeneType.EARTH,
) -> Raksha:
    return Raksha(
        id=uuid4(),
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=secondary, recessive=recessive),
    )


def _left_path(steps: int = 5) -> list[tuple[int, int]]:
    return [(0, 49)] + [(x, 49) for x in range(1, steps)]


class TestRouteFromTravelog:
    def test_route_from_travelog_valid_archetype_three_criteria(self) -> None:
        raksha = _raksha(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        path = _left_path()
        travelog = Travelog(raksha.id, path, {}, 50, True)
        route = route_from_travelog(raksha, travelog)
        assert route is not None
        assert len(route.criteria) == 3
        assert route.path == tuple(path)

    def test_route_from_travelog_rejects_non_survivor(self) -> None:
        raksha = _raksha(GeneType.FIRE)
        travelog = Travelog(raksha.id, _left_path(), {}, 0, False)
        assert route_from_travelog(raksha, travelog) is None

    def test_route_from_travelog_rejects_invalid_path(self) -> None:
        raksha = _raksha(GeneType.FIRE)
        travelog = Travelog(raksha.id, [(50, 50), (51, 50)], {}, 0, True)
        assert route_from_travelog(raksha, travelog) is None


class TestBuildRouteCache:
    def test_build_cache_picks_higher_soma_same_archetype(self) -> None:
        raksha = _raksha(GeneType.FIRE)
        short_path = _left_path(3)
        long_path = _left_path(6)
        logs = [
            Travelog(raksha.id, short_path, {}, 10, True),
            Travelog(raksha.id, long_path, {}, 80, True),
        ]
        routes = build_route_cache(logs, [raksha])
        assert len(routes) == 2
        assert routes[0].path == tuple(long_path)
        assert routes[1].path == tuple(long_path)

    def test_build_cache_tier1_before_tier2_ordering(self) -> None:
        fire = _raksha(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        water = _raksha(GeneType.WATER, GeneType.FIRE, GeneType.AIR)
        logs = [
            Travelog(fire.id, _left_path(), {}, 50, True),
            Travelog(water.id, [(99, 49), (98, 49), (97, 49)], {}, 30, True),
        ]
        routes = build_route_cache(logs, [fire, water])
        assert len(routes) == 4
        tier1 = [r for r in routes if len(r.criteria) == 3]
        tier2 = [r for r in routes if len(r.criteria) == 1]
        assert len(tier1) == 2
        assert len(tier2) == 2
        assert {r.criteria[0].value for r in tier1} == {GeneType.FIRE, GeneType.WATER}
        assert {r.criteria[0].value for r in tier2} == {GeneType.FIRE, GeneType.WATER}

    def test_build_cache_dominant_fallback_when_no_archetype_duplicate(self) -> None:
        fire_a = _raksha(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        fire_b = _raksha(GeneType.FIRE, GeneType.AIR, GeneType.WATER)
        logs = [
            Travelog(fire_a.id, _left_path(), {}, 40, True),
            Travelog(fire_b.id, [(0, 50), (1, 50), (2, 50)], {}, 20, True),
        ]
        routes = build_route_cache(logs, [fire_a, fire_b])
        assert len(routes) == 3
        assert all(len(r.criteria) in (1, 3) for r in routes)
        assert sum(1 for r in routes if len(r.criteria) == 3) == 2

    def test_build_cache_includes_dominant_fallback_after_archetype(self) -> None:
        fire = _raksha(GeneType.FIRE)
        logs = [Travelog(fire.id, _left_path(), {}, 25, True)]
        routes = build_route_cache(logs, [fire])
        assert len(routes) == 2
        assert len(routes[0].criteria) == 3
        assert len(routes[1].criteria) == 1
        assert routes[1].criteria[0].value == GeneType.FIRE

    def test_build_cache_empty_travelogs_returns_empty(self) -> None:
        assert build_route_cache([], []) == []
