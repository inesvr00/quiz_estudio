from __future__ import annotations

import re
import unicodedata
from typing import Any

from .question_repository import (
    get_default_question_repository,
    get_question_id,
    get_topics,
)

PUNCT_TRANSLATION_TABLE = str.maketrans(
    {
        '"': " ",
        "'": " ",
        "‘": " ",
        "’": " ",
        "‚": " ",
        "‛": " ",
        "“": " ",
        "”": " ",
        "„": " ",
        "‟": " ",
        "«": " ",
        "»": " ",
        "´": " ",
        "`": " ",
    }
)


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.translate(PUNCT_TRANSLATION_TABLE)
    normalized = normalized.lower()
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def get_questions_by_ids(
    questions: list[dict[str, Any]],
    question_ids: list[str],
) -> list[dict[str, Any]]:
    questions_by_id = {get_question_id(question): question for question in questions}

    return [questions_by_id[question_id] for question_id in question_ids if question_id in questions_by_id]


def parse_teoria(value: str, row_number: int | None = None) -> int:
    raw_value = value.strip()
    if raw_value not in {"0", "1"}:
        location = f" en la fila {row_number}" if row_number is not None else ""
        raise ValueError(f"teoria debe ser 0 o 1{location}")

    return int(raw_value)


def load_questions() -> list[dict[str, Any]]:
    """Carga y valida las preguntas desde el repositorio configurado."""
    return get_default_question_repository().list_questions()


def get_questions_by_topic_from_csv() -> dict[str, list[dict[str, Any]]]:
    """Lee el CSV principal y agrupa las preguntas validas por tema."""
    return get_default_question_repository().get_questions_by_topic()
