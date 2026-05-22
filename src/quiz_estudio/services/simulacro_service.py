from __future__ import annotations

import random
import uuid
from collections import defaultdict
from typing import Any

from ..csv_repository import load_questions
from ..db import get_attempt_repository
from ..exam_config import (
    DEFAULT_SIMULACRO_TOTAL_QUESTIONS,
    EXAM_BLOCKS,
    NETAS_FALLADAS_DIVISOR,
    THEME_JITTER_INTENSITY,
    get_exam_topics,
)


def _resolve_rng(rng: random.Random | None) -> random.Random:
    return rng if rng is not None else random.Random()


def scale_block_sizes(total_questions: int) -> list[int]:
    if total_questions < 0:
        raise ValueError("El numero total de preguntas no puede ser negativo.")

    base_sizes = [block.base_questions for block in EXAM_BLOCKS]
    base_total = sum(base_sizes)
    if base_total == 0:
        return [0 for _ in base_sizes]

    scaled = [total_questions * base_size / base_total for base_size in base_sizes]
    floors = [int(value) for value in scaled]
    remainder = total_questions - sum(floors)

    ranking = sorted(
        range(len(scaled)),
        key=lambda index: (scaled[index] - floors[index], -index),
        reverse=True,
    )

    for index in ranking[:remainder]:
        floors[index] += 1

    return floors


def _remove_question_by_id(
    questions: list[dict[str, Any]],
    question_id: int,
) -> dict[str, Any] | None:
    for index, question in enumerate(questions):
        if question["csv_id"] == question_id:
            return questions.pop(index)

    return None


def _pop_random_question(
    questions: list[dict[str, Any]],
    rng: random.Random,
) -> dict[str, Any]:
    index = rng.randrange(len(questions))
    return questions.pop(index)


