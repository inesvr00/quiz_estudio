from __future__ import annotations

import random

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..csv_repository import get_topics, load_questions
from ..services.quiz_attempt_service import (
    clear_missing_attempt_notice,
    clear_stale_quiz_state,
    copy_attempt_settings_to_legacy_state,
    create_attempt,
    get_attempt,
    get_attempt_id_from_request,
    get_attempt_option_orders,
    get_attempt_question_ids,
    get_attempt_questions,
    mark_stats_saved,
    set_missing_attempt_notice,
    stats_were_saved,
    store_answers,
    validate_submitted_question_ids,
)
from ..services.quiz_correction_service import (
    correct_questions,
    parse_answers,
    questions_with_display_options,
    score_questions,
)
from ..services.quiz_form_service import parse_batch_size, parse_quiz_mode
from ..services.quiz_service import QUIZ_MODE_STANDARD, select_quiz_questions
from ..services.stats_service import save_attempts


quiz_bp = Blueprint("quiz", __name__)


@quiz_bp.route("/", methods=["GET", "POST"])
def index():
    clear_stale_quiz_state(session)
    questions = load_questions()
    topics = get_topics(questions)
    error = clear_missing_attempt_notice(session)

    if request.method == "POST":
        selected_topics = request.form.getlist("temas") or topics
        batch_size, warning = parse_batch_size(request.form)
        quiz_mode = parse_quiz_mode(request.form)

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

        attempt_id = create_attempt(
            session,
            selected_questions,
            selected_topics,
            batch_size,
            quiz_mode,
            warning,
            random.shuffle,
        )

        return redirect(url_for("quiz.quiz", attempt_id=attempt_id))

    return render_template(
        "index.html",
        topics=topics,
        selected_topics=[],
        selected_batch_size="10",
        selected_quiz_mode=QUIZ_MODE_STANDARD,
        error=error,
    )


@quiz_bp.route("/quiz", methods=["GET", "POST"])
def quiz():
    clear_stale_quiz_state(session)
    attempt_id = get_attempt_id_from_request(request.args, request.form)
    attempt = get_attempt(session, attempt_id)

    if attempt is None:
        set_missing_attempt_notice(
            session,
            "No se encontro el intento original del quiz. Inicia un quiz nuevo.",
        )
        return redirect(url_for("quiz.index"))

    questions = load_questions()
    question_ids = get_attempt_question_ids(attempt)
    attempt_questions = get_attempt_questions(questions, attempt)
    notice = session.pop("quiz_notice", None)

    if len(attempt_questions) != len(question_ids):
        set_missing_attempt_notice(
            session,
            "No se pudieron recuperar todas las preguntas del intento original.",
        )
        return redirect(url_for("quiz.index"))

    display_questions = questions_with_display_options(
        attempt_questions,
        get_attempt_option_orders(attempt),
    )
    copy_attempt_settings_to_legacy_state(session, attempt)

    if request.method == "POST":
        if not validate_submitted_question_ids(attempt, request.form.getlist("question_id")):
            set_missing_attempt_notice(
                session,
                "Las preguntas recibidas no coinciden con el intento original.",
            )
            return redirect(url_for("quiz.index"))

        answers = parse_answers(request.form, display_questions)
        store_answers(session, attempt, answers)
        corrected_questions = correct_questions(display_questions, answers)

        if not stats_were_saved(attempt):
            save_attempts(corrected_questions)
            mark_stats_saved(session, attempt)

        return redirect(url_for("quiz.quiz", attempt_id=attempt["attempt_id"], results=1))

    if request.args.get("results") == "1":
        answers = attempt.get("answers", {})
        if not isinstance(answers, dict):
            answers = {}
        corrected_questions = correct_questions(display_questions, answers)
        score, total = score_questions(corrected_questions)
        return render_template(
            "resultados.html",
            questions=corrected_questions,
            score=score,
            total=total,
        )

    return render_template(
        "quiz.html",
        questions=display_questions,
        attempt_id=attempt["attempt_id"],
        notice=notice,
    )


@quiz_bp.route("/reiniciar")
def reiniciar():
    session.clear()
    return redirect(url_for("quiz.index"))


@quiz_bp.route("/otra-mas")
def otra_mas():
    clear_stale_quiz_state(session)
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

    attempt_id = create_attempt(
        session,
        selected_questions,
        selected_topics,
        batch_size,
        quiz_mode,
        None,
        random.shuffle,
    )

    return redirect(url_for("quiz.quiz", attempt_id=attempt_id))
