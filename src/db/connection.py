"""Conexión SQLite compartida por los repositorios.

Usamos `sqlite3` (síncrono, stdlib) porque las operaciones son cortas y se
ejecutan en el wiring layer de la CLI, no dentro del hot path de los agentes.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src.config.settings import PROJECT_ROOT

# Ruta por defecto del SQLite de modelos (separado del state.sqlite del grafo).
DEFAULT_DB_PATH: Path = PROJECT_ROOT / "output" / "fitness.sqlite"


def get_db_path() -> Path:
    """Ruta del SQLite de modelos. Sobreescribible con `FITNESS_DB`."""
    raw: str | None = os.environ.get("FITNESS_DB")
    return Path(raw) if raw else DEFAULT_DB_PATH


@contextmanager
def open_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Abre una conexión SQLite (con foreign keys) y la cierra al salir."""
    path: Path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn: sqlite3.Connection = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path | None = None) -> None:
    """Crea las tablas si no existen. Idempotente."""
    with open_connection(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)


# ---------------------------------------------------------------- Esquema

_SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS user_profile (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS body_assessment (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    assessed_on TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_body_assessment_user
    ON body_assessment(user_id, assessed_on DESC);

CREATE TABLE IF NOT EXISTS mesocycle (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mesocycle_user
    ON mesocycle(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_plan (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nutrition_plan_user
    ON nutrition_plan(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS progress_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    mesocycle_id TEXT NOT NULL,
    log_date TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_progress_log_user_date
    ON progress_log(user_id, log_date DESC);

CREATE TABLE IF NOT EXISTS telegram_users (
    chat_id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0
);
"""
