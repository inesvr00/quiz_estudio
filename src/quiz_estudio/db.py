from __future__ import annotations

import sqlite3

from .config import DB_PATH


def init_stats_db() -> None:
    """Crea la base de datos de estadisticas si no existe."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS question_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                enunciado TEXT NOT NULL,
                tema TEXT NOT NULL,
                respuesta_correcta INTEGER NOT NULL,
                respuesta_usuario INTEGER NOT NULL,
                es_correcta INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection
