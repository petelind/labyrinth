"""Game persistence repository."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from labyrinth.domain.entities import Civilization, CivilizationStatus, Epoch, TurnSummary
from labyrinth.logging_config import get_logger
from labyrinth.persistence.schema import migrate

if TYPE_CHECKING:
    from labyrinth.engine.turn import CivilizationState

log = get_logger(__name__)


class GameRepository:
    """SQLite persistence for games, turns, and replay data."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._game_id: int | None = None
        self._civ_ids: dict[str, int] = {}
        self._epoch_id: int | None = None

    def initialize(self) -> None:
        """Create schema if not exists."""
        with sqlite3.connect(self._db_path) as conn:
            migrate(conn)
        log.debug("repo.initialized", path=str(self._db_path))

    def create_game(self, turns_total: int, civilizations: list[Civilization]) -> int:
        """
        Insert a new game record.

        :param turns_total: Total turns configured.
        :param civilizations: Initial civilizations.
        :return: Game id.
        """
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT INTO games (name, turns_total, played_at) VALUES (?, ?, ?)",
                ("game", turns_total, now),
            )
            game_id = cur.lastrowid
            assert game_id is not None
            for civ in civilizations:
                cur = conn.execute(
                    """INSERT INTO civilizations
                       (game_id, name, strategy_type, status, extinct_turn)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        game_id,
                        civ.name,
                        "unknown",
                        civ.status.value,
                        civ.extinct_turn,
                    ),
                )
                civ_db_id = cur.lastrowid
                assert civ_db_id is not None
                self._civ_ids[civ.id] = civ_db_id
            conn.commit()
        self._game_id = game_id
        log.info("repo.game_created", game_id=game_id)
        return game_id

    def _ensure_epoch(self, conn: sqlite3.Connection, epoch: Epoch | None, turn_number: int) -> int:
        if epoch is None:
            raise ValueError("Epoch required for persistence")
        if self._epoch_id is None or epoch.turns_remaining == epoch.length - 1:
            cur = conn.execute(
                "INSERT INTO epochs (game_id, dominant_type, start_turn) VALUES (?, ?, ?)",
                (self._game_id, epoch.dominant_type.name, turn_number),
            )
            self._epoch_id = cur.lastrowid
        return self._epoch_id  # type: ignore[return-value]

    def save_turn(
        self,
        turn_number: int,
        epoch: Epoch | None,
        summaries: list[TurnSummary],
        states: list[CivilizationState],
    ) -> None:
        """
        Persist turn summaries and map snapshots.

        :param turn_number: Current turn number.
        :param epoch: Active epoch.
        :param summaries: Per-civ summaries.
        :param states: Civilization states for map snapshots.
        """
        if self._game_id is None:
            return
        with sqlite3.connect(self._db_path) as conn:
            epoch_id = self._ensure_epoch(conn, epoch, turn_number)
            cur = conn.execute(
                "INSERT INTO turns (game_id, turn_number, epoch_id) VALUES (?, ?, ?)",
                (self._game_id, turn_number, epoch_id),
            )
            turn_id = cur.lastrowid
            assert turn_id is not None
            for summary in summaries:
                civ_db_id = self._civ_ids.get(summary.civilization_id)
                if civ_db_id is None:
                    continue
                conn.execute(
                    """INSERT INTO turn_summaries
                       (turn_id, civ_id, soma_start, soma_end, pop_start, pop_end,
                        trips_sent, trips_survived, soma_gathered, strategy_sumup,
                        strategy_thinking, went_extinct)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        turn_id, civ_db_id,
                        summary.soma_start, summary.soma_end,
                        summary.pop_start, summary.pop_end,
                        summary.trips_sent, summary.trips_survived,
                        summary.soma_gathered, summary.strategy_sumup,
                        summary.strategy_thinking,
                        int(summary.went_extinct),
                    ),
                )
            for state in states:
                civ_db_id = self._civ_ids.get(state.civilization.id)
                if civ_db_id is None:
                    continue
                conn.execute(
                    """UPDATE civilizations
                       SET status = ?, extinct_turn = ?
                       WHERE id = ?""",
                    (
                        state.civilization.status.value,
                        state.civilization.extinct_turn,
                        civ_db_id,
                    ),
                )
                knowledge = {
                    f"{x},{y}": {"trap": r.trap_type.name if r.trap_type else None, "is_center": r.is_center}
                    for (x, y), r in state.civilization.known_map.items()
                }
                conn.execute(
                    "INSERT INTO map_snapshots (turn_id, civ_id, knowledge_json) VALUES (?, ?, ?)",
                    (turn_id, civ_db_id, json.dumps(knowledge)),
                )
            conn.commit()
        log.debug("repo.turn_saved", turn=turn_number)

    def finalize_game(self, winner: str | None) -> None:
        """Mark game complete with winner."""
        if self._game_id is None:
            return
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE games SET winner_civ = ? WHERE id = ?",
                (winner, self._game_id),
            )
            conn.commit()
        log.info("repo.game_finalized", winner=winner)

    def turn_count(self) -> int:
        """Return number of persisted turns."""
        if self._game_id is None:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM turns").fetchone()
                return row[0] if row else 0
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM turns WHERE game_id = ?",
                (self._game_id,),
            ).fetchone()
            return row[0] if row else 0

    def load_summaries(self) -> list[TurnSummary]:
        """Load all turn summaries for replay (display only, no re-simulation)."""
        with sqlite3.connect(self._db_path) as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(turn_summaries)").fetchall()
            }
            has_went_extinct = "went_extinct" in columns
            extinct_col = ", ts.went_extinct" if has_went_extinct else ""
            rows = conn.execute(
                f"""SELECT t.turn_number, c.name, ts.soma_start, ts.soma_end,
                          ts.pop_start, ts.pop_end, ts.trips_sent, ts.trips_survived,
                          ts.soma_gathered, ts.strategy_sumup, ts.strategy_thinking
                          {extinct_col}
                   FROM turn_summaries ts
                   JOIN turns t ON ts.turn_id = t.id
                   JOIN civilizations c ON ts.civ_id = c.id
                   ORDER BY t.turn_number, c.name"""
            ).fetchall()
        summaries = []
        for row in rows:
            went_extinct = bool(row[11]) if has_went_extinct else False
            summaries.append(TurnSummary(
                turn_number=row[0],
                civilization_id=row[1],
                soma_start=row[2],
                soma_end=row[3],
                pop_start=row[4],
                pop_end=row[5],
                trips_sent=row[6],
                trips_survived=row[7],
                soma_gathered=row[8],
                strategy_sumup=row[9] or "",
                strategy_thinking=row[10] or "",
                deaths=row[4] - row[5],
                went_extinct=went_extinct,
            ))
        return summaries

    def load_civilization_status(self, civ_id: str) -> tuple[CivilizationStatus, int | None]:
        """
        Load persisted status for a civilization.

        :param civ_id: Civilization string id.
        :return: Status and extinct turn (if any).
        """
        db_id = self._civ_ids.get(civ_id)
        if db_id is None:
            return CivilizationStatus.ACTIVE, None
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT status, extinct_turn FROM civilizations WHERE id = ?",
                (db_id,),
            ).fetchone()
        if row is None:
            return CivilizationStatus.ACTIVE, None
        status = CivilizationStatus(row[0]) if row[0] else CivilizationStatus.ACTIVE
        return status, row[1]
