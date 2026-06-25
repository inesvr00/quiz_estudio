from __future__ import annotations

import logging
import random
from typing import Any

from ..csv_repository import get_question_id, get_questions_by_ids
from ..question_ids import option_id_for
from .quiz_session_service import get_attempt_question_ids


logger = logging.getLogger(__name__)


def get_question_options(question: dict[str, Any]) -> list[dict[str, Any]]:
    raw_options = question.get("options")

    return [
        {
            "option_id": str(option.get("option_id", option_id_for(get_question_id(question), index))),
            "text": str(option["text"]),
            "is_correct": bool(option["is_correct"]),
        }
        for index, option in enumerate(raw_options or [], start=1)
    ]


def build_option_orders(questions: list[dict[str, object]]) -> dict[str, list[str]]:
    option_orders = {}

    for question in questions:
        options = get_question_options(question)
        option_ids = [option["option_id"] for option in options]
        random.shuffle(option_ids)
        option_orders[get_question_id(question)] = option_ids

    return option_orders


def get_attempt_option_orders(attempt: dict[str, Any]) -> dict[str, list[str]]:
    raw_option_orders = attempt.get("option_order", {})

    if not isinstance(raw_option_orders, dict):
        logger.warning("Estado de opciones invalido para el intento del quiz.")
        return {}

    option_orders = {}
    for question_key, raw_option_ids in raw_option_orders.items():
        if not isinstance(raw_option_ids, list):
            logger.warning(
                "Orden de opciones invalido para la pregunta %s.",
                question_key,
            )
            continue

        option_orders[str(question_key)] = [str(option_id) for option_id in raw_option_ids]

    return option_orders


def get_attempt_questions(
    all_questions: list[dict[str, Any]],
    attempt: dict[str, Any],
) -> list[dict[str, Any]] | None:
    question_ids = get_attempt_question_ids(attempt)
    if not question_ids:
        return None

    questions = get_questions_by_ids(all_questions, question_ids)
    questions_by_id = {get_question_id(question): question for question in questions}

    if len(questions_by_id) != len(question_ids):
        return None

    ordered_questions = [questions_by_id.get(question_id) for question_id in question_ids]
    if any(question is None for question in ordered_questions):
        return None

    option_orders = get_attempt_option_orders(attempt)
    return questions_with_display_options(
        [question for question in ordered_questions if question is not None],
        option_orders,
    )


def questions_with_display_options(
    questions: list[dict[str, Any]],
    option_orders: dict[str, list[str]],
) -> list[dict[str, Any]]:
    display_questions = []

    for question in questions:
        question_key = get_question_id(question)
        options_by_id = {
            option["option_id"]: option for option in get_question_options(question)
        }
        ordered_option_ids = option_orders.get(question_key)

        if not ordered_option_ids:
            logger.warning(
                "Falta el orden de opciones para la pregunta %s.",
                question_key,
            )
            ordered_option_ids = list(options_by_id)

        display_options = []
        for option_id in ordered_option_ids:
            option = options_by_id.get(option_id)
            if option is None:
                logger.warning(
                    "La opcion %s no pertenece a la pregunta %s.",
                    option_id,
                    question_key,
                )
                continue
            display_options.append(option)

        display_option_ids = [option["option_id"] for option in display_options]
        if (
            len(display_option_ids) != len(options_by_id)
            or set(display_option_ids) != set(options_by_id)
        ):
            logger.warning(
                "Orden de opciones incompleto o duplicado para la pregunta %s.",
                question_key,
            )
            display_options = list(options_by_id.values())

        display_questions.append(
            {
                **question,
                "display_options": display_options,
            }
        )

    return display_questions


def parse_selected_option(question: dict[str, Any], selected: str | None) -> str | None:
    if selected is None:
        return None

    selected_option_id = str(selected)

    valid_option_ids = {
        option["option_id"] for option in get_question_options(question)
    }
    if selected_option_id not in valid_option_ids:
        logger.warning(
            "La opcion seleccionada %s no pertenece a la pregunta %s.",
            selected_option_id,
            get_question_id(question),
        )
        return None

    return selected_option_id


def is_correct_option(question: dict[str, Any], selected_option_id: str | None) -> bool:
    if selected_option_id is None:
        return False

    options_by_id = {
        option["option_id"]: option for option in get_question_options(question)
    }
    selected_option = options_by_id.get(selected_option_id)
    return bool(selected_option and selected_option["is_correct"])


def build_corrected_questions(
    all_questions: list[dict[str, Any]],
    attempt: dict[str, Any],
    answers: dict[str, str | None],
) -> list[dict[str, Any]] | None:
    questions = get_attempt_questions(all_questions, attempt)
    if questions is None:
        return None

    return [
        {
            **question,
            "respuesta_usuario": answers.get(get_question_id(question)),
            "es_correcta": is_correct_option(question, answers.get(get_question_id(question))),
        }
        for question in questions
    ]
