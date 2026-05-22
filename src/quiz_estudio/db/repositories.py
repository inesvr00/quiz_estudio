from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..config import DB_PATH


AttemptRow = tuple[int, str, str, int, int, bool]
SimulacroAttemptRow = tuple[
    str,
    int,
    str,
    str,
    int,
    int | None,
    bool,
]


class AttemptRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_attempts(self, attempts: Iterable[AttemptRow]) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_simulacro_attempts(
        self,
        attempts: Iterable[SimulacroAttemptRow],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_exam_attempt(self, exam_attempt: tuple) -> int:
        """Save a high-level exam attempt summary and return its id."""
        raise NotImplementedError

    @abstractmethod
    def save_exam_topic_stats(self, topic_stats: Iterable[tuple]) -> None:
        """Save per-topic stats for an exam attempt."""
        raise NotImplementedError

    @abstractmethod
    def get_all_exam_attempts(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_exam_attempt_topics(self, exam_attempt_id: int) -> list[dict[str, Any]]:
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS simulacro_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulacro_id TEXT NOT NULL,
                    question_id INTEGER NOT NULL,
                    enunciado TEXT NOT NULL,
                    tema TEXT NOT NULL,
                    respuesta_correcta INTEGER NOT NULL,
                    respuesta_usuario INTEGER,
                    es_correcta INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_simulacro_attempts_simulacro_id
                ON simulacro_attempts (simulacro_id)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exam_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulacro_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    total_questions INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    wrong INTEGER NOT NULL,
                    unanswered INTEGER NOT NULL,
                    net_score REAL NOT NULL,
                    accuracy_percentage REAL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exam_attempt_topic_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_attempt_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    total_questions INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    wrong INTEGER NOT NULL,
                    unanswered INTEGER NOT NULL,
                    accuracy_percentage REAL,
                    FOREIGN KEY (exam_attempt_id) REFERENCES exam_attempts(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_exam_attempts_simulacro_id
                ON exam_attempts (simulacro_id)
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

    def save_simulacro_attempts(
        self,
        attempts: Iterable[SimulacroAttemptRow],
    ) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO simulacro_attempts (
                    simulacro_id,
                    question_id,
                    enunciado,
                    tema,
                    respuesta_correcta,
                    respuesta_usuario,
                    es_correcta
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        simulacro_id,
                        question_id,
                        enunciado,
                        tema,
                        respuesta_correcta,
                        respuesta_usuario,
                        int(es_correcta),
                    )
                    for (
                        simulacro_id,
                        question_id,
                        enunciado,
                        tema,
                        respuesta_correcta,
                        respuesta_usuario,
                        es_correcta,
                    ) in attempts
                ],
            )

    def save_exam_attempt(self, exam_attempt: tuple) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO exam_attempts (
                    simulacro_id,
                    total_questions,
                    correct,
                    wrong,
                    unanswered,
                    net_score,
                    accuracy_percentage
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                exam_attempt,
            )

            return cursor.lastrowid

    def save_exam_topic_stats(self, topic_stats: Iterable[tuple]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO exam_attempt_topic_stats (
                    exam_attempt_id,
                    topic,
                    total_questions,
                    correct,
                    wrong,
                    unanswered,
                    accuracy_percentage
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                list(topic_stats),
            )

    def get_all_exam_attempts(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, simulacro_id, created_at, total_questions, correct, wrong, unanswered, net_score, accuracy_percentage
                FROM exam_attempts
                ORDER BY created_at DESC
                """
            ).fetchall()

        return self._rows_to_dicts(rows)

    def get_exam_attempt_topics(self, exam_attempt_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT topic, total_questions, correct, wrong, unanswered, accuracy_percentage
                FROM exam_attempt_topic_stats
                WHERE exam_attempt_id = ?
                ORDER BY topic
                """,
                (exam_attempt_id,),
            ).fetchall()

        return self._rows_to_dicts(rows)

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
                    CREATE TABLE IF NOT EXISTS simulacro_attempts (
                        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        simulacro_id TEXT NOT NULL,
                        question_id INTEGER NOT NULL,
                        enunciado TEXT NOT NULL,
                        tema TEXT NOT NULL,
                        respuesta_correcta INTEGER NOT NULL,
                        respuesta_usuario INTEGER,
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
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_simulacro_attempts_simulacro_id
                    ON simulacro_attempts (simulacro_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS exam_attempts (
                        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        simulacro_id TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        total_questions INTEGER NOT NULL,
                        correct INTEGER NOT NULL,
                        wrong INTEGER NOT NULL,
                        unanswered INTEGER NOT NULL,
                        net_score DOUBLE PRECISION NOT NULL,
                        accuracy_percentage DOUBLE PRECISION
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS exam_attempt_topic_stats (
                        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        exam_attempt_id BIGINT NOT NULL,
                        topic TEXT NOT NULL,
                        total_questions INTEGER NOT NULL,
                        correct INTEGER NOT NULL,
                        wrong INTEGER NOT NULL,
                        unanswered INTEGER NOT NULL,
                        accuracy_percentage DOUBLE PRECISION,
                        CONSTRAINT fk_exam_attempt FOREIGN KEY (exam_attempt_id) REFERENCES exam_attempts(id) ON DELETE CASCADE
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_exam_attempts_simulacro_id
                    ON exam_attempts (simulacro_id)
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
        normalized_attempts = [
            (
                question_id,
                enunciado,
                tema,
                respuesta_correcta,
                respuesta_usuario,
                bool(es_correcta),
            )
            for (
                question_id,
                enunciado,
                tema,
                respuesta_correcta,
                respuesta_usuario,
                es_correcta,
            ) in attempts
        ]

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
                    normalized_attempts,
                )

    def save_exam_attempt(self, exam_attempt: tuple) -> int:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO exam_attempts (
                        simulacro_id,
                        total_questions,
                        correct,
                        wrong,
                        unanswered,
                        net_score,
                        accuracy_percentage
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    exam_attempt,
                )
                row = cursor.fetchone()

        return row["id"]

    def save_exam_topic_stats(self, topic_stats: Iterable[tuple]) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO exam_attempt_topic_stats (
                        exam_attempt_id,
                        topic,
                        total_questions,
                        correct,
                        wrong,
                        unanswered,
                        accuracy_percentage
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    list(topic_stats),
                )

    def get_all_exam_attempts(self) -> list[dict[str, Any]]:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, simulacro_id, created_at, total_questions, correct, wrong, unanswered, net_score, accuracy_percentage
                        FROM exam_attempts
                        ORDER BY created_at DESC
                        """
                    )
                    rows = cursor.fetchall()

            return rows
        except Exception as exc:  # pragma: no cover - defensive for runtime DB differences
            msg = str(exc).lower()
            if "does not exist" in msg or "relation \"exam_attempts\" does not exist" in msg:
                return []
            raise

    def get_exam_attempt_topics(self, exam_attempt_id: int) -> list[dict[str, Any]]:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT topic, total_questions, correct, wrong, unanswered, accuracy_percentage
                        FROM exam_attempt_topic_stats
                        WHERE exam_attempt_id = %s
                        ORDER BY topic
                        """,
                        (exam_attempt_id,)
                    )
                    rows = cursor.fetchall()

            return rows
        except Exception as exc:  # pragma: no cover - defensive for runtime DB differences
            msg = str(exc).lower()
            if "does not exist" in msg or "relation \"exam_attempt_topic_stats\" does not exist" in msg:
                return []
            raise

    def save_simulacro_attempts(
        self,
        attempts: Iterable[SimulacroAttemptRow],
    ) -> None:
        normalized_attempts = [
            (
                simulacro_id,
                question_id,
                enunciado,
                tema,
                respuesta_correcta,
                respuesta_usuario,
                bool(es_correcta),
            )
            for (
                simulacro_id,
                question_id,
                enunciado,
                tema,
                respuesta_correcta,
                respuesta_usuario,
                es_correcta,
            ) in attempts
        ]

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO simulacro_attempts (
                        simulacro_id,
                        question_id,
                        enunciado,
                        tema,
                        respuesta_correcta,
                        respuesta_usuario,
                        es_correcta
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    normalized_attempts,
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
