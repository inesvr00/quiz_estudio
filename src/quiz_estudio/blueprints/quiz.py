from __future__ import annotations

import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..csv_repository import get_question_id, get_topics, load_questions
from ..services.quiz_correction_service import (
    build_corrected_questions,
    build_option_orders,
    get_attempt_questions,
    is_correct_option,
    parse_selected_option,
)
from ..services.quiz_form_service import parse_batch_size, parse_quiz_mode
from ..services.quiz_service import (
    QUIZ_MODE_PRACTICAL,
    QUIZ_MODE_STANDARD,
    QUIZ_MODE_THEORY,
    select_quiz_questions,
)
from ..services.quiz_session_service import (
    clear_stale_quiz_state,
    get_attempt_question_ids,
    get_quiz_attempt,
    get_quiz_attempts,
    get_quiz_results,
    store_quiz_attempt,
    store_quiz_result,
)
from ..services.stats_service import save_attempts


quiz_bp = Blueprint("quiz", __name__)
logger = logging.getLogger(__name__)


ATTEMPT_MISSING_ERROR = (
    "No se ha encontrado el intento original del quiz. "
    "Vuelve a iniciar el test para corregirlo con sus preguntas exactas."
)
ATTEMPT_MISMATCH_ERROR = (
    "Las preguntas enviadas no coinciden con el intento original. "
    "No se ha corregido el quiz."
)
RESULT_MISSING_ERROR = (
    "No se ha encontrado el resultado de ese intento. "
    "Vuelve a iniciar el test si quieres corregirlo de nuevo."
)


def _render_attempt_error(message: str, status_code: int = 400):
    questions = load_questions()
    topics = get_topics(questions)

    return (
        render_template(
            "index.html",
            topics=topics,
            selected_topics=[],
            selected_batch_size="10",
            selected_quiz_mode=QUIZ_MODE_STANDARD,
            error=message,
        ),
        status_code,
    )


@quiz_bp.route("/", methods=["GET", "POST"])
def index():
    clear_stale_quiz_state(session)
    questions = load_questions()
    topics = get_topics(questions)

    if request.method == "POST":
        selected_topics = request.form.getlist("temas")
        batch_size, warning = parse_batch_size(request.form)
        quiz_mode = parse_quiz_mode(request.form)

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

        question_ids = [get_question_id(question) for question in selected_questions]
        attempt_id = store_quiz_attempt(
            session,
            question_ids,
            build_option_orders(selected_questions),
            selected_topics,
            batch_size,
            quiz_mode,
            warning,
        )

        return redirect(url_for("quiz.quiz", attempt_id=attempt_id))

    return render_template(
        "index.html",
        topics=topics,
        selected_topics=[],
        selected_batch_size="10",
        selected_quiz_mode=QUIZ_MODE_STANDARD,
    )


