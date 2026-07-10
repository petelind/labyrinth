"""SQLite schema DDL."""

from __future__ import annotations

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL DEFAULT 'game',
    turns_total  INTEGER NOT NULL,
    winner_civ   TEXT,
    played_at    TEXT    NOT NULL,
    seed         INTEGER NOT NULL DEFAULT 42
);

CREATE TABLE IF NOT EXISTS civilizations (
    id            INTEGER PRIMARY KEY,
    game_id       INTEGER NOT NULL REFERENCES games(id),
    name          TEXT    NOT NULL,
    strategy_type TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS epochs (
    id            INTEGER PRIMARY KEY,
    game_id       INTEGER NOT NULL REFERENCES games(id),
    dominant_type TEXT    NOT NULL,
    start_turn    INTEGER NOT NULL,
    end_turn      INTEGER,
    epoch_length  INTEGER NOT NULL DEFAULT 0,
    grid_json     TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    turn_number INTEGER NOT NULL,
    epoch_id    INTEGER NOT NULL REFERENCES epochs(id)
);

CREATE TABLE IF NOT EXISTS turn_summaries (
    id             INTEGER PRIMARY KEY,
    turn_id        INTEGER NOT NULL REFERENCES turns(id),
    civ_id         INTEGER NOT NULL REFERENCES civilizations(id),
    soma_start     INTEGER NOT NULL,
    soma_end       INTEGER NOT NULL,
    pop_start      INTEGER NOT NULL,
    pop_end        INTEGER NOT NULL,
    trips_sent     INTEGER NOT NULL,
    trips_survived INTEGER NOT NULL,
    soma_gathered  INTEGER NOT NULL,
    strategy_sumup TEXT,
    strategy_thinking TEXT
);

CREATE TABLE IF NOT EXISTS rakshas (
    id             TEXT    PRIMARY KEY,
    civ_id         INTEGER NOT NULL REFERENCES civilizations(id),
    dominant_gene  TEXT    NOT NULL,
    secondary_gene TEXT    NOT NULL,
    recessive_gene TEXT    NOT NULL,
    alive          INTEGER NOT NULL DEFAULT 1,
    parent_a_id    TEXT,
    parent_b_id    TEXT
);

CREATE TABLE IF NOT EXISTS trips (
    id            INTEGER PRIMARY KEY,
    turn_id       INTEGER NOT NULL REFERENCES turns(id),
    raksha_id     TEXT    NOT NULL REFERENCES rakshas(id),
    path_json     TEXT,
    survived      INTEGER NOT NULL,
    soma_gathered INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS map_snapshots (
    id             INTEGER PRIMARY KEY,
    turn_id        INTEGER NOT NULL REFERENCES turns(id),
    civ_id         INTEGER NOT NULL REFERENCES civilizations(id),
    knowledge_json TEXT    NOT NULL
);
"""


def migrate(conn) -> None:
    """
    Apply schema migrations to a SQLite connection.

    :param conn: Open sqlite3 connection.
    """
    conn.executescript(SCHEMA_SQL)
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(turn_summaries)").fetchall()
    }
    if "strategy_thinking" not in columns:
        conn.execute("ALTER TABLE turn_summaries ADD COLUMN strategy_thinking TEXT")
    if "went_extinct" not in columns:
        conn.execute("ALTER TABLE turn_summaries ADD COLUMN went_extinct INTEGER DEFAULT 0")
    civ_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(civilizations)").fetchall()
    }
    if "status" not in civ_columns:
        conn.execute("ALTER TABLE civilizations ADD COLUMN status TEXT DEFAULT 'active'")
    if "extinct_turn" not in civ_columns:
        conn.execute("ALTER TABLE civilizations ADD COLUMN extinct_turn INTEGER")
    game_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()
    }
    if "seed" not in game_columns:
        conn.execute("ALTER TABLE games ADD COLUMN seed INTEGER NOT NULL DEFAULT 42")
    epoch_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(epochs)").fetchall()
    }
    if "epoch_length" not in epoch_columns:
        conn.execute("ALTER TABLE epochs ADD COLUMN epoch_length INTEGER NOT NULL DEFAULT 0")
    if "grid_json" not in epoch_columns:
        conn.execute("ALTER TABLE epochs ADD COLUMN grid_json TEXT")
    conn.commit()
