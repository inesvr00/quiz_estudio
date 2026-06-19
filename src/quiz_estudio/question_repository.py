from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Any, Callable, Protocol

from .config import QUESTION_REPOSITORY_BACKEND, QUESTIONS_CSV_PATH
from .question_ids import question_id_to_storage_id, validate_question_ids
from .question_model import (
    AnswerOption,
    Question,
    question_from_csv_row,
    question_to_app_dict,
    validate_csv_header,
)


logger = logging.getLogger(__name__)


class QuestionRepository(Protocol):
    def list_questions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_questions_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_topics(self) -> list[str]:
        raise NotImplementedError

    def get_questions_by_topic(self) -> dict[str, list[dict[str, Any]]]:
        raise NotImplementedError

    def filter_by_mode(
        self,
        questions: list[dict[str, Any]],
        quiz_mode: str,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class CSVQuestionRepository:
    def __init__(self, csv_path: Path = QUESTIONS_CSV_PATH) -> None:
        self.csv_path = csv_path

    def list_questions(self) -> list[dict[str, Any]]:
        return [
            question_to_app_dict(question)
            for question in self._iter_valid_questions("cargar CSV")
        ]

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        questions_by_id = {
            get_question_id(question): question for question in self.list_questions()
        }
        return questions_by_id.get(question_id)

    def get_questions_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        questions_by_id = {
            get_question_id(question): question for question in self.list_questions()
        }
        return [
            questions_by_id[question_id]
            for question_id in question_ids
            if question_id in questions_by_id
        ]

    def list_topics(self) -> list[str]:
        return get_topics(self.list_questions())

    def get_questions_by_topic(self) -> dict[str, list[dict[str, Any]]]:
        questions_by_topic: dict[str, list[dict[str, Any]]] = {}

        for question in self.list_questions():
            questions_by_topic.setdefault(question["tema"], []).append(question)

        return questions_by_topic

    def filter_by_mode(
        self,
        questions: list[dict[str, Any]],
        quiz_mode: str,
    ) -> list[dict[str, Any]]:
        return _filter_questions_by_mode(questions, quiz_mode)

    def _iter_valid_questions(self, context: str) -> list[Question]:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"No se encontro el archivo {self.csv_path}")

        questions = []

        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            if reader.fieldnames is None:
                raise ValueError("El CSV esta vacio o no tiene cabecera.")

            validate_csv_header(reader.fieldnames)
            rows = list(reader)
            id_issues = validate_question_ids(rows)
            if id_issues:
                details = "; ".join(
                    f"fila {issue.row_number}: {issue.detail}"
                    for issue in id_issues
                )
                raise ValueError(f"question_id invalido en CSV: {details}")

            for index, row in enumerate(rows):
                if (
                    not row.get("enunciado")
                    or not row.get("respuesta_correcta")
                    or not row.get("tema")
                ):
                    continue

                try:
                    questions.append(question_from_repository_row(row, index, index + 2))
                except ValueError as exc:
                    logger.warning(
                        "Pregunta descartada al %s en fila %s: %s",
                        context,
                        index + 2,
                        exc,
                    )

        return questions


class SupabaseQuestionRepository:
    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from .supabase_question_client import SupabaseQuestionClient

            client = SupabaseQuestionClient.from_env()

        self.client = client

    def list_questions(self) -> list[dict[str, Any]]:
        remote_questions = [
            question
            for question in self.client.fetch_questions()
            if _is_active_row(question)
        ]
        remote_options = [
            option
            for option in self.client.fetch_answer_options()
            if _is_active_row(option)
        ]
        options_by_question_id: dict[str, list[dict[str, Any]]] = {}

        for option in remote_options:
            question_id = str(option.get("question_id", "")).strip()
            options_by_question_id.setdefault(question_id, []).append(option)

        questions = []
        for csv_id, row in enumerate(remote_questions):
            question_id = str(row.get("question_id", "")).strip()
            if not question_id:
                raise ValueError("Supabase contiene una pregunta activa sin question_id")

            options = sorted(
                options_by_question_id.get(question_id, []),
                key=lambda option: int(option.get("option_order", 0)),
            )
            question = _question_from_supabase_row(row, options, csv_id)
            app_question = question_to_app_dict(question)

            for index, option in enumerate(options):
                app_question["options"][index]["option_id"] = str(
                    option["option_id"]
                ).strip()

            questions.append(app_question)

        return questions

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        questions_by_id = {
            get_question_id(question): question for question in self.list_questions()
        }
        return questions_by_id.get(question_id)

    def get_questions_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        questions_by_id = {
            get_question_id(question): question for question in self.list_questions()
        }
        return [
            questions_by_id[question_id]
            for question_id in question_ids
            if question_id in questions_by_id
        ]

    def list_topics(self) -> list[str]:
        return get_topics(self.list_questions())

    def get_questions_by_topic(self) -> dict[str, list[dict[str, Any]]]:
        questions_by_topic: dict[str, list[dict[str, Any]]] = {}

        for question in self.list_questions():
            questions_by_topic.setdefault(question["tema"], []).append(question)

        return questions_by_topic

    def filter_by_mode(
        self,
        questions: list[dict[str, Any]],
        quiz_mode: str,
    ) -> list[dict[str, Any]]:
        return _filter_questions_by_mode(questions, quiz_mode)


