from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..config import DB_PATH


AttemptRow = tuple[int, str, str, int, int, bool]


class AttemptRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_attempts(self, attempts: Iterable[AttemptRow]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_seen_question_ids(self) -> set[int]:
        raise NotImplementedError

    @abstractmethod
    def get_seen_question_enunciados_by_topic(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_totals(self) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    def get_topic_totals(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_attempt_topics(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def count_failed_questions(self, tema: str | None = None) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_failed_questions(
        self,
        tema: str | None,
        order_clause: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class SqliteAttemptRepository(AttemptRepository):
    def initialize(self) -> None:
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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def save_attempts(self, attempts: Iterable[AttemptRow]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO question_attempts (
                    question_id,
                    enunciado,
                    tema,
                    respuesta_correcta,
                    respuesta_usuario,
                    es_correcta
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        question_id,
                        enunciado,
                        tema,
                        respuesta_correcta,
                        respuesta_usuario,
                        int(es_correcta),
                    )
                    for (
                        question_id,
                        enunciado,
                        tema,
                        respuesta_correcta,
                        respuesta_usuario,
                        es_correcta,
                    ) in attempts
                ],
            )

    def get_seen_question_ids(self) -> set[int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT question_id
                FROM question_attempts
                """
            ).fetchall()

        return {row["question_id"] for row in rows}

    def get_seen_question_enunciados_by_topic(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT tema, enunciado
                FROM question_attempts
                WHERE enunciado IS NOT NULL
                """
            ).fetchall()

        return self._rows_to_dicts(rows)

    def get_totals(self) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(es_correcta), 0) AS aciertos
                FROM question_attempts
                """
            ).fetchone()

        return dict(row)

    def get_topic_totals(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    tema,
                    COUNT(*) AS total,
                    COALESCE(SUM(es_correcta), 0) AS aciertos
                FROM question_attempts
                GROUP BY tema
                ORDER BY tema
                """
            ).fetchall()

        return self._rows_to_dicts(rows)

    def get_attempt_topics(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT tema
                FROM question_attempts
                ORDER BY tema
                """
            ).fetchall()

        return [row["tema"] for row in rows]

    def count_failed_questions(self, tema: str | None = None) -> int:
        where_clause = "WHERE tema = ?" if tema else ""
        params = (tema,) if tema else ()

        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM (
                    SELECT COUNT(*) - COALESCE(SUM(es_correcta), 0) AS fallos
                    FROM question_attempts
                    {where_clause}
                    GROUP BY question_id, enunciado, tema
                    HAVING fallos > 0
                )
                """,
                params,
            ).fetchone()

        return row["total"]

    def get_failed_questions(
        self,
        tema: str | None,
        order_clause: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        where_clause = "WHERE tema = ?" if tema else ""
        params: tuple[Any, ...] = (tema,) if tema else ()

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    question_id,
                    enunciado,
                    tema,
                    COUNT(*) AS total,
                    COALESCE(SUM(es_correcta), 0) AS aciertos,
                    COUNT(*) - COALESCE(SUM(es_correcta), 0) AS fallos,
                    ((COUNT(*) - COALESCE(SUM(es_correcta), 0)) * 100.0 / COUNT(*)) AS porcentaje_fallo
                FROM question_attempts
                {where_clause}
                GROUP BY question_id, enunciado, tema
                HAVING fallos > 0
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()

        return self._rows_to_dicts(rows)


class PostgresAttemptRepository(AttemptRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = _with_default_sslmode(database_url)

    def initialize(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS question_attempts (
                        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        question_id INTEGER NOT NULL,
                        enunciado TEXT NOT NULL,
                        tema TEXT NOT NULL,
                        respuesta_correcta INTEGER NOT NULL,
                        respuesta_usuario INTEGER NOT NULL,
                        es_correcta BOOLEAN NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_question_attempts_question_id
                    ON question_attempts (question_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_question_attempts_tema
                    ON question_attempts (tema)
                    """
                )

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            prepare_threshold=None,
        )

    def save_attempts(self, attempts: Iterable[AttemptRow]) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO question_attempts (
                        question_id,
                        enunciado,
                        tema,
                        respuesta_correcta,
                        respuesta_usuario,
                        es_correcta
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    list(attempts),
                )

    def get_seen_question_ids(self) -> set[int]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT question_id
                    FROM question_attempts
                    """
                )
                rows = cursor.fetchall()

        return {row["question_id"] for row in rows}

    def get_seen_question_enunciados_by_topic(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tema, enunciado
                    FROM question_attempts
                    WHERE enunciado IS NOT NULL
                    """
                )
                return cursor.fetchall()

    def get_totals(self) -> dict[str, int]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(es_correcta::integer), 0) AS aciertos
                    FROM question_attempts
                    """
                )
                return cursor.fetchone()

    def get_topic_totals(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        tema,
                        COUNT(*) AS total,
                        COALESCE(SUM(es_correcta::integer), 0) AS aciertos
                    FROM question_attempts
                    GROUP BY tema
                    ORDER BY tema
                    """
                )
                return cursor.fetchall()

    def get_attempt_topics(self) -> list[str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT tema
                    FROM question_attempts
                    ORDER BY tema
                    """
                )
                rows = cursor.fetchall()

        return [row["tema"] for row in rows]

    def count_failed_questions(self, tema: str | None = None) -> int:
        where_clause = "WHERE tema = %s" if tema else ""
        params = (tema,) if tema else ()

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM (
                        SELECT COUNT(*) - COALESCE(SUM(es_correcta::integer), 0) AS fallos
                        FROM question_attempts
                        {where_clause}
                        GROUP BY question_id, enunciado, tema
                        HAVING COUNT(*) - COALESCE(SUM(es_correcta::integer), 0) > 0
                    ) AS failed_questions
                    """,
                    params,
                )
                row = cursor.fetchone()

        return row["total"]

    def get_failed_questions(
        self,
        tema: str | None,
        order_clause: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        where_clause = "WHERE tema = %s" if tema else ""
        params: tuple[Any, ...] = (tema,) if tema else ()

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        question_id,
                        enunciado,
                        tema,
                        COUNT(*) AS total,
                        COALESCE(SUM(es_correcta::integer), 0) AS aciertos,
                        COUNT(*) - COALESCE(SUM(es_correcta::integer), 0) AS fallos,
                        ((COUNT(*) - COALESCE(SUM(es_correcta::integer), 0)) * 100.0 / COUNT(*)) AS porcentaje_fallo
                    FROM question_attempts
                    {where_clause}
                    GROUP BY question_id, enunciado, tema
                    HAVING COUNT(*) - COALESCE(SUM(es_correcta::integer), 0) > 0
                    ORDER BY {order_clause}
                    LIMIT %s OFFSET %s
                    """,
                    (*params, limit, offset),
                )
                return cursor.fetchall()


def _with_default_sslmode(database_url: str) -> str:
    parsed_url = urlparse(database_url)
    query = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
    if "sslmode" not in query:
        query["sslmode"] = "require"

    return urlunparse(parsed_url._replace(query=urlencode(query)))
