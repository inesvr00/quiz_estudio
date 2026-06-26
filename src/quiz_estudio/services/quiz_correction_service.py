from __future__ import annotations

import logging
from typing import Any, Callable

from ..question_ids import option_id_for
from ..question_repository import get_question_id


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


def build_option_orders(
    questions: list[dict[str, object]],
    shuffle_options: Callable[[list[str]], None],
) -> dict[str, list[str]]:
    option_orders = {}

    for question in questions:
        options = get_question_options(question)
        option_ids = [option["option_id"] for option in options]
        shuffle_options(option_ids)
        option_orders[get_question_id(question)] = option_ids

    return option_orders


def normalize_option_orders(raw_option_orders: object) -> dict[str, list[str]]:
    if not isinstance(raw_option_orders, dict):
        logger.debug("Estado de opciones invalido en la sesion del quiz.")
        return {}

    option_orders = {}
    for question_key, raw_option_ids in raw_option_orders.items():
        try:
            option_orders[str(question_key)] = [str(option_id) for option_id in raw_option_ids]
        except (TypeError, ValueError):
            logger.debug("Orden de opciones invalido para la pregunta %s.", question_key)

    return option_orders


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
            logger.debug("Falta el orden de opciones para la pregunta %s.", question_key)
            ordered_option_ids = list(options_by_id)

        display_options = []
        for option_id in ordered_option_ids:
            option = options_by_id.get(option_id)
            if option is None:
                logger.debug(
                    "La opcion %s no pertenece a la pregunta %s.",
                    option_id,
                    question_key,
                )
                continue
            display_options.append(option)

        if len(display_options) != len(options_by_id):
            display_options = list(options_by_id.values())

        display_questions.append(
            {
                **question,
                "display_options": display_options,
            }
        )

    return display_questions


def parse_answers(form, questions: list[dict[str, Any]]) -> dict[str, str | None]:
    answers = {}

    for question in questions:
        question_id = get_question_id(question)
        answers[question_id] = parse_selected_option(
            question,
            form.get(f"pregunta_{question_id}"),
        )

    return answers


def correct_questions(
    questions: list[dict[str, Any]],
    answers: dict[str, str | None],
) -> list[dict[str, Any]]:
    corrected_questions = []

    for question in questions:
        question_id = get_question_id(question)
        user_answer = answers.get(question_id)

        corrected_questions.append(
            {
                **question,
                "respuesta_usuario": user_answer,
                "es_correcta": is_correct_option(question, user_answer),
            }
        )

    return corrected_questions


def score_questions(corrected_questions: list[dict[str, Any]]) -> tuple[int, int]:
    return sum(q["es_correcta"] for q in corrected_questions), len(corrected_questions)


def parse_selected_option(question: dict[str, Any], selected: str | None) -> str | None:
    if selected is None:
        return None

    selected_option_id = str(selected)

    valid_option_ids = {
        option["option_id"] for option in get_question_options(question)
    }
    if selected_option_id not in valid_option_ids:
        logger.debug(
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