class FallbackQuestionRepository:
    def __init__(
        self,
        primary_factory: Callable[[], QuestionRepository],
        fallback_repository: QuestionRepository,
        primary_label: str = "repositorio primario",
    ) -> None:
        self.primary_factory = primary_factory
        self.fallback_repository = fallback_repository
        self.primary_label = primary_label
        self._primary_repository: QuestionRepository | None = None

    def list_questions(self) -> list[dict[str, Any]]:
        return self._call_with_fallback("list_questions")

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        return self._call_with_fallback("get_question", question_id)

    def get_questions_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        return self._call_with_fallback("get_questions_by_ids", question_ids)

    def list_topics(self) -> list[str]:
        return self._call_with_fallback("list_topics")

    def get_questions_by_topic(self) -> dict[str, list[dict[str, Any]]]:
        return self._call_with_fallback("get_questions_by_topic")

    def filter_by_mode(
        self,
        questions: list[dict[str, Any]],
        quiz_mode: str,
    ) -> list[dict[str, Any]]:
        return self._call_with_fallback("filter_by_mode", questions, quiz_mode)

    def _get_primary_repository(self) -> QuestionRepository:
        if self._primary_repository is None:
            self._primary_repository = self.primary_factory()

        return self._primary_repository

    def _call_with_fallback(self, method_name: str, *args: Any) -> Any:
        try:
            method = getattr(self._get_primary_repository(), method_name)
            return method(*args)
        except Exception as exc:
            logger.warning(
                "%s no disponible al ejecutar %s: %s. Se usa CSV como fallback.",
                self.primary_label,
                method_name,
                exc,
            )
            fallback_method = getattr(self.fallback_repository, method_name)
            return fallback_method(*args)


def question_from_repository_row(
    row: dict[str, Any],
    csv_id: int,
    row_number: int,
) -> Question:
    from .csv_repository import parse_teoria

    teoria = parse_teoria(row.get("teoria", ""), row_number)
    return question_from_csv_row(row, csv_id, teoria)


def get_question_repository(
    backend: str | None = None,
) -> QuestionRepository:
    selected_backend = (
        backend
        or os.getenv("QUESTION_REPOSITORY_BACKEND", QUESTION_REPOSITORY_BACKEND)
    ).strip().lower()

    if selected_backend == "csv":
        return CSVQuestionRepository(QUESTIONS_CSV_PATH)

    if selected_backend == "supabase":
        return SupabaseQuestionRepository()

    if selected_backend == "supabase_with_csv_fallback":
        return FallbackQuestionRepository(
            primary_factory=SupabaseQuestionRepository,
            fallback_repository=CSVQuestionRepository(QUESTIONS_CSV_PATH),
            primary_label="Supabase",
        )

    raise ValueError(
        "QUESTION_REPOSITORY_BACKEND debe ser 'csv', 'supabase' o "
        "'supabase_with_csv_fallback', "
        f"no {selected_backend!r}"
    )


def get_default_question_repository() -> QuestionRepository:
    return get_question_repository()


def get_question_id(question: dict[str, Any]) -> str:
    return str(question["question_id"])


def get_storage_question_id(question: dict[str, Any]) -> int:
    return question_id_to_storage_id(
        question.get("question_id", ""),
        int(question["csv_id"]),
    )


def get_topics(questions: list[dict[str, Any]]) -> list[str]:
    return sorted({question["tema"] for question in questions})


def _question_from_supabase_row(
    row: dict[str, Any],
    options: list[dict[str, Any]],
    csv_id: int,
) -> Question:
    question_id = str(row.get("question_id", "")).strip()
    if not question_id:
        raise ValueError("Supabase contiene una pregunta activa sin question_id")

    if len(options) != 4:
        raise ValueError(
            f"La pregunta {question_id} debe tener exactamente 4 opciones activas"
        )

    answer_options = []
    option_texts = []
    for option in options:
        option_id = str(option.get("option_id", "")).strip()
        if not option_id:
            raise ValueError(f"La pregunta {question_id} contiene una opcion sin option_id")

        text = str(option.get("texto", "")).strip()
        if not text:
            raise ValueError(f"La pregunta {question_id} contiene una opcion vacia")

        option_texts.append(text)
        answer_options.append(
            AnswerOption(
                text=text,
                is_correct=bool(option.get("is_correct", False)),
            )
        )

    if len(set(option_texts)) != len(option_texts):
        raise ValueError(f"La pregunta {question_id} contiene opciones duplicadas")

    if sum(option.is_correct for option in answer_options) != 1:
        raise ValueError(
            f"La pregunta {question_id} debe tener exactamente una opcion correcta"
        )

    return Question(
        question_id=question_id,
        csv_id=csv_id,
        enunciado=str(row.get("enunciado", "")).strip(),
        options=(answer_options[0], answer_options[1], answer_options[2], answer_options[3]),
        explicacion=str(row.get("explicacion", "")).strip(),
        tema=str(row.get("tema", "")).strip(),
        teoria=int(bool(row.get("teoria", False))),
    )


def _is_active_row(row: dict[str, Any]) -> bool:
    return bool(row.get("is_active", True))


def _filter_questions_by_mode(
    questions: list[dict[str, Any]],
    quiz_mode: str,
) -> list[dict[str, Any]]:
    if quiz_mode == "theory":
        return [
            question
            for question in questions
            if int(question.get("teoria", 0)) == 1
        ]

    if quiz_mode == "practical":
        return [
            question
            for question in questions
            if int(question.get("teoria", 0)) == 0
        ]

    return questions