@quiz_bp.route("/quiz", methods=["GET", "POST"])
def quiz():
    clear_stale_quiz_state(session)
    all_questions = load_questions()
    notice = session.pop("quiz_notice", None)

    if request.method == "POST":
        attempt_id = (request.form.get("attempt_id") or "").strip()
        attempt = get_quiz_attempt(session, attempt_id)

        if attempt is None:
            logger.warning(
                "Quiz submit without original attempt: attempt_id=%s form_keys=%s",
                attempt_id,
                list(request.form.keys()),
            )
            return _render_attempt_error(ATTEMPT_MISSING_ERROR)

        question_ids = get_attempt_question_ids(attempt)
        received_question_ids = [str(question_id) for question_id in request.form.getlist("question_id")]
        answer_keys = [key for key in request.form.keys() if key.startswith("pregunta_")]

        logger.info(
            "Quiz submit: attempt_id=%s attempt_question_ids=%s received_question_ids=%s answer_keys=%s",
            attempt_id,
            question_ids,
            received_question_ids,
            answer_keys,
        )

        if received_question_ids != question_ids:
            logger.warning(
                "Quiz submit question mismatch: attempt_id=%s attempt_question_ids=%s received_question_ids=%s",
                attempt_id,
                question_ids,
                received_question_ids,
            )
            return _render_attempt_error(ATTEMPT_MISMATCH_ERROR)

        existing_result = get_quiz_results(session).get(attempt_id)
        if existing_result is not None:
            return redirect(url_for("quiz.resultados", attempt_id=attempt_id))

        questions = get_attempt_questions(all_questions, attempt)

        if questions is None:
            logger.warning(
                "Quiz submit with missing questions: attempt_id=%s question_ids=%s",
                attempt_id,
                question_ids,
            )
            return _render_attempt_error(ATTEMPT_MISSING_ERROR)

        answers = {}

        for question in questions:
            question_id = get_question_id(question)
            selected = request.form.get(f"pregunta_{question_id}")
            answers[question_id] = parse_selected_option(question, selected)

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

        score = sum(q["es_correcta"] for q in corrected_questions)
        total = len(corrected_questions)
        save_attempts(corrected_questions)
        store_quiz_result(session, attempt_id, answers, score, total)

        return redirect(url_for("quiz.resultados", attempt_id=attempt_id))

    attempt_id = request.args.get("attempt_id") or session.get("active_attempt_id")
    attempt = get_quiz_attempt(session, str(attempt_id) if attempt_id else None)

    if attempt is None:
        return redirect(url_for("quiz.index"))

    questions = get_attempt_questions(all_questions, attempt)

    if questions is None:
        session.pop("questions", None)
        attempts = get_quiz_attempts(session)
        if attempt_id:
            attempts.pop(str(attempt_id), None)
        session["quiz_attempts"] = attempts
        session.pop("active_attempt_id", None)
        return redirect(url_for("quiz.index"))

    return render_template("quiz.html", questions=questions, notice=notice, attempt_id=attempt_id)


@quiz_bp.route("/resultados/<attempt_id>", methods=["GET"])
def resultados(attempt_id: str):
    clear_stale_quiz_state(session)
    attempt = get_quiz_attempt(session, attempt_id)
    result = get_quiz_results(session).get(attempt_id)

    if attempt is None or result is None:
        return _render_attempt_error(RESULT_MISSING_ERROR, status_code=404)

    raw_answers = result.get("answers", {})
    if not isinstance(raw_answers, dict):
        return _render_attempt_error(RESULT_MISSING_ERROR, status_code=404)

    answers = {
        str(question_id): (None if selected is None else str(selected))
        for question_id, selected in raw_answers.items()
    }
    corrected_questions = build_corrected_questions(load_questions(), attempt, answers)

    if corrected_questions is None:
        return _render_attempt_error(RESULT_MISSING_ERROR, status_code=404)

    return render_template(
        "resultados.html",
        questions=corrected_questions,
        score=int(result.get("score", 0)),
        total=int(result.get("total", len(corrected_questions))),
    )


@quiz_bp.route("/reiniciar")
def reiniciar():
    session.clear()
    return redirect(url_for("quiz.index"))


@quiz_bp.route("/otra-mas")
def otra_mas():
    clear_stale_quiz_state(session)
    questions = load_questions()

    attempt_id = session.get("active_attempt_id")
    attempt = get_quiz_attempt(session, str(attempt_id) if attempt_id else None)

    if attempt is None:
        return redirect(url_for("quiz.index"))

    raw_selected_topics = attempt.get("selected_topics", [])
    selected_topics = [str(topic) for topic in raw_selected_topics] if isinstance(raw_selected_topics, list) else []

    try:
        batch_size = int(attempt.get("batch_size", 10))
    except (TypeError, ValueError):
        batch_size = 10

    quiz_mode = str(attempt.get("mode", QUIZ_MODE_STANDARD))
    if quiz_mode not in {QUIZ_MODE_STANDARD, QUIZ_MODE_THEORY, QUIZ_MODE_PRACTICAL}:
        quiz_mode = QUIZ_MODE_STANDARD

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

    question_ids = [get_question_id(question) for question in selected_questions]
    attempt_id = store_quiz_attempt(
        session,
        question_ids,
        build_option_orders(selected_questions),
        selected_topics,
        batch_size,
        quiz_mode,
        None,
    )

    return redirect(url_for("quiz.quiz", attempt_id=attempt_id))
