from __future__ import annotations

from typing import Any

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..config import ALLOWED_BATCH_SIZES
from ..csv_repository import get_question_id, get_questions_by_ids, get_topics, load_questions
from ..services.quiz_service import select_quiz_questions
from ..services.stats_service import save_attempts


quiz_bp = Blueprint("quiz", __name__)


def _get_question_ids() -> list[int]:
    raw_question_ids = session.get("question_ids", [])

    try:
        return [int(question_id) for question_id in raw_question_ids]
    except (TypeError, ValueError):
        return []


def _store_quiz_state(
    selected_questions: list[dict[str, object]],
    selected_topics: list[str],
    batch_size: int,
    warning: str | None,
) -> None:
    session["question_ids"] = [get_question_id(question) for question in selected_questions]
    session["selected_topics"] = selected_topics
    session["batch_size"] = batch_size
    session.pop("questions", None)

    if warning:
        session["quiz_notice"] = warning
    else:
        session.pop("quiz_notice", None)


def _clear_legacy_quiz_state() -> None:
    session.pop("questions", None)


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


@quiz_bp.route("/", methods=["GET", "POST"])
def index():
    _clear_legacy_quiz_state()
    questions = load_questions()
    topics = get_topics(questions)

    if request.method == "POST":
        selected_topics = request.form.getlist("temas")
        batch_size, warning = _parse_batch_size(request.form)

        if not selected_topics:
            selected_topics = topics

        selected_questions = select_quiz_questions(
            questions,
            selected_topics,
            batch_size,
        )

        if not selected_questions:
            return render_template(
                "index.html",
                topics=topics,
                error="No hay preguntas para los temas seleccionados.",
            )

        if batch_size > len(selected_questions):
            warning = (
                f"Solo hay {len(selected_questions)} preguntas disponibles para los temas seleccionados. "
                f"Se usará ese máximo."
            )

        _store_quiz_state(selected_questions, selected_topics, batch_size, warning)

        return redirect(url_for("quiz.quiz"))

    return render_template("index.html", topics=topics)


@quiz_bp.route("/quiz", methods=["GET", "POST"])
def quiz():
    _clear_legacy_quiz_state()
    questions = load_questions()
    question_ids = _get_question_ids()
    notice = session.pop("quiz_notice", None)

    if not question_ids:
        return redirect(url_for("quiz.index"))

    questions = get_questions_by_ids(questions, question_ids)

    if len(questions) != len(question_ids):
        session.pop("question_ids", None)
        session.pop("questions", None)
        return redirect(url_for("quiz.index"))

    if request.method == "POST":
        answers = {}

        for question in questions:
            csv_id = str(question["csv_id"])
            selected = request.form.get(f"pregunta_{csv_id}")
            answers[csv_id] = int(selected) if selected else None

        corrected_questions = []

        for question in questions:
            csv_id = str(question["csv_id"])
            user_answer = answers.get(csv_id)
            correct_answer = int(question["respuesta_correcta"])

            corrected_questions.append(
                {
                    **question,
                    "respuesta_usuario": user_answer,
                    "es_correcta": user_answer == correct_answer,
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
    _clear_legacy_quiz_state()
    questions = load_questions()

    selected_topics = session.get("selected_topics", [])
    batch_size = int(session.get("batch_size", 10))

    if not selected_topics:
        return redirect(url_for("quiz.index"))

    selected_questions = select_quiz_questions(
        questions,
        selected_topics,
        batch_size,
    )

    if not selected_questions:
        return redirect(url_for("quiz.index"))

    _store_quiz_state(selected_questions, selected_topics, batch_size, None)

    return redirect(url_for("quiz.quiz"))
