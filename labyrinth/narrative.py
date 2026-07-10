"""Turn narrative chronicler — logs that read like book chapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from labyrinth.domain.entities import Epoch, Raksha, StandingOrders, TripResult, TurnSummary
from labyrinth.domain.types import Criterion, CriteriaField, CriteriaOp, GeneType
from labyrinth.logging_config import emit_chapter

if TYPE_CHECKING:
    pass


def _format_value(value: GeneType | int | bool) -> str:
    if isinstance(value, GeneType):
        return value.name
    if isinstance(value, bool):
        return "alive" if value else "dead"
    return str(value)


def format_criterion(criterion: Criterion) -> str:
    """Render one criterion as readable prose."""
    field_name = criterion.field.value.replace("_", " ")
    op_symbols = {
        CriteriaOp.EQ: "is",
        CriteriaOp.NEQ: "is not",
        CriteriaOp.GT: ">",
        CriteriaOp.GTE: ">=",
        CriteriaOp.LT: "<",
        CriteriaOp.LTE: "<=",
    }
    op = op_symbols.get(criterion.op, criterion.op.value)
    return f"{field_name} {op} {_format_value(criterion.value)}"


def format_criteria(criteria: list[Criterion]) -> str:
    """Render criteria list as AND-ed phrase."""
    if not criteria:
        return "none"
    return " AND ".join(format_criterion(c) for c in criteria)


def _gene_label(raksha: Raksha) -> str:
    return raksha.dna.dominant.name


@dataclass
class CivChapter:
    """Narrative lines for one civilization within a turn."""

    name: str
    strategy_label: str
    lines: list[str] = field(default_factory=list)

    def add(self, line: str) -> None:
        self.lines.append(line)


@dataclass
class TurnChronicler:
    """
    Collects turn events and emits a readable chapter at flush.

    Think of each flush as one page/chapter: who deliberated, what they
    ordered, what happened in the labyrinth, and how the turn closed.
    """

    turn_number: int = 0
    turns_total: int = 0
    epoch_name: str = ""
    epoch_turns_left: int = 0
    civ_chapters: list[CivChapter] = field(default_factory=list)
    _current: CivChapter | None = None

    def begin_turn(
        self,
        turn_number: int,
        turns_total: int,
        epoch: Epoch,
    ) -> None:
        """Open a new turn chapter."""
        self.turn_number = turn_number
        self.turns_total = turns_total
        self.epoch_name = epoch.dominant_type.name
        self.epoch_turns_left = epoch.turns_remaining
        self.civ_chapters.clear()
        self._current = None

    def begin_civilization(self, name: str, strategy_label: str) -> None:
        """Start a civilization section within the current turn."""
        self._current = CivChapter(name=name, strategy_label=strategy_label)
        self.civ_chapters.append(self._current)

    def record_opening(self, soma: int, population: int) -> None:
        """Record civilization state at turn open."""
        self._require_current().add(
            f"Opening the turn with {soma} Soma and {population} Rakshas alive."
        )

    def record_thinking(self, text: str) -> None:
        """Record the model's internal thinking stream (Qwen3 deliberation)."""
        if not text.strip():
            return
        chapter = self._require_current()
        chapter.add("Internal deliberation:")
        for paragraph in text.strip().split("\n"):
            paragraph = paragraph.strip()
            if paragraph:
                chapter.add(f"    {paragraph}")

    def record_reasoning(self, text: str) -> None:
        """Record the strategy's stated conclusion (from JSON reasoning field)."""
        if not text.strip():
            return
        chapter = self._require_current()
        chapter.add("Conclusion:")
        for paragraph in text.strip().split("\n"):
            paragraph = paragraph.strip()
            if paragraph:
                chapter.add(f"  {paragraph}")

    def record_deliberation(self, summary: str) -> None:
        """Record the strategy's stated plan for this turn."""
        if summary.strip():
            self._require_current().add(f"Plan: {summary.strip()}")

    def record_orders(
        self,
        orders: StandingOrders,
        *,
        used_fallback: bool = False,
    ) -> None:
        """Record standing orders issued by the strategy."""
        chapter = self._require_current()
        if used_fallback:
            chapter.add(
                "Orders: (fallback — strategy did not finish in time; "
                "reusing previous orders)"
            )
        else:
            chapter.add(
                f"Orders — Weed: {format_criteria(orders.weed_criteria)}; "
                f"Send: {format_criteria(orders.send_criteria)}; "
                f"Reproduce: {format_criteria(orders.reproduce_criteria)}"
            )

    def record_weeding(
        self,
        strategy_killed: list[Raksha],
        mandatory_killed: list[Raksha],
        criteria: list[Criterion],
    ) -> None:
        """Record who was culled and why."""
        chapter = self._require_current()
        if strategy_killed:
            genes = ", ".join(sorted({_gene_label(r) for r in strategy_killed}))
            chapter.add(
                f"Weeding: {len(strategy_killed)} Rakshas culled by strategy "
                f"({format_criteria(criteria)}). Dominant genes affected: {genes}."
            )
        elif criteria:
            chapter.add("Weeding: strategy criteria matched no one.")
        else:
            chapter.add("Weeding: none ordered.")

        if mandatory_killed:
            chapter.add(
                f"Starvation: {len(mandatory_killed)} additional Rakshas died "
                f"— not enough Soma to sustain the population. "
                f"Lowest performers removed first."
            )

    def record_labyrinth(
        self,
        sent: int,
        survived: int,
        died: int,
        soma_gathered: int,
        center_visits: int,
        step_limit_returns: int,
    ) -> None:
        """Record labyrinth expedition outcomes."""
        chapter = self._require_current()
        if sent == 0:
            chapter.add("Labyrinth: no Rakshas were sent.")
            return
        parts = [
            f"{sent} ventured in",
            f"{survived} returned",
            f"{died} perished",
        ]
        if soma_gathered:
            parts.append(f"{soma_gathered} Soma gathered")
        if center_visits:
            parts.append(f"{center_visits} reached the center")
        if step_limit_returns:
            parts.append(f"{step_limit_returns} turned back at the step limit")
        chapter.add(f"Labyrinth: {', '.join(parts)}.")

    def record_reproduction(self, children: int) -> None:
        """Record reproduction outcome."""
        if children:
            self._require_current().add(
                f"Reproduction: {children} new Rakshas born from random pairing."
            )
        else:
            self._require_current().add("Reproduction: none this turn.")

    def record_extinction(self, *, already_extinct: bool = False) -> None:
        """Record civilization extinction."""
        if already_extinct:
            self._require_current().add(
                "Extinction: this civilization was already lost — no actions taken."
            )
        else:
            self._require_current().add(
                "Extinction: no Rakshas remain. This civilization is lost."
            )

    def record_close(self, summary: TurnSummary) -> None:
        """Record turn closing stats for one civilization."""
        self._require_current().add(
            f"Close: Soma {summary.soma_start} → {summary.soma_end}, "
            f"Population {summary.pop_start} → {summary.pop_end}."
        )

    def flush(self) -> str:
        """
        Render and emit the full turn chapter.

        :return: The chapter text that was emitted.
        """
        header = (
            f"\n{'═' * 60}\n"
            f"  CHAPTER {self.turn_number} — Turn {self.turn_number} "
            f"of {self.turns_total}\n"
            f"  Epoch: {self.epoch_name} "
            f"({self.epoch_turns_left} epoch turns remain)\n"
            f"{'═' * 60}"
        )
        sections: list[str] = [header]
        for civ in self.civ_chapters:
            sections.append(
                f"\n▸ {civ.name} ({civ.strategy_label})"
            )
            for line in civ.lines:
                sections.append(f"  {line}")
        sections.append(f"\n{'─' * 60}\n")
        body = "\n".join(sections)
        emit_chapter(body)
        return body

    def _require_current(self) -> CivChapter:
        if self._current is None:
            raise RuntimeError("begin_civilization() must be called first")
        return self._current


def aggregate_trip_results(results: list[TripResult]) -> dict[str, int]:
    """Summarize trip outcomes for narrative."""
    survived = sum(1 for r in results if r.travelog.survived and not r.died)
    died = sum(1 for r in results if r.died)
    soma = sum(r.travelog.soma_gathered for r in results)
    center = sum(
        1 for r in results
        if r.travelog.soma_gathered > 0
    )
    step_limit = sum(1 for r in results if r.travelog.hit_step_limit)
    return {
        "sent": len(results),
        "survived": survived,
        "died": died,
        "soma_gathered": soma,
        "center_visits": center,
        "step_limit_returns": step_limit,
    }
