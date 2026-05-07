from __future__ import annotations

from typing import Any

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..config import ALLOWED_BATCH_SIZES
from ..csv_repository import get_topics, load_questions
from ..services.quiz_service import select_quiz_questions
from ..services.stats_service import save_attempts


quiz_bp = Blueprint("quiz", __name__)


@quiz_bp.route("/", methods=["GET", "POST"])
def index():
    questions = load_questions()
    topics = get_topics(questions)

    if request.method == "POST":
        selected_topics = request.form.getlist("temas")
        batch_size = int(request.form.get("batch_size", 10))

        if not selected_topics:
            selected_topics = topics

        if batch_size not in ALLOWED_BATCH_SIZES:
            batch_size = 10

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

        session["questions"] = selected_questions
        session["selected_topics"] = selected_topics
        session["batch_size"] = batch_size

        return redirect(url_for("quiz.quiz"))

    return render_template("index.html", topics=topics)


@quiz_bp.route("/quiz", methods=["GET", "POST"])
def quiz():
    questions: list[dict[str, Any]] = session.get("questions", [])

    if not questions:
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

    return render_template("quiz.html", questions=questions)


@quiz_bp.route("/reiniciar")
def reiniciar():
    session.clear()
    return redirect(url_for("quiz.index"))


@quiz_bp.route("/otra-mas")
def otra_mas():
    questions = load_questions()

    selected_topics = session.get("selected_topics", [])
    batch_size = session.get("batch_size", 10)

    if not selected_topics:
        return redirect(url_for("quiz.index"))

    selected_questions = select_quiz_questions(
        questions,
        selected_topics,
        batch_size,
    )

    if not selected_questions:
        return redirect(url_for("quiz.index"))

    session["questions"] = selected_questions

    return redirect(url_for("quiz.quiz"))
