from __future__ import annotations

import os
from dataclasses import asdict

from .services.question_sync_service import SyncAnswerOption, SyncQuestion


REQUIRED_ENV_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_DATABASE_URL",
]


class MissingSupabaseConfig(RuntimeError):
    pass


class SupabaseQuestionClient:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("SUPABASE_DATABASE_URL", "")

    @classmethod
    def from_env(cls) -> "SupabaseQuestionClient":
        missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
        if missing:
            raise MissingSupabaseConfig(
                "Faltan variables de entorno para conectar con Supabase: "
                + ", ".join(missing)
                + ". Configuralas en tu entorno o usa tests/planificacion sin red."
            )

        return cls(os.environ["SUPABASE_DATABASE_URL"])

    def fetch_questions(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT question_id, enunciado, explicacion, tema, teoria,
                           is_active, content_hash
                    FROM questions
                    """
                )
                return cursor.fetchall()

    def fetch_answer_options(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT option_id, question_id, texto, is_correct, option_order,
                           is_active, content_hash
                    FROM answer_options
                    """
                )
                return cursor.fetchall()

    def upsert_questions(self, questions: list[SyncQuestion]) -> None:
        if not questions:
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO questions (
                        question_id, enunciado, explicacion, tema, teoria,
                        is_active, content_hash, updated_at
                    )
                    VALUES (
                        %(question_id)s, %(enunciado)s, %(explicacion)s, %(tema)s,
                        %(teoria)s, %(is_active)s, %(content_hash)s, now()
                    )
                    ON CONFLICT (question_id) DO UPDATE SET
                        enunciado = EXCLUDED.enunciado,
                        explicacion = EXCLUDED.explicacion,
                        tema = EXCLUDED.tema,
                        teoria = EXCLUDED.teoria,
                        is_active = EXCLUDED.is_active,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = now()
                    """,
                    [asdict(question) for question in questions],
                )

    def upsert_answer_options(self, options: list[SyncAnswerOption]) -> None:
        if not options:
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO answer_options (
                        option_id, question_id, texto, is_correct, option_order,
                        is_active, content_hash, updated_at
                    )
                    VALUES (
                        %(option_id)s, %(question_id)s, %(texto)s, %(is_correct)s,
                        %(option_order)s, %(is_active)s, %(content_hash)s, now()
                    )
                    ON CONFLICT (option_id) DO UPDATE SET
                        question_id = EXCLUDED.question_id,
                        texto = EXCLUDED.texto,
                        is_correct = EXCLUDED.is_correct,
                        option_order = EXCLUDED.option_order,
                        is_active = EXCLUDED.is_active,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = now()
                    """,
                    [asdict(option) for option in options],
                )

    def deactivate_questions(self, questions: list[SyncQuestion]) -> None:
        if not questions:
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE questions
                    SET is_active = FALSE, updated_at = now()
                    WHERE question_id = %(question_id)s
                    """,
                    [asdict(question) for question in questions],
                )

    def deactivate_answer_options(self, options: list[SyncAnswerOption]) -> None:
        if not options:
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE answer_options
                    SET is_active = FALSE, updated_at = now()
                    WHERE option_id = %(option_id)s
                    """,
                    [asdict(option) for option in options],
                )

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)
