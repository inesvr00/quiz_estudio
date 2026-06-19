from __future__ import annotations

import logging
import random
from typing import Any

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..config import ALLOWED_BATCH_SIZES
from ..csv_repository import get_question_id, get_questions_by_ids, get_topics, load_questions
from ..question_ids import option_id_for
from ..services.quiz_service import (
    QUIZ_MODE_PRACTICAL,
    QUIZ_MODE_STANDARD,
    QUIZ_MODE_THEORY,
    select_quiz_questions,
)
from ..services.stats_service import save_attempts


quiz_bp = Blueprint("quiz", __name__)
logger = logging.getLogger(__name__)


def _get_question_ids() -> list[str]:
    raw_question_ids = session.get("question_ids", [])

    if not isinstance(raw_question_ids, list):
        return []

    return [str(question_id) for question_id in raw_question_ids]


def _store_quiz_state(
    selected_questions: list[dict[str, object]],
    selected_topics: list[str],
    batch_size: int,
    quiz_mode: str,
    warning: str | None,
) -> None:
    session["question_ids"] = [get_question_id(question) for question in selected_questions]
    session["option_orders"] = _build_option_orders(selected_questions)
    session["selected_topics"] = selected_topics
    session["batch_size"] = batch_size
    session["quiz_mode"] = quiz_mode
    session.pop("questions", None)

    if warning:
        session["quiz_notice"] = warning
    else:
        session.pop("quiz_notice", None)


def _clear_stale_quiz_state() -> None:
    session.pop("questions", None)


def _get_question_options(question: dict[str, Any]) -> list[dict[str, Any]]:
    raw_options = question.get("options")

    return [
        {
            "option_id": str(option.get("option_id", option_id_for(get_question_id(question), index))),
            "text": str(option["text"]),
            "is_correct": bool(option["is_correct"]),
        }
        for index, option in enumerate(raw_options or [], start=1)
    ]


def _build_option_orders(questions: list[dict[str, object]]) -> dict[str, list[str]]:
    option_orders = {}

    for question in questions:
        options = _get_question_options(question)
        option_ids = [option["option_id"] for option in options]
        random.shuffle(option_ids)
        option_orders[get_question_id(question)] = option_ids

    return option_orders


def _get_option_orders() -> dict[str, list[str]]:
    raw_option_orders = session.get("option_orders", {})

    if not isinstance(raw_option_orders, dict):
        logger.warning("Estado de opciones invalido en la sesion del quiz.")
        return {}

    option_orders = {}
    for question_key, raw_option_ids in raw_option_orders.items():
        try:
            option_orders[str(question_key)] = [str(option_id) for option_id in raw_option_ids]
        except (TypeError, ValueError):
            logger.warning(
                "Orden de opciones invalido para la pregunta %s.",
                question_key,
            )

    return option_orders


