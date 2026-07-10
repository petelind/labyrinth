"""Game persistence repository."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from labyrinth.domain.entities import Civilization, CivilizationStatus, Epoch, SquareRecord, TurnSummary
from labyrinth.domain.types import GeneType, LABYRINTH_SIZE
from labyrinth.logging_config import get_logger
from labyrinth.persistence.schema import migrate

if TYPE_CHECKING:
    from labyrinth.engine.labyrinth import Labyrinth
    from labyrinth.engine.turn import CivilizationState

log = get_logger(__name__)


@dataclass
class ReplayFrame:
    """One turn's worth of data needed to replay a saved game in the GUI."""

    turn_number: int
    epoch_dominant: GeneType
    epoch_turns_remaining: int
    epoch_length: int
    grid: dict[tuple[int, int], GeneType | None]
    summaries: list[TurnSummary]
    known_maps: dict[str, dict[tuple[int, int], SquareRecord]] = field(default_factory=dict)


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

    def create_game(
        self,
        turns_total: int,
        civilizations: list[Civilization],
        seed: int = 42,
    ) -> int:
        """
        Insert a new game record.

        :param turns_total: Total turns configured.
        :param civilizations: Initial civilizations.
        :param seed: RNG seed used for labyrinth generation (needed for replay).
        :return: Game id.
        """
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT INTO games (name, turns_total, played_at, seed) VALUES (?, ?, ?, ?)",
                ("game", turns_total, now, seed),
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

    def _serialize_grid(self, labyrinth: Labyrinth) -> str:
        """Serialize only trap squares to a compact JSON string."""
        trap_squares = {
            f"{x},{y}": trap.name
            for (x, y), trap in labyrinth.grid.items()
            if trap is not None
        }
        return json.dumps(trap_squares)

    def _ensure_epoch(
        self,
        conn: sqlite3.Connection,
        epoch: Epoch | None,
        turn_number: int,
        labyrinth: Labyrinth | None = None,
    ) -> int:
        if epoch is None:
            raise ValueError("Epoch required for persistence")
        if self._epoch_id is None or epoch.turns_remaining == epoch.length - 1:
            grid_json = self._serialize_grid(labyrinth) if labyrinth is not None else None
            cur = conn.execute(
                """INSERT INTO epochs (game_id, dominant_type, start_turn, epoch_length, grid_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (self._game_id, epoch.dominant_type.name, turn_number, epoch.length, grid_json),
            )
            self._epoch_id = cur.lastrowid
        return self._epoch_id  # type: ignore[return-value]

    def save_turn(
        self,
        turn_number: int,
        epoch: Epoch | None,
        summaries: list[TurnSummary],
        states: list[CivilizationState],
        labyrinth: Labyrinth | None = None,
    ) -> None:
        """
        Persist turn summaries and map snapshots.

        :param turn_number: Current turn number.
        :param epoch: Active epoch.
        :param summaries: Per-civ summaries.
        :param states: Civilization states for map snapshots.
        :param labyrinth: Active labyrinth (used to snapshot grid on epoch change).
        """
        if self._game_id is None:
            return
        with sqlite3.connect(self._db_path) as conn:
            epoch_id = self._ensure_epoch(conn, epoch, turn_number, labyrinth)
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

    @staticmethod
    def load_replay_data(
        db_path: Path,
    ) -> tuple[int, list[tuple[str, str]], list[ReplayFrame]]:
        """
        Load all data needed to replay a saved game.

        :param db_path: Path to the SQLite save file.
        :return: Tuple of (turns_total, [(civ_id, civ_name)], frames).
        :raises FileNotFoundError: If db_path does not exist.
        :raises ValueError: If the file contains no game record.
        """
        if not db_path.exists():
            raise FileNotFoundError(f"Save file not found: {db_path}")

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row

            game_row = conn.execute(
                "SELECT id, turns_total FROM games ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if game_row is None:
                raise ValueError("No game record found in the save file.")
            game_id: int = game_row["id"]
            turns_total: int = game_row["turns_total"]

            # Civilizations: id is derived from name (engine convention)
            civ_rows = conn.execute(
                "SELECT id, name FROM civilizations WHERE game_id = ? ORDER BY id",
                (game_id,),
            ).fetchall()
            civ_db_id_to_id: dict[int, str] = {}
            civ_db_id_to_name: dict[int, str] = {}
            civ_infos: list[tuple[str, str]] = []
            for row in civ_rows:
                db_id: int = row["id"]
                name: str = row["name"]
                civ_id = name.lower().replace(" ", "-")
                civ_db_id_to_id[db_id] = civ_id
                civ_db_id_to_name[db_id] = name
                civ_infos.append((civ_id, name))

            # Turns joined with epoch info
            turn_rows = conn.execute(
                """SELECT t.id, t.turn_number,
                          e.dominant_type, e.start_turn, e.epoch_length, e.grid_json
                   FROM turns t
                   JOIN epochs e ON t.epoch_id = e.id
                   WHERE t.game_id = ?
                   ORDER BY t.turn_number""",
                (game_id,),
            ).fetchall()

            # Turn summaries keyed by turn_id
            summary_rows = conn.execute(
                """SELECT ts.turn_id, ts.civ_id,
                          ts.soma_start, ts.soma_end, ts.pop_start, ts.pop_end,
                          ts.trips_sent, ts.trips_survived, ts.soma_gathered,
                          ts.strategy_sumup, ts.strategy_thinking,
                          COALESCE(ts.went_extinct, 0) AS went_extinct
                   FROM turn_summaries ts
                   JOIN turns t ON ts.turn_id = t.id
                   WHERE t.game_id = ?
                   ORDER BY t.turn_number, ts.civ_id""",
                (game_id,),
            ).fetchall()
            summaries_by_turn: dict[int, list[TurnSummary]] = {}
            for row in summary_rows:
                tid: int = row["turn_id"]
                civ_id_norm = civ_db_id_to_id.get(row["civ_id"], str(row["civ_id"]))
                ts = TurnSummary(
                    turn_number=0,  # filled below
                    civilization_id=civ_id_norm,
                    soma_start=row["soma_start"],
                    soma_end=row["soma_end"],
                    pop_start=row["pop_start"],
                    pop_end=row["pop_end"],
                    trips_sent=row["trips_sent"],
                    trips_survived=row["trips_survived"],
                    soma_gathered=row["soma_gathered"],
                    strategy_sumup=row["strategy_sumup"] or "",
                    strategy_thinking=row["strategy_thinking"] or "",
                    deaths=row["pop_start"] - row["pop_end"],
                    went_extinct=bool(row["went_extinct"]),
                )
                summaries_by_turn.setdefault(tid, []).append(ts)

            # Map snapshots keyed by turn_id → {civ_id: knowledge_json}
            snapshot_rows = conn.execute(
                """SELECT ms.turn_id, ms.civ_id, ms.knowledge_json
                   FROM map_snapshots ms
                   JOIN turns t ON ms.turn_id = t.id
                   WHERE t.game_id = ?""",
                (game_id,),
            ).fetchall()
            snapshots_by_turn: dict[int, dict[str, str]] = {}
            for row in snapshot_rows:
                tid = row["turn_id"]
                civ_id_norm = civ_db_id_to_id.get(row["civ_id"], str(row["civ_id"]))
                snapshots_by_turn.setdefault(tid, {})[civ_id_norm] = row["knowledge_json"]

        frames: list[ReplayFrame] = []
        _empty_grid: dict[tuple[int, int], GeneType | None] = {
            (x, y): None
            for x in range(LABYRINTH_SIZE)
            for y in range(LABYRINTH_SIZE)
        }
        _cached_grid: dict[tuple[int, int], GeneType | None] | None = None
        _cached_grid_json: str | None = None

        for turn_row in turn_rows:
            turn_id: int = turn_row["id"]
            turn_number: int = turn_row["turn_number"]
            dominant_type = GeneType[turn_row["dominant_type"]]
            start_turn: int = turn_row["start_turn"]
            epoch_length: int = turn_row["epoch_length"] or 1
            grid_json_str: str | None = turn_row["grid_json"]

            turns_remaining = max(1, epoch_length - (turn_number - start_turn))

            # Parse grid (cache to avoid re-parsing same epoch's grid repeatedly)
            if grid_json_str is not None and grid_json_str != _cached_grid_json:
                _cached_grid_json = grid_json_str
                parsed = json.loads(grid_json_str)
                new_grid = dict(_empty_grid)
                for key, trap_name in parsed.items():
                    x_str, y_str = key.split(",")
                    new_grid[(int(x_str), int(y_str))] = GeneType[trap_name]
                _cached_grid = new_grid
            grid = dict(_cached_grid) if _cached_grid is not None else dict(_empty_grid)

            # Attach turn_number to summaries
            turn_summaries = summaries_by_turn.get(turn_id, [])
            for ts in turn_summaries:
                ts.turn_number = turn_number

            # Parse known maps
            known_maps: dict[str, dict[tuple[int, int], SquareRecord]] = {}
            for civ_id_norm, kj in snapshots_by_turn.get(turn_id, {}).items():
                kmap: dict[tuple[int, int], SquareRecord] = {}
                for coord_key, val in json.loads(kj).items():
                    kx, ky = map(int, coord_key.split(","))
                    trap_name = val.get("trap")
                    trap_type = GeneType[trap_name] if trap_name else None
                    kmap[(kx, ky)] = SquareRecord(
                        x=kx,
                        y=ky,
                        trap_type=trap_type,
                        is_center=val.get("is_center", False),
                    )
                known_maps[civ_id_norm] = kmap

            frames.append(ReplayFrame(
                turn_number=turn_number,
                epoch_dominant=dominant_type,
                epoch_turns_remaining=turns_remaining,
                epoch_length=epoch_length,
                grid=grid,
                summaries=turn_summaries,
                known_maps=known_maps,
            ))

        log.info("repo.replay_data_loaded", turns=len(frames), game_id=game_id)
        return turns_total, civ_infos, frames

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
