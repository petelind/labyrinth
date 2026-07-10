"""Empirical inference helpers for strategies (no epoch oracle)."""

from __future__ import annotations

from labyrinth.domain.archetypes import all_archetype_dnas, dna_key, format_dna
from labyrinth.domain.entities import Raksha, SquareRecord, Travelog, TurnContext
from labyrinth.domain.types import GeneType, CENTER_SQUARES
from labyrinth.engine.labyrinth import SOMA_REWARD_MAX, SOMA_REWARD_MIN

DEFAULT_SURVIVAL_RATE = 0.5

ArchetypeSurvivalMap = dict[tuple[GeneType, GeneType, GeneType], float]


def per_gene_survival_rates(
    travelogs: list[Travelog],
    rakshas: list[Raksha],
) -> dict[GeneType, float]:
    """
    Compute per-dominant-gene trip survival rates from recent travelogs.

    :param travelogs: Recent trip records from the current turn.
    :param rakshas: Civilization rakshas for gene lookup by id.
    :return: Survival rate per gene type (default 0.5 when no data).
    """
    by_id = {r.id: r for r in rakshas}
    totals: dict[GeneType, list[bool]] = {g: [] for g in GeneType}
    for log in travelogs:
        raksha = by_id.get(log.raksha_id)
        if raksha is None:
            continue
        totals[raksha.dna.dominant].append(log.survived)

    rates = {g: DEFAULT_SURVIVAL_RATE for g in GeneType}
    for gene, outcomes in totals.items():
        if outcomes:
            rates[gene] = sum(outcomes) / len(outcomes)
    return rates


def trap_histogram(known_map: dict[tuple[int, int], SquareRecord]) -> dict[str, int]:
    """
    Count trap types discovered in civilization known_map.

    :param known_map: Squares uncovered by returning scouts.
    :return: Histogram keyed by trap name or ``free``.
    """
    counts: dict[str, int] = {}
    for record in known_map.values():
        key = record.trap_type.name if record.trap_type else "free"
        counts[key] = counts.get(key, 0) + 1
    return counts


def recent_trips_by_gene(
    travelogs: list[Travelog],
    rakshas: list[Raksha],
) -> dict[str, dict[str, int]]:
    """
    Summarize recent trips sent/survived per dominant gene.

    :param travelogs: Recent travelogs.
    :param rakshas: Raksha roster for gene lookup.
    :return: Per-gene dict with sent and survived counts.
    """
    by_id = {r.id: r for r in rakshas}
    summary: dict[str, dict[str, int]] = {
        g.name: {"sent": 0, "survived": 0} for g in GeneType
    }
    for log in travelogs:
        raksha = by_id.get(log.raksha_id)
        if raksha is None:
            continue
        name = raksha.dna.dominant.name
        summary[name]["sent"] += 1
        if log.survived:
            summary[name]["survived"] += 1
    return summary


def gene_counts(rakshas: list[Raksha]) -> dict[str, dict[str, int]]:
    """
    Count alive Rakshas by dominant and secondary gene.

    :param rakshas: Civilization roster.
    :return: Nested dict with dominant and secondary breakdowns.
    """
    dominant = {g.name: 0 for g in GeneType}
    secondary = {g.name: 0 for g in GeneType}
    for raksha in rakshas:
        if not raksha.alive:
            continue
        dominant[raksha.dna.dominant.name] += 1
        secondary[raksha.dna.secondary.name] += 1
    return {"dominant": dominant, "secondary": secondary}


def clone_counts(rakshas: list[Raksha]) -> dict[str, int]:
    """
    Count alive Rakshas per full DNA triple.

    :param rakshas: Civilization roster.
    :return: Map keyed by ``DOM/SEC/REC`` string to alive count.
    """
    counts: dict[str, int] = {}
    for raksha in rakshas:
        if not raksha.alive:
            continue
        label = format_dna(raksha.dna)
        counts[label] = counts.get(label, 0) + 1
    return counts


def update_archetype_survival(
    prior: ArchetypeSurvivalMap,
    travelogs: list[Travelog],
    rakshas: list[Raksha],
) -> ArchetypeSurvivalMap:
    """
    Blend prior archetype survival with last-turn trip outcomes.

    :param prior: Existing cumulative rates per DNA triple.
    :param travelogs: Recent travelogs from the last expedition.
    :param rakshas: Roster for gene lookup by raksha id.
    :return: Updated survival map (new dict, prior unchanged).
    """
    updated = dict(prior)
    if not travelogs:
        return updated
    by_id = {r.id: r for r in rakshas}
    for log_entry in travelogs:
        raksha = by_id.get(log_entry.raksha_id)
        if raksha is None:
            continue
        key = dna_key(raksha.dna)
        old_rate = updated.get(key, DEFAULT_SURVIVAL_RATE)
        outcome = 1.0 if log_entry.survived else 0.0
        updated[key] = (old_rate + outcome) / 2
    return updated


