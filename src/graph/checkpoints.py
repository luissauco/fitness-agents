"""Persistencia del estado del workflow LangGraph.

Usamos `AsyncSqliteSaver` de `langgraph-checkpoint-sqlite` para serializar el
`FitnessState` entre invocaciones. Se persiste en `output/state.sqlite` por
defecto, configurable con la variable de entorno `FITNESS_STATE_DB`.

`AsyncSqliteSaver.from_conn_string` es un async context manager. Lo exponemos
con un helper que abre/cierra la conexión y lo usaremos como dependencia del
workflow desde el wiring de la CLI.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.config.settings import PROJECT_ROOT

# Ubicación por defecto del fichero SQLite con el estado del grafo.
DEFAULT_STATE_DB: Path = PROJECT_ROOT / "output" / "state.sqlite"


def get_state_db_path() -> Path:
    """Devuelve la ruta del SQLite (env var `FITNESS_STATE_DB` la sobreescribe)."""
    raw: str | None = os.environ.get("FITNESS_STATE_DB")
    return Path(raw) if raw else DEFAULT_STATE_DB


@asynccontextmanager
async def open_async_checkpointer(
    db_path: Path | None = None,
) -> AsyncIterator[AsyncSqliteSaver]:
    """Context manager que abre un `AsyncSqliteSaver` listo para usar.

    Crea el directorio padre si no existe.
    """
    path: Path = db_path or get_state_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn: aiosqlite.Connection = await aiosqlite.connect(str(path))
    try:
        saver: AsyncSqliteSaver = AsyncSqliteSaver(conn)
        await saver.setup()
        yield saver
    finally:
        await conn.close()
