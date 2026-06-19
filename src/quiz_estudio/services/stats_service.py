from __future__ import annotations

from typing import Any

from ..config import PAGE_SIZE
from ..csv_repository import get_questions_by_topic_from_csv, normalize_text
from ..db import get_attempt_repository
from ..question_ids import option_index_from_id
from ..question_repository import get_storage_question_id


def save_attempts(questions: list[dict[str, Any]]) -> None:
    attempts = [
        (
            get_storage_question_id(question),
            question["enunciado"],
            question["tema"],
            question["respuesta_correcta"],
            option_index_from_id(question["respuesta_usuario"]) or question["respuesta_usuario"],
            bool(question["es_correcta"]),
        )
        for question in questions
        if question["respuesta_usuario"] is not None
    ]

    if not attempts:
        return

    get_attempt_repository().save_attempts(attempts)


def get_seen_question_enunciados_by_topic() -> dict[str, set[str]]:
    seen_by_topic: dict[str, set[str]] = {}

    rows = get_attempt_repository().get_seen_question_enunciados_by_topic()

    for row in rows:
        tema = row["tema"]
        enunciado = normalize_text(row["enunciado"])

        if not tema or not enunciado:
            continue

        seen_by_topic.setdefault(tema, set()).add(enunciado)

    return seen_by_topic


def get_statistics() -> dict[str, Any]:
    questions_by_topic = get_questions_by_topic_from_csv()
    seen_question_ids = get_attempt_repository().get_seen_question_ids()

    repository = get_attempt_repository()
    totals = repository.get_totals()
    topics = repository.get_topic_totals()

    topic_stats_by_name = {
        row["tema"]: {
            "total": row["total"],
            "aciertos": row["aciertos"],
            "fallos": row["total"] - row["aciertos"],
            "porcentaje": round((row["aciertos"] / row["total"]) * 100, 1),
        }
        for row in topics
    }
    all_topic_names = sorted(set(questions_by_topic) | set(topic_stats_by_name))

    total = totals["total"]
    aciertos = totals["aciertos"]
    fallos = total - aciertos

    topic_rows = []
    for tema in all_topic_names:
        repository_questions = questions_by_topic.get(tema, [])
        repository_question_ids = {
            get_storage_question_id(question) for question in repository_questions
        }
        respondidas_distintas = len(repository_question_ids & seen_question_ids)

        topic_rows.append(
            {
                "tema": tema,
                "preguntas_en_repositorio": len(repository_questions),
                "preguntas_respondidas_distintas": respondidas_distintas,
                "preguntas_no_hechas": len(repository_questions) - respondidas_distintas,
                "total": topic_stats_by_name.get(tema, {}).get("total", 0),
                "aciertos": topic_stats_by_name.get(tema, {}).get("aciertos", 0),
                "fallos": topic_stats_by_name.get(tema, {}).get("fallos", 0),
                "porcentaje": topic_stats_by_name.get(tema, {}).get("porcentaje"),
            }
        )

    return {
        "total": total,
        "aciertos": aciertos,
        "fallos": fallos,
        "porcentaje": round((aciertos / total) * 100, 1) if total else 0,
        "topics": topic_rows,
    }


def get_attempt_topics() -> list[str]:
    return get_attempt_repository().get_attempt_topics()


def get_failed_questions(
    tema: str | None = None,
    orden: str = "porcentaje",
    page: int = 1,
) -> dict[str, Any]:
    order_clause = (
        "fallos DESC, porcentaje_fallo DESC, total DESC"
        if orden == "fallos"
        else "porcentaje_fallo DESC, fallos DESC, total DESC"
    )

    repository = get_attempt_repository()
    total_rows = repository.count_failed_questions(tema)
    total_pages = max((total_rows + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    rows = repository.get_failed_questions(tema, order_clause, PAGE_SIZE, offset)

    return {
        "questions": [
            {
                "question_id": row["question_id"],
                "enunciado": row["enunciado"],
                "tema": row["tema"],
                "total": row["total"],
                "aciertos": row["aciertos"],
                "fallos": row["fallos"],
                "porcentaje_fallo": round(row["porcentaje_fallo"], 1),
            }
            for row in rows
        ],
        "page": page,
        "total_pages": total_pages,
        "total_rows": total_rows,
    }


def get_unseen_questions_by_topic(tema: str) -> list[dict[str, Any]]:
    questions_by_topic = get_questions_by_topic_from_csv()
    seen_question_ids = get_attempt_repository().get_seen_question_ids()

    return [
        question
        for question in questions_by_topic.get(tema, [])
        if get_storage_question_id(question) not in seen_question_ids
    ]