def archetype_survival_snapshot(rates: ArchetypeSurvivalMap) -> dict[str, float]:
    """
    Serialize all 64 archetype survival rates for strategy dashboards.

    :param rates: Cumulative archetype survival map.
    :return: ``DOM/SEC/REC`` string keys to survival rate (0.5 default).
    """
    snapshot: dict[str, float] = {}
    for archetype in all_archetype_dnas():
        key = dna_key(archetype)
        snapshot[format_dna(archetype)] = rates.get(key, DEFAULT_SURVIVAL_RATE)
    return snapshot


def _squares_trap_histogram(squares: dict[tuple[int, int], SquareRecord]) -> dict[str, int]:
    """Count trap types from a travelog squares dict."""
    counts: dict[str, int] = {}
    for record in squares.values():
        key = record.trap_type.name if record.trap_type else "free"
        counts[key] = counts.get(key, 0) + 1
    return counts


def compact_travelogs(
    travelogs: list[Travelog],
    rakshas: list[Raksha],
) -> list[dict[str, object]]:
    """
    Compact last-turn trips for LLM context (no paths or UUIDs).

    :param travelogs: Recent travelogs.
    :param rakshas: Roster for gene lookup.
    :return: List of compact trip summary dicts.
    """
    by_id = {r.id: r for r in rakshas}
    compact: list[dict[str, object]] = []
    for log_entry in travelogs:
        raksha = by_id.get(log_entry.raksha_id)
        if raksha is None:
            continue
        compact.append({
            "gene": format_dna(raksha.dna),
            "survived": log_entry.survived,
            "soma": log_entry.soma_gathered,
            "traps_seen": _squares_trap_histogram(log_entry.squares),
        })
    return compact


def soma_bearing_genes(
    travelogs: list[Travelog],
    rakshas: list[Raksha],
) -> list[str]:
    """
    Dominant genes that returned with soma on the last expedition.

    :param travelogs: Recent travelogs.
    :param rakshas: Roster for gene lookup.
    :return: Sorted unique dominant gene names with soma > 0.
    """
    by_id = {r.id: r for r in rakshas}
    genes: set[str] = set()
    for log_entry in travelogs:
        if log_entry.soma_gathered <= 0:
            continue
        raksha = by_id.get(log_entry.raksha_id)
        if raksha is not None:
            genes.add(raksha.dna.dominant.name)
    return sorted(genes)


def build_strategy_snapshot(
    context: TurnContext,
    archetype_survival: ArchetypeSurvivalMap,
    prior_blackboard: dict[str, str] | None = None,
) -> dict[str, object]:
    """
    Build JSON-serializable turn snapshot for LLM strategy input.

    :param context: Current turn context.
    :param archetype_survival: Cumulative per-archetype survival rates.
    :param prior_blackboard: Optional self-notes from the prior turn.
    :return: Snapshot dict for the user message payload.
    """
    alive = [r for r in context.rakshas if r.alive]
    gene_rates = {
        g.name: per_gene_survival_rates(context.recent_travelogs, context.rakshas)[g]
        for g in GeneType
    }
    snapshot: dict[str, object] = {
        "turn": context.turn_number,
        "soma": context.soma,
        "alive_count": len(alive),
        "turns_remaining": context.turns_remaining,
        "recent_trips": len(context.recent_travelogs),
        "known_squares": len(context.known_map),
        "gene_survival_rates": gene_rates,
        "known_trap_counts": trap_histogram(context.known_map),
        "recent_trips_summary": recent_trips_by_gene(
            context.recent_travelogs, context.rakshas,
        ),
        "gene_counts": gene_counts(context.rakshas),
        "archetype_survival": archetype_survival_snapshot(archetype_survival),
        "clone_counts": clone_counts(context.rakshas),
        "last_travelogs": compact_travelogs(context.recent_travelogs, context.rakshas),
        "soma_bearers": soma_bearing_genes(context.recent_travelogs, context.rakshas),
        "center_squares": [list(coord) for coord in sorted(CENTER_SQUARES)],
        "soma_rule": (
            "Soma is awarded only when a Raksha steps on a center square "
            f"({SOMA_REWARD_MIN}–{SOMA_REWARD_MAX} soma)."
        ),
    }
    if prior_blackboard:
        snapshot["prior_blackboard"] = prior_blackboard
    return snapshot
