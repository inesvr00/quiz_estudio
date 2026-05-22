from __future__ import annotations

import sqlite3
from pathlib import Path

from quiz_estudio.db import init_stats_db
from quiz_estudio.config import DB_PATH
from quiz_estudio.db.repositories import SqliteAttemptRepository


def test_init_creates_simulacro_tables_sqlite(tmp_path: Path) -> None:
    # Use the existing DB_PATH (the project uses a local stats.db)
    # Ensure init creates the tables without raising.
    # Initialize sqlite repo explicitly to avoid using DATABASE_URL during tests
    SqliteAttemptRepository().initialize()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}

    assert "exam_attempts" in tables
    assert "exam_attempt_topic_stats" in tables
    assert "simulacro_attempts" in tables

    conn.close()

