from __future__ import annotations

from functools import lru_cache

from ..config import DATABASE_URL
from .repositories import AttemptRepository, PostgresAttemptRepository, SqliteAttemptRepository


@lru_cache(maxsize=1)
def get_attempt_repository() -> AttemptRepository:
    if DATABASE_URL:
        return PostgresAttemptRepository(DATABASE_URL)

    return SqliteAttemptRepository()


def init_stats_db() -> None:
    """Crea las tablas de persistencia de uso si no existen."""
    get_attempt_repository().initialize()
