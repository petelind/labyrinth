"""DNA archetype helpers for population diversity and scouting."""

from __future__ import annotations

from labyrinth.domain.entities import DNA, Raksha
from labyrinth.domain.types import GeneType

ARCHETYPE_GRID_SIZE = 64  # 4 dominant × 4 secondary × 4 recessive
ARCHETYPE_COHORT_SIZE = 96  # 16 dom×sec pairs × 6 members
MEMBERS_PER_DOM_SEC = 6
STRAY_COUNT = 4
INITIAL_RAKSHAS = ARCHETYPE_COHORT_SIZE + STRAY_COUNT


def dna_key(dna: DNA) -> tuple[GeneType, GeneType, GeneType]:
    """Hashable triple for clone / archetype grouping."""
    return (dna.dominant, dna.secondary, dna.recessive)


def all_archetype_dnas() -> list[DNA]:
    """All 64 canonical DNA triples (4³ gene combinations)."""
    return [
        DNA(dominant=d, secondary=s, recessive=r)
        for d in GeneType
        for s in GeneType
        for r in GeneType
    ]


def archetype_similarity(a: DNA, b: DNA) -> int:
    """
    Score how closely two DNA profiles match (higher = more similar).

    :param a: First DNA.
    :param b: Second DNA.
    :return: 0–3 match score.
    """
    score = 0
    if a.dominant == b.dominant:
        score += 1
    if a.secondary == b.secondary:
        score += 1
    if a.recessive == b.recessive:
        score += 1
    return score


def raksha_matches_dna(raksha: Raksha, target: DNA) -> bool:
    """Return True when raksha DNA equals the target triple."""
    return dna_key(raksha.dna) == dna_key(target)


def format_dna(dna: DNA) -> str:
    """Compact label for logs and narrative."""
    return f"{dna.dominant.name}/{dna.secondary.name}/{dna.recessive.name}"
