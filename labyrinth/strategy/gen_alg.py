"""Genetic-algorithm style strategy."""

from __future__ import annotations

import math
import random
from collections import defaultdict

from labyrinth.domain.archetypes import (
    ARCHETYPE_GRID_SIZE,
    all_archetype_dnas,
    archetype_similarity,
    dna_key,
    format_dna,
    raksha_matches_dna,
)
from labyrinth.domain.entities import DNA, Raksha, StandingOrders, TurnContext, Travelog
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.logging_config import get_logger
from labyrinth.strategy.base import Strategy
from labyrinth.strategy.empirical import per_gene_survival_rates, update_archetype_survival

log = get_logger(__name__)


class GenAlgStrategy(Strategy):
    """
    Archetype-scout genetic strategy.

    Turn 1: full 4×4×4 scout cohort (no weed).
    Turn 2+: harvest best-dominant gene at HARVEST_RATIO; reproduce survivors.
    Mass death on prior harvest re-sends scouts for missing archetypes only.
    """

    HARVEST_RATIO: float = 0.40
    MAX_POPULATION: int = 200
    RESERVE_PER_ARCHETYPE: int = 1
    MASS_DEATH_THRESHOLD: float = 0.25
    MAX_SCOUT_FRACTION: float = 0.20
    SOMA_POP_BUFFER: int = 15
    REPRO_SOMA_FACTOR: float = 1.05
    MIN_SOMA_RUNWAY_TURNS: int = 30
    POP_RUNWAY_FACTOR: float = 1.10
    CONSERVATION_POP: int = 70
    MAX_RAID_SIZE: int = 8
    CONSERVATION_MAX_RAID: int = 4

    def __init__(self) -> None:
        super().__init__()
        self._survival_rates: dict[GeneType, float] = {g: 0.50 for g in GeneType}
        self._archetype_survival: dict[tuple[GeneType, GeneType, GeneType], float] = {}
        self._initial_scout_done: bool = False

    def decide(self, context: TurnContext) -> None:
        if self.should_stop():
            return
        self._update_survival_rates(context.recent_travelogs, context.rakshas)
        counts = self._count_by_gene(context.rakshas)

        send = self._build_send_criteria(context)
        repro = self._build_repro_criteria(context)

        self.set_standing_orders(StandingOrders(
            weed_criteria=[],
            send_criteria=send,
            reproduce_criteria=repro,
            current_strategy_sumup=self._summarize(context, counts),
            last_updated_turn=context.turn_number,
        ))
        if context.chronicler is not None:
            context.chronicler.record_reasoning(self._explain_decision(context, counts))
            context.chronicler.record_deliberation(self._summarize(context, counts))

    def select_send_pool(self, candidates: list[Raksha], context: TurnContext) -> list[Raksha]:
        """
        Scout full archetype grid once, then harvest best-dominant survivors.

        :param candidates: Rakshas matching send_criteria.
        :param context: Current turn context (includes prior-turn travelogs).
        :return: Rakshas to send into the labyrinth.
        """
        alive = [r for r in candidates if r.alive]
        if not alive:
            return []

        if self._needs_scout(context):
            selected = self._scout_pool(alive, context)
            if context.turn_number == 1:
                self._initial_scout_done = True
            log.info(
                "gen_alg.scout_cohort",
                turn=context.turn_number,
                scouts=len(selected),
                archetypes=[format_dna(r.dna) for r in selected],
            )
            return selected

        best = self._inferred_best_gene(
            context.recent_travelogs, context.rakshas, soma=context.soma,
        )
        harvest_pool = [r for r in alive if r.dna.dominant == best]
        if not harvest_pool:
            harvest_pool = alive
        sorted_pool = sorted(
            harvest_pool,
            key=lambda r: (
                self._archetype_survival.get(dna_key(r.dna), 0.5),
                self._dominant_rates_from_archetypes()[r.dna.dominant],
            ),
            reverse=True,
        )
        ratio = self._harvest_ratio(len(alive), len(harvest_pool))
        limit = max(1, math.ceil(ratio * len(harvest_pool)))
        if self._conservation_mode(context):
            limit = min(limit, max(2, len(alive) // 8), self.CONSERVATION_MAX_RAID)
        elif len(alive) < 50:
            limit = min(limit, max(2, len(alive) // 4))
        limit = min(limit, self.MAX_RAID_SIZE)
        selected = sorted_pool[:limit]
        log.info(
            "gen_alg.harvest_pool",
            turn=context.turn_number,
            best_gene=best.name,
            sent=len(selected),
            pool=len(harvest_pool),
        )
        return selected

    def select_repro_pairs(
        self,
        pool: list[Raksha],
        context: TurnContext,
        rng: random.Random,
    ) -> list[tuple[Raksha, Raksha]]:
        """
        Pair trip survivors with the most genetically similar partner.

        :param pool: Eligible parents from reproduce_criteria.
        :param context: Current turn context.
        :param rng: Injectable RNG for tie-breaking.
        :return: Parent pairs for breeding.
        """
        if len(pool) < 2:
            return []

        remaining = sorted(pool, key=lambda r: (-r.trips_survived, -r.trips_completed))
        used: set = set()
        pairs: list[tuple[Raksha, Raksha]] = []

        for anchor in remaining:
            if anchor.id in used:
                continue
            best: Raksha | None = None
            best_score = -1
            mates = [r for r in remaining if r.id != anchor.id and r.id not in used]
            rng.shuffle(mates)
            for candidate in mates:
                score = archetype_similarity(anchor.dna, candidate.dna)
                if score > best_score:
                    best_score = score
                    best = candidate
            if best is not None:
                pairs.append((anchor, best))
                used.add(anchor.id)
                used.add(best.id)

        return pairs

    def _needs_scout(self, context: TurnContext) -> bool:
        """Full scout on turn 1; partial re-scout only after harvest massacre."""
        if self._conservation_mode(context):
            return False
        if context.turn_number == 1:
            return True
        if not self._initial_scout_done:
            return True
        last_survival = self._recent_send_survival(context.recent_travelogs)
        if context.recent_travelogs and last_survival < self.MASS_DEATH_THRESHOLD:
            return True
        return False

    def _conservation_mode(self, context: TurnContext) -> bool:
        """Protect a shrinking population from risky mass expeditions."""
        alive_count = sum(1 for r in context.rakshas if r.alive)
        if context.recent_travelogs and self._recent_send_survival(
            context.recent_travelogs,
        ) < self.MASS_DEATH_THRESHOLD:
            return False
        return alive_count < self.CONSERVATION_POP and context.turns_remaining > 15

    def _scout_pool(self, alive: list[Raksha], context: TurnContext) -> list[Raksha]:
        """One scout per archetype; after turn 1 only gaps without trip data."""
        if context.turn_number == 1:
            targets = all_archetype_dnas()
        else:
            targets = self._archetypes_needing_data(context.recent_travelogs, alive)
        selected: list[Raksha] = []
        for archetype in targets:
            for raksha in alive:
                if raksha_matches_dna(raksha, archetype) and raksha not in selected:
                    selected.append(raksha)
                    break
        if context.turn_number > 1:
            cap = max(1, math.ceil(len(alive) * self.MAX_SCOUT_FRACTION))
            if len(alive) < 50:
                cap = min(cap, max(2, len(alive) // 4))
            selected = selected[:cap]
        return selected

    def _archetypes_needing_data(
        self,
        travelogs: list[Travelog],
        rakshas: list[Raksha],
    ) -> list[DNA]:
        """Archetypes with no recent travelog from an alive representative."""
        by_id = {r.id: r for r in rakshas}
        covered: set[tuple[GeneType, GeneType, GeneType]] = set()
        for log_entry in travelogs:
            raksha = by_id.get(log_entry.raksha_id)
            if raksha is not None:
                covered.add(dna_key(raksha.dna))
        return [
            archetype for archetype in all_archetype_dnas()
            if dna_key(archetype) not in covered
            and any(raksha_matches_dna(r, archetype) for r in rakshas if r.alive)
        ]

    def _recent_send_survival(self, travelogs: list[Travelog]) -> float:
        if not travelogs:
            return 1.0
        survived = sum(1 for t in travelogs if t.survived)
        return survived / len(travelogs)

    def _update_survival_rates(
        self,
        travelogs: list[Travelog],
        rakshas: list[Raksha],
    ) -> None:
        if not travelogs:
            return
        self._archetype_survival = update_archetype_survival(
            self._archetype_survival, travelogs, rakshas,
        )

        rates = per_gene_survival_rates(travelogs, rakshas)
        for gene, rate in rates.items():
            if any(
                r.dna.dominant == gene
                for r in rakshas
                for t in travelogs
                if t.raksha_id == r.id
            ):
                self._survival_rates[gene] = rate
        log.debug(
            "gen_alg.survival_rates_updated",
            rates={g.name: r for g, r in rates.items()},
            best=self._inferred_best_gene(travelogs, rakshas).name,
        )

    def _count_by_gene(self, rakshas: list[Raksha]) -> dict[GeneType, int]:
        counts = {g: 0 for g in GeneType}
        for r in rakshas:
            if r.alive:
                counts[r.dna.dominant] += 1
        return counts

    def _dominant_rates_from_archetypes(self) -> dict[GeneType, float]:
        """Average archetype survival grouped by dominant gene."""
        buckets: dict[GeneType, list[float]] = {g: [] for g in GeneType}
        for (dominant, _secondary, _recessive), rate in self._archetype_survival.items():
            buckets[dominant].append(rate)
        return {
            gene: (sum(values) / len(values) if values else 0.5)
            for gene, values in buckets.items()
        }

    def _harvest_ratio(self, alive_count: int, pool_size: int) -> float:
        """Send fewer raiders when population is small."""
        if alive_count < 30:
            return min(self.HARVEST_RATIO, 0.25)
        if alive_count < 60:
            return min(self.HARVEST_RATIO, 0.35)
        return self.HARVEST_RATIO

    def _inferred_best_gene(
        self,
        travelogs: list[Travelog],
        rakshas: list[Raksha],
        *,
        soma: int | None = None,
    ) -> GeneType:
        """Prefer last-turn multi-gene data; fall back to archetype aggregates."""
        archetype_rates = self._dominant_rates_from_archetypes()
        alive_count = sum(1 for r in rakshas if r.alive)
        if soma is not None and soma < alive_count * 2:
            soma_genes = self._soma_bearing_genes(travelogs, rakshas)
            if soma_genes:
                return max(soma_genes, key=lambda g: archetype_rates[g])
        if travelogs:
            recent = per_gene_survival_rates(travelogs, rakshas)
            by_id = {r.id: r for r in rakshas}
            genes_sent = {
                by_id[t.raksha_id].dna.dominant
                for t in travelogs
                if t.raksha_id in by_id
            }
            if len(genes_sent) >= 2:
                return max(GeneType, key=lambda g: recent[g])
        return max(GeneType, key=lambda g: archetype_rates[g])

    def _population_cap(self, context: TurnContext) -> int:
        """Cap population so soma lasts for remaining turns."""
        alive_count = sum(1 for r in context.rakshas if r.alive)
        runway_turns = max(context.turns_remaining, 1)
        runway_cap = max(20, int(context.soma / runway_turns * self.POP_RUNWAY_FACTOR))
        if context.turns_remaining > 60:
            runway_cap = max(runway_cap, 100)
        sustain_cap = max(10, int(context.soma * 0.90))
        if context.soma < alive_count * 2:
            sustain_cap = max(10, int(context.soma * 0.85))
        return min(self.MAX_POPULATION, runway_cap, sustain_cap)

    def select_cull_targets(self, context: TurnContext) -> list[Raksha]:
        """Cull excess clones when population exceeds soma-backed cap."""
        if context.turn_number == 1 or self._needs_scout(context):
            return []
        alive = [r for r in context.rakshas if r.alive]
        cap = self._population_cap(context)
        if len(alive) <= cap:
            return []
        victims = self._excess_clone_victims(alive, context, len(alive) - cap)
        return victims

    def _excess_clone_victims(
        self,
        alive: list[Raksha],
        context: TurnContext,
        deficit: int,
    ) -> list[Raksha]:
        """Kill lowest-value excess copies, keeping one reserve per archetype."""
        if deficit <= 0:
            return []
        by_key: dict[tuple[GeneType, GeneType, GeneType], list[Raksha]] = defaultdict(list)
        for raksha in alive:
            by_key[dna_key(raksha.dna)].append(raksha)

        soma_genes = self._soma_bearing_genes(context.recent_travelogs, alive)
        best = self._inferred_best_gene(
            context.recent_travelogs, alive, soma=context.soma,
        )
        victims: list[Raksha] = []

        ranked_groups = sorted(
            by_key.items(),
            key=lambda item: (
                0 if item[1][0].dna.dominant == best else 1,
                self._dominant_rates_from_archetypes()[item[1][0].dna.dominant],
                -len(item[1]),
            ),
        )
        for _key, members in ranked_groups:
            if deficit <= 0:
                break
            if members[0].dna.dominant in soma_genes or members[0].dna.dominant == best:
                continue
            if len(members) <= self.RESERVE_PER_ARCHETYPE:
                continue
            sorted_members = sorted(
                members,
                key=lambda r: (r.trips_survived, r.trips_completed),
            )
            for raksha in sorted_members[self.RESERVE_PER_ARCHETYPE:]:
                victims.append(raksha)
                deficit -= 1
                if deficit <= 0:
                    break

        if victims:
            log.info(
                "gen_alg.cull_excess",
                turn=context.turn_number,
                victims=len(victims),
                alive_pop=len(alive),
            )
        return victims

    def _soma_bearing_genes(
        self,
        travelogs: list[Travelog],
        rakshas: list[Raksha],
    ) -> set[GeneType]:
        """Dominant genes that returned with soma on the last expedition."""
        by_id = {r.id: r for r in rakshas}
        genes: set[GeneType] = set()
        for log_entry in travelogs:
            if log_entry.soma_gathered <= 0:
                continue
            raksha = by_id.get(log_entry.raksha_id)
            if raksha is not None:
                genes.add(raksha.dna.dominant)
        return genes

    def _build_send_criteria(self, context: TurnContext) -> list[Criterion]:
        if context.turn_number == 1 or self._needs_scout(context):
            return [Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)]
        if self._conservation_mode(context):
            return [
                Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True),
                Criterion(CriteriaField.TRIPS_SURVIVED, CriteriaOp.GTE, 1),
            ]
        best = self._inferred_best_gene(
            context.recent_travelogs, context.rakshas, soma=context.soma,
        )
        alive = [r for r in context.rakshas if r.alive]
        if any(r.dna.dominant == best for r in alive):
            return [
                Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True),
                Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ, best),
            ]
        return [Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True)]

    def _build_repro_criteria(self, context: TurnContext) -> list[Criterion]:
        alive_count = sum(1 for r in context.rakshas if r.alive)
        if context.soma < alive_count * self.REPRO_SOMA_FACTOR:
            return [Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, False)]
        return [
            Criterion(CriteriaField.TRIPS_SURVIVED, CriteriaOp.GTE, 1),
            Criterion(CriteriaField.ALIVE, CriteriaOp.EQ, True),
        ]

    def _explain_decision(
        self,
        context: TurnContext,
        counts: dict[GeneType, int],
    ) -> str:
        mode = "scout" if self._needs_scout(context) else "harvest"
        best = self._inferred_best_gene(
            context.recent_travelogs, context.rakshas, soma=context.soma,
        )
        last = self._recent_send_survival(context.recent_travelogs)
        return (
            f"{mode.capitalize()} mode. Inferred best gene {best.name} "
            f"({self._dominant_rates_from_archetypes()[best]:.0%}). Prior send survival {last:.0%}. "
            f"Turn 1 full scout ({ARCHETYPE_GRID_SIZE} archetypes); then harvest "
            f"{self.HARVEST_RATIO:.0%} of best-gene pool. Re-scout capped at "
            f"{self.MAX_SCOUT_FRACTION:.0%} of population on mass death."
        )

    def _summarize(self, context: TurnContext, counts: dict[GeneType, int]) -> str:
        mode = "scout" if self._needs_scout(context) else "harvest"
        best = self._inferred_best_gene(
            context.recent_travelogs, context.rakshas, soma=context.soma,
        )
        return (
            f"Turn {context.turn_number}: {mode} mode. "
            f"Inferred best gene {best.name} ({self._dominant_rates_from_archetypes()[best]:.0%}). "
            f"Prior send survival {self._recent_send_survival(context.recent_travelogs):.0%}. "
            f"Gene counts: {', '.join(f'{g.name}={counts[g]}' for g in GeneType)}."
        )