def _build_theme_pool(questions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    pool: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for question in questions:
        pool[question["tema"]].append(question)

    return pool


def _ordered_themes_for_output(
    block_topics: tuple[str, ...],
    selected_by_theme: dict[str, list[dict[str, Any]]],
) -> list[str]:
    ordered = [topic for topic in block_topics if selected_by_theme.get(topic)]
    extra_themes = [
        topic
        for topic in get_exam_topics()
        if topic not in block_topics and selected_by_theme.get(topic)
    ]
    extra_themes.extend(
        sorted(
            topic
            for topic in selected_by_theme
            if topic not in block_topics and topic not in extra_themes
        )
    )
    return ordered + extra_themes


def _borrow_from_global_pool(
    remaining_questions: list[dict[str, Any]],
    remaining_needed: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    borrowed: list[dict[str, Any]] = []

    while remaining_needed > 0 and remaining_questions:
        question = _pop_random_question(remaining_questions, rng)
        borrowed.append(question)
        remaining_needed -= 1

    return borrowed


def _remove_from_remaining_pool(
    remaining_pool: dict[str, list[dict[str, Any]]],
    question: dict[str, Any],
) -> None:
    topic = question["tema"]
    topic_questions = remaining_pool.get(topic)
    if not topic_questions:
        return

    _remove_question_by_id(topic_questions, question["csv_id"])
    if not topic_questions:
        remaining_pool.pop(topic, None)


def _build_block_questions(
    block_topics: tuple[str, ...],
    block_target: int,
    remaining_pool: dict[str, list[dict[str, Any]]],
    remaining_questions: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    if block_target <= 0:
        return []

    # Ensure coverage: if a theme from the block has at least one available
    # question, reserve one slot for that theme before applying jitter.
    # If the block has fewer slots than available themes, choose up to
    # `block_target` distinct themes (prioritizing variety). The remaining
    # slots (if any) are distributed with jitter across the eligible themes.
    selected_by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    eligible_themes = [theme for theme in block_topics if remaining_pool.get(theme)]

    # Jittered weights prepared up-front to make theme selection varied.
    jittered_weights = {
        theme: rng.uniform(1 - THEME_JITTER_INTENSITY, 1 + THEME_JITTER_INTENSITY)
        for theme in eligible_themes
    }

    if eligible_themes:
        if block_target >= len(eligible_themes):
            # There is room to include at least one question of every available
            # theme in this block: reserve one question per theme.
            shuffled_themes = list(eligible_themes)
            rng.shuffle(shuffled_themes)

            for theme in shuffled_themes:
                topic_questions = remaining_pool.get(theme, [])
                if not topic_questions:
                    continue

                question = _pop_random_question(topic_questions, rng)
                selected_by_theme[theme].append(question)
                _remove_from_remaining_pool(remaining_pool, question)
                _remove_question_by_id(remaining_questions, question["csv_id"])
        else:
            # Not enough slots to include every theme. Prioritize including as
            # many distinct themes as possible: select `block_target` different
            # themes using jittered weights without replacement.
            available_themes = list(eligible_themes)
            distinct_selected: list[str] = []

            while len(distinct_selected) < block_target and available_themes:
                weights = [jittered_weights[t] for t in available_themes]
                chosen = rng.choices(available_themes, weights=weights, k=1)[0]
                distinct_selected.append(chosen)
                available_themes.remove(chosen)

            # For each chosen theme, take exactly one question.
            for theme in distinct_selected:
                topic_questions = remaining_pool.get(theme, [])
                if not topic_questions:
                    continue

                question = _pop_random_question(topic_questions, rng)
                selected_by_theme[theme].append(question)
                _remove_from_remaining_pool(remaining_pool, question)
                _remove_question_by_id(remaining_questions, question["csv_id"])

    remaining_slots = block_target - sum(len(questions) for questions in selected_by_theme.values())

    # Distribute the remaining slots across eligible themes (those that still
    # have available questions) using jittered weights. This preserves the
    # per-theme coverage guarantee above.
    while remaining_slots > 0:
        available_themes = [theme for theme in eligible_themes if remaining_pool.get(theme)]
        if not available_themes:
            break

        weights = [jittered_weights.get(theme, 1.0) for theme in available_themes]
        chosen_theme = rng.choices(available_themes, weights=weights, k=1)[0]

        topic_questions = remaining_pool.get(chosen_theme, [])
        if not topic_questions:
            # If chosen theme exhausted, try again.
            continue

        question = _pop_random_question(topic_questions, rng)
        selected_by_theme[chosen_theme].append(question)
        _remove_from_remaining_pool(remaining_pool, question)
        _remove_question_by_id(remaining_questions, question["csv_id"])
        remaining_slots -= 1

    if remaining_slots > 0:
        # Fallback separada: si el bloque no tiene suficientes preguntas en sus temas,
        # tomamos preguntas de otros bloques que sigan disponibles para completar el examen.
        borrowed_questions = _borrow_from_global_pool(remaining_questions, remaining_slots, rng)
        for question in borrowed_questions:
            selected_by_theme[question["tema"]].append(question)
            _remove_from_remaining_pool(remaining_pool, question)

    ordered_questions: list[dict[str, Any]] = []
    for theme in _ordered_themes_for_output(block_topics, selected_by_theme):
        ordered_questions.extend(selected_by_theme[theme])

    return ordered_questions


def generate_simulacro_plan(
    questions: list[dict[str, Any]],
    total_questions: int = DEFAULT_SIMULACRO_TOTAL_QUESTIONS,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    random_generator = _resolve_rng(rng)
    remaining_pool = _build_theme_pool(list(questions))
    remaining_questions = list(questions)
    block_sizes = scale_block_sizes(total_questions)

    blocks: list[dict[str, Any]] = []
    for block, block_target in zip(EXAM_BLOCKS, block_sizes):
        block_questions = _build_block_questions(
            block.topics,
            block_target,
            remaining_pool,
            remaining_questions,
            random_generator,
        )

        blocks.append(
            {
                "name": block.name,
                "target": block_target,
                "questions": block_questions,
            }
        )

    flattened_questions = [question for block in blocks for question in block["questions"]]

    return {
        "requested_total": total_questions,
        "generated_total": len(flattened_questions),
        "block_sizes": block_sizes,
        "blocks": blocks,
        "questions": flattened_questions,
        "warning": None
        if len(flattened_questions) == total_questions
        else f"Solo se han podido generar {len(flattened_questions)} de {total_questions} preguntas.",
    }


def build_corrected_questions(
    questions: list[dict[str, Any]],
    form_data: dict[str, Any],
) -> list[dict[str, Any]]:
    corrected_questions: list[dict[str, Any]] = []

    for question in questions:
        csv_id = str(question["csv_id"])
        selected_answer = form_data.get(f"pregunta_{csv_id}")
        user_answer = int(selected_answer) if selected_answer else None

        corrected_questions.append(
            {
                **question,
                "respuesta_usuario": user_answer,
                "es_correcta": user_answer == int(question["respuesta_correcta"]),
            }
        )

    return corrected_questions


def calculate_simulacro_summary(questions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(questions)
    acertadas = sum(1 for question in questions if question["es_correcta"])
    respondidas = sum(1 for question in questions if question["respuesta_usuario"] is not None)
    falladas = respondidas - acertadas
    sin_responder = total - respondidas
    netas = round(acertadas - (falladas / NETAS_FALLADAS_DIVISOR), 2)

    return {
        "total": total,
        "acertadas": acertadas,
        "falladas": falladas,
        "sin_responder": sin_responder,
        "respondidas": respondidas,
        "netas": netas,
        "topics": calculate_simulacro_topic_stats(questions),
    }


def calculate_simulacro_topic_stats(
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    questions_by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for question in questions:
        questions_by_theme[question["tema"]].append(question)

    topic_stats: list[dict[str, Any]] = []
    for theme in get_exam_topics():
        theme_questions = questions_by_theme.get(theme, [])
        if not theme_questions:
            topic_stats.append(
                {
                    "tema": theme,
                    "total": 0,
                    "respondidas": 0,
                    "acertadas": 0,
                    "falladas": 0,
                    "porcentaje": None,
                }
            )
            continue

        respondidas = sum(1 for question in theme_questions if question["respuesta_usuario"] is not None)
        acertadas = sum(1 for question in theme_questions if question["es_correcta"])
        falladas = respondidas - acertadas

        topic_stats.append(
            {
                "tema": theme,
                "total": len(theme_questions),
                "respondidas": respondidas,
                "acertadas": acertadas,
                "falladas": falladas,
                # Se usa acertadas/respondidas para no penalizar las preguntas en blanco.
                "porcentaje": round((acertadas / respondidas) * 100, 1) if respondidas else 0.0,
            }
        )

    return topic_stats


def save_simulacro_attempts(
    simulacro_id: str,
    questions: list[dict[str, Any]],
) -> None:
    attempt_rows = [
        (
            simulacro_id,
            int(question["csv_id"]),
            question["enunciado"],
            question["tema"],
            int(question["respuesta_correcta"]),
            question["respuesta_usuario"],
            bool(question["es_correcta"]),
        )
        for question in questions
    ]

    get_attempt_repository().save_simulacro_attempts(attempt_rows)
    # Además de guardar cada respuesta individual, persistimos
    # un registro de examen (resumen) y las estadísticas por tema.
    summary = calculate_simulacro_summary([
        {**q, "respuesta_usuario": q.get("respuesta_usuario"), "es_correcta": q.get("es_correcta")} for q in questions
    ])

    total = summary["total"]
    acertadas = summary["acertadas"]
    falladas = summary["falladas"]
    sin_responder = summary["sin_responder"]
    netas = summary["netas"]
    accuracy = round((acertadas / total) * 100, 1) if total else None

    exam_attempt = (
        simulacro_id,
        total,
        acertadas,
        falladas,
        sin_responder,
        netas,
        accuracy,
    )

    repo = get_attempt_repository()
    try:
        exam_attempt_id = repo.save_exam_attempt(exam_attempt)
    except Exception:
        # No hacemos fallar el flujo principal si no se puede guardar el resumen,
        # ya que al menos hemos persistido las respuestas individuales.
        return

    topic_rows: list[tuple] = []
    for topic in summary["topics"]:
        porcentaje = topic.get("porcentaje")
        porcentaje_val = None if porcentaje is None else float(porcentaje)
        topic_rows.append(
            (
                exam_attempt_id,
                topic["tema"],
                int(topic["total"]),
                int(topic["acertadas"]),
                int(topic["falladas"]),
                int(topic.get("respondidas", 0) and (topic["total"] - topic.get("respondidas", 0)) or (topic["total"] - topic.get("respondidas", 0))),
                porcentaje_val,
            )
        )

    try:
        repo.save_exam_topic_stats(topic_rows)
    except Exception:
        # Intencionalmente silencioso: no romper el flujo por fallos en métricas adicionales.
        return


def create_simulacro_id() -> str:
    return uuid.uuid4().hex


def load_questions_by_ids(question_ids: list[int]) -> list[dict[str, Any]]:
    questions = load_questions()
    question_by_id = {question["csv_id"]: question for question in questions}

    return [question_by_id[question_id] for question_id in question_ids if question_id in question_by_id]