def _questions_with_display_options(
    questions: list[dict[str, Any]],
    option_orders: dict[str, list[str]],
) -> list[dict[str, Any]]:
    display_questions = []

    for question in questions:
        question_key = get_question_id(question)
        options_by_id = {
            option["option_id"]: option for option in _get_question_options(question)
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

        if len(display_options) != len(options_by_id):
            display_options = list(options_by_id.values())

        display_questions.append(
            {
                **question,
                "display_options": display_options,
            }
        )

    return display_questions


def _parse_selected_option(question: dict[str, Any], selected: str | None) -> str | None:
    if selected is None:
        return None

    selected_option_id = str(selected)

    valid_option_ids = {
        option["option_id"] for option in _get_question_options(question)
    }
    if selected_option_id not in valid_option_ids:
        logger.warning(
            "La opcion seleccionada %s no pertenece a la pregunta %s.",
            selected_option_id,
            get_question_id(question),
        )
        return None

    return selected_option_id


def _is_correct_option(question: dict[str, Any], selected_option_id: str | None) -> bool:
    if selected_option_id is None:
        return False

    options_by_id = {
        option["option_id"]: option for option in _get_question_options(question)
    }
    selected_option = options_by_id.get(selected_option_id)
    return bool(selected_option and selected_option["is_correct"])


def _parse_batch_size(form) -> tuple[int, str | None]:
    mode = (form.get("quiz_size_mode") or form.get("batch_size") or "10").strip()
    custom_raw = (form.get("custom_num_preguntas") or form.get("custom_batch_size") or "").strip()

    if mode == "custom":
        try:
            custom_size = int(custom_raw)
        except ValueError:
            return 10, "El número personalizado debe ser un entero mayor que 0."

        if custom_size <= 0:
            return 10, "El número personalizado debe ser mayor que 0."

        return custom_size, None

    try:
        selected_size = int(mode)
    except ValueError:
        selected_size = 10

    if selected_size not in ALLOWED_BATCH_SIZES:
        selected_size = 10

    return selected_size, None


def _parse_quiz_mode(form) -> str:
    mode = (form.get("quiz_mode") or QUIZ_MODE_STANDARD).strip()

    if mode not in {QUIZ_MODE_STANDARD, QUIZ_MODE_THEORY, QUIZ_MODE_PRACTICAL}:
        return QUIZ_MODE_STANDARD

    return mode


@quiz_bp.route("/", methods=["GET", "POST"])
def index():
    _clear_stale_quiz_state()
    questions = load_questions()
    topics = get_topics(questions)

    if request.method == "POST":
        selected_topics = request.form.getlist("temas")
        batch_size, warning = _parse_batch_size(request.form)
        quiz_mode = _parse_quiz_mode(request.form)

        if not selected_topics:
            selected_topics = topics

        selected_questions = select_quiz_questions(
            questions,
            selected_topics,
            batch_size,
            quiz_mode,
        )

        if not selected_questions:
            return render_template(
                "index.html",
                topics=topics,
                selected_topics=selected_topics,
                selected_batch_size=str(batch_size),
                selected_quiz_mode=quiz_mode,
                error="No hay preguntas para los temas y modo seleccionados.",
            )

        if batch_size > len(selected_questions):
            warning = (
                f"Solo hay {len(selected_questions)} preguntas disponibles para los temas seleccionados. "
                f"Se usará ese máximo."
            )

        _store_quiz_state(selected_questions, selected_topics, batch_size, quiz_mode, warning)

        return redirect(url_for("quiz.quiz"))

    return render_template(
        "index.html",
        topics=topics,
        selected_topics=[],
        selected_batch_size="10",
        selected_quiz_mode=QUIZ_MODE_STANDARD,
    )


@quiz_bp.route("/quiz", methods=["GET", "POST"])
def quiz():
    _clear_stale_quiz_state()
    questions = load_questions()
    question_ids = _get_question_ids()
    notice = session.pop("quiz_notice", None)

    if not question_ids:
        return redirect(url_for("quiz.index"))

    questions = get_questions_by_ids(questions, question_ids)

    if len(questions) != len(question_ids):
        session.pop("question_ids", None)
        session.pop("questions", None)
        session.pop("option_orders", None)
        return redirect(url_for("quiz.index"))

    option_orders = _get_option_orders()
    questions = _questions_with_display_options(questions, option_orders)

    if request.method == "POST":
        answers = {}

        for question in questions:
            question_id = get_question_id(question)
            selected = request.form.get(f"pregunta_{question_id}")
            answers[question_id] = _parse_selected_option(question, selected)

        corrected_questions = []

        for question in questions:
            question_id = get_question_id(question)
            user_answer = answers.get(question_id)

            corrected_questions.append(
                {
                    **question,
                    "respuesta_usuario": user_answer,
                    "es_correcta": _is_correct_option(question, user_answer),
                }
            )

        score = sum(q["es_correcta"] for q in corrected_questions)
        total = len(corrected_questions)
        save_attempts(corrected_questions)

        return render_template(
            "resultados.html",
            questions=corrected_questions,
            score=score,
            total=total,
        )

    return render_template("quiz.html", questions=questions, notice=notice)


@quiz_bp.route("/reiniciar")
def reiniciar():
    session.clear()
    return redirect(url_for("quiz.index"))


@quiz_bp.route("/otra-mas")
def otra_mas():
    _clear_stale_quiz_state()
    questions = load_questions()

    selected_topics = session.get("selected_topics", [])
    batch_size = int(session.get("batch_size", 10))
    quiz_mode = session.get("quiz_mode", QUIZ_MODE_STANDARD)

    if not selected_topics:
        return redirect(url_for("quiz.index"))

    selected_questions = select_quiz_questions(
        questions,
        selected_topics,
        batch_size,
        quiz_mode,
    )

    if not selected_questions:
        return redirect(url_for("quiz.index"))

    _store_quiz_state(selected_questions, selected_topics, batch_size, quiz_mode, None)

    return redirect(url_for("quiz.quiz"))
