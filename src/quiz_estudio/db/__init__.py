from __future__ import annotations

from functools import lru_cache

from ..config import DATABASE_URL
from .repositories import AttemptRepository, PostgresAttemptRepository


class DatabaseConfigurationError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_attempt_repository() -> AttemptRepository:
    if not DATABASE_URL:
        raise DatabaseConfigurationError(
            "DATABASE_URL es obligatorio. Configuralo para usar Supabase/PostgreSQL."
        )

    return PostgresAttemptRepository(DATABASE_URL)


def reset_attempt_repository_cache() -> None:
    get_attempt_repository.cache_clear()


def init_stats_db() -> None:
    get_attempt_repository().initialize()
