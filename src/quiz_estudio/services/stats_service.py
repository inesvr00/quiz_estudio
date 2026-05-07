from __future__ import annotations

import sqlite3
from typing import Any

from ..config import DB_PATH, PAGE_SIZE
from ..csv_repository import get_questions_by_topic_from_csv, normalize_text
from ..db import get_db_connection


def save_attempts(questions: list[dict[str, Any]]) -> None:
    attempts = [
        (
            question["csv_id"],
            question["enunciado"],
            question["tema"],
            question["respuesta_correcta"],
            question["respuesta_usuario"],
            int(question["es_correcta"]),
        )
        for question in questions
        if question["respuesta_usuario"] is not None
    ]

    if not attempts:
        return

    with sqlite3.connect(DB_PATH) as connection:
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
            attempts,
        )


def get_seen_question_enunciados_by_topic() -> dict[str, set[str]]:
    seen_by_topic: dict[str, set[str]] = {}

    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT tema, enunciado
            FROM question_attempts
            WHERE enunciado IS NOT NULL
            """
        ).fetchall()

    for row in rows:
        tema = row["tema"]
        enunciado = normalize_text(row["enunciado"])

        if not tema or not enunciado:
            continue

        seen_by_topic.setdefault(tema, set()).add(enunciado)

    return seen_by_topic


def get_statistics() -> dict[str, Any]:
    questions_by_topic = get_questions_by_topic_from_csv()
    seen_enunciados_by_topic = get_seen_question_enunciados_by_topic()

    with get_db_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(es_correcta), 0) AS aciertos
            FROM question_attempts
            """
        ).fetchone()

        topics = connection.execute(
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
        repository_enunciados = {
            normalize_text(question["enunciado"])
            for question in repository_questions
        }
        respondidas_distintas = len(
            repository_enunciados & seen_enunciados_by_topic.get(tema, set())
        )

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
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT tema
            FROM question_attempts
            ORDER BY tema
            """
        ).fetchall()

    return [row["tema"] for row in rows]


def get_failed_questions(
    tema: str | None = None,
    orden: str = "porcentaje",
    page: int = 1,
) -> dict[str, Any]:
    where_clause = ""
    params = ()
    order_clause = (
        "fallos DESC, porcentaje_fallo DESC, total DESC"
        if orden == "fallos"
        else "porcentaje_fallo DESC, fallos DESC, total DESC"
    )

    if tema:
        where_clause = "WHERE tema = ?"
        params = (tema,)

    with get_db_connection() as connection:
        total_rows = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM (
                SELECT
                    COUNT(*) - COALESCE(SUM(es_correcta), 0) AS fallos
                FROM question_attempts
                {where_clause}
                GROUP BY question_id, enunciado, tema
                HAVING fallos > 0
            )
            """,
            params,
        ).fetchone()["total"]

        total_pages = max((total_rows + PAGE_SIZE - 1) // PAGE_SIZE, 1)
        page = min(page, total_pages)
        offset = (page - 1) * PAGE_SIZE

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
            (*params, PAGE_SIZE, offset),
        ).fetchall()

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
    seen_enunciados = get_seen_question_enunciados_by_topic().get(tema, set())

    return [
        question
        for question in questions_by_topic.get(tema, [])
        if normalize_text(question["enunciado"]) not in seen_enunciados
    ]
