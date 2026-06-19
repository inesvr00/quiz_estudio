from __future__ import annotations

import pytest

from quiz_estudio import db
from quiz_estudio.db.repositories import PostgresAttemptRepository


@pytest.fixture(autouse=True)
def clear_attempt_repository_cache():
    db.reset_attempt_repository_cache()
    yield
    db.reset_attempt_repository_cache()


def test_database_url_is_required(monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_URL", "")

    with pytest.raises(db.DatabaseConfigurationError, match="DATABASE_URL es obligatorio"):
        db.get_attempt_repository()


def test_database_url_selects_postgres(monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://example")

    repository = db.get_attempt_repository()

    assert isinstance(repository, PostgresAttemptRepository)
