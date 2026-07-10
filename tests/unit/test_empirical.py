"""Tests for empirical strategy helpers."""

from __future__ import annotations

from uuid import uuid4

from labyrinth.domain.archetypes import ARCHETYPE_GRID_SIZE, format_dna
from labyrinth.domain.entities import DNA, Raksha, SquareRecord, Travelog, TurnContext
from labyrinth.domain.types import GeneType
from labyrinth.strategy.empirical import (
    archetype_survival_snapshot,
    build_strategy_snapshot,
    clone_counts,
    compact_travelogs,
    gene_counts,
    per_gene_survival_rates,
    soma_bearing_genes,
    trap_histogram,
    update_archetype_survival,
)


def _raksha(
    dominant: GeneType,
    secondary: GeneType = GeneType.WATER,
    recessive: GeneType = GeneType.EARTH,
    *,
    alive: bool = True,
) -> Raksha:
    rid = uuid4()
    return Raksha(
        id=rid,
        civilization_id="civ-1",
        dna=DNA(dominant=dominant, secondary=secondary, recessive=recessive),
        alive=alive,
    )


class TestPerGeneSurvivalRates:
    def test_computes_per_gene_rates(self) -> None:
        fire = _raksha(GeneType.FIRE)
        water = _raksha(GeneType.WATER)
        logs = [
            Travelog(fire.id, [(0, 0)], {}, 0, True),
            Travelog(water.id, [(1, 1)], {}, 0, False),
            Travelog(fire.id, [(2, 2)], {}, 0, False),
        ]
        rates = per_gene_survival_rates(logs, [fire, water])
        assert rates[GeneType.FIRE] == 0.5
        assert rates[GeneType.WATER] == 0.0

    def test_empty_travelogs_returns_defaults(self) -> None:
        rates = per_gene_survival_rates([], [])
        assert all(v == 0.5 for v in rates.values())


class TestTrapHistogram:
    def test_counts_trap_types_in_known_map(self) -> None:
        known = {
            (0, 0): SquareRecord(0, 0, GeneType.FIRE),
            (1, 1): SquareRecord(1, 1, GeneType.FIRE),
            (2, 2): SquareRecord(2, 2, None),
        }
        hist = trap_histogram(known)
        assert hist["FIRE"] == 2
        assert hist["free"] == 1


class TestGeneAndCloneCounts:
    def test_gene_counts_alive_only(self) -> None:
        alive = _raksha(GeneType.FIRE, GeneType.WATER)
        dead = _raksha(GeneType.EARTH, GeneType.AIR, alive=False)
        counts = gene_counts([alive, dead])
        assert counts["dominant"]["FIRE"] == 1
        assert counts["dominant"]["EARTH"] == 0
        assert counts["secondary"]["WATER"] == 1

    def test_clone_counts_by_triple(self) -> None:
        a = _raksha(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        b = _raksha(GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        c = _raksha(GeneType.AIR, GeneType.WATER, GeneType.EARTH)
        counts = clone_counts([a, b, c])
        assert counts[format_dna(a.dna)] == 2
        assert counts[format_dna(c.dna)] == 1


class TestArchetypeSurvival:
    def test_update_blends_prior_with_outcome(self) -> None:
        fire = _raksha(GeneType.FIRE)
        logs = [Travelog(fire.id, [(0, 0)], {}, 0, True)]
        updated = update_archetype_survival({}, logs, [fire])
        key = (GeneType.FIRE, GeneType.WATER, GeneType.EARTH)
        assert updated[key] == 0.75

    def test_snapshot_has_all_archetypes(self) -> None:
        snap = archetype_survival_snapshot({})
        assert len(snap) == ARCHETYPE_GRID_SIZE
        assert all(rate == 0.5 for rate in snap.values())


class TestCompactTravelogs:
    def test_compact_includes_traps_and_soma(self) -> None:
        raksha = _raksha(GeneType.FIRE)
        squares = {
            (0, 0): SquareRecord(0, 0, GeneType.FIRE),
            (1, 0): SquareRecord(1, 0, None),
        }
        logs = [Travelog(raksha.id, [(0, 0), (1, 0)], squares, 50, True)]
        compact = compact_travelogs(logs, [raksha])
        assert len(compact) == 1
        assert compact[0]["gene"] == format_dna(raksha.dna)
        assert compact[0]["soma"] == 50
        assert compact[0]["traps_seen"]["FIRE"] == 1


class TestSomaBearingGenes:
    def test_returns_dominant_with_soma(self) -> None:
        fire = _raksha(GeneType.FIRE)
        water = _raksha(GeneType.WATER)
        logs = [
            Travelog(fire.id, [(0, 0)], {}, 40, True),
            Travelog(water.id, [(1, 0)], {}, 0, True),
        ]
        assert soma_bearing_genes(logs, [fire, water]) == ["FIRE"]


class TestBuildStrategySnapshot:
    def test_includes_new_fields_no_epoch(self) -> None:
        ctx = TurnContext(
            turn_number=2,
            soma=500,
            rakshas=[_raksha(GeneType.FIRE)],
            recent_travelogs=[],
            known_map={},
            turns_remaining=18,
        )
        snap = build_strategy_snapshot(ctx, {})
        assert "gene_counts" in snap
        assert "archetype_survival" in snap
        assert "clone_counts" in snap
        assert "last_travelogs" in snap
        assert "soma_bearers" in snap
        assert "center_squares" in snap
        assert "soma_rule" in snap
        assert snap["center_squares"] == [[49, 49], [49, 50], [50, 49], [50, 50]]
        assert "epoch" not in snap

    def test_includes_prior_blackboard_when_set(self) -> None:
        ctx = TurnContext(
            turn_number=3,
            soma=500,
            rakshas=[],
            recent_travelogs=[],
            known_map={},
            turns_remaining=17,
        )
        board = {"phase": "harvest", "current_plan": "send FIRE"}
        snap = build_strategy_snapshot(ctx, {}, prior_blackboard=board)
        assert snap["prior_blackboard"] == board
