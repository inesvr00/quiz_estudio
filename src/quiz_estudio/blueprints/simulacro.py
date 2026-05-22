from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..csv_repository import load_questions
from ..exam_config import DEFAULT_SIMULACRO_TOTAL_QUESTIONS
from ..services.simulacro_service import (
    build_corrected_questions,
    calculate_simulacro_summary,
    create_simulacro_id,
    generate_simulacro_plan,
    load_questions_by_ids,
    save_simulacro_attempts,
)
from ..exam_config import get_exam_topics
from quiz_estudio.db import get_attempt_repository


simulacro_bp = Blueprint("simulacro", __name__, url_prefix="/simulacro")


def _parse_total_questions(raw_total: str | None) -> int:
    try:
        total_questions = int(raw_total or DEFAULT_SIMULACRO_TOTAL_QUESTIONS)
    except ValueError:
        return DEFAULT_SIMULACRO_TOTAL_QUESTIONS

    return total_questions if total_questions > 0 else DEFAULT_SIMULACRO_TOTAL_QUESTIONS


def _load_simulacro_questions() -> list[dict[str, object]]:
    question_ids = session.get("simulacro_question_ids", [])
    if not question_ids:
        return []

    return load_questions_by_ids(question_ids)


@simulacro_bp.route("/", methods=["GET", "POST"])
def index():
    available_questions = load_questions()

    if request.method == "POST":
        total_questions = _parse_total_questions(request.form.get("total_questions"))
        plan = generate_simulacro_plan(available_questions, total_questions)

        if not plan["questions"]:
            return render_template(
                "simulacro_real.html",
                default_total=DEFAULT_SIMULACRO_TOTAL_QUESTIONS,
                available_total=len(available_questions),
                error="No hay preguntas suficientes para generar el simulacro.",
            )

        session["simulacro_question_ids"] = [question["csv_id"] for question in plan["questions"]]
        session["simulacro_requested_total"] = total_questions
        session["simulacro_warning"] = plan["warning"]

        return redirect(url_for("simulacro.quiz"))

    return render_template(
        "simulacro_real.html",
        default_total=DEFAULT_SIMULACRO_TOTAL_QUESTIONS,
        available_total=len(available_questions),
        error=None,
    )


@simulacro_bp.route("/quiz", methods=["GET", "POST"])
def quiz():
    questions = _load_simulacro_questions()
    if not questions:
        return redirect(url_for("simulacro.index"))

    warning = session.get("simulacro_warning")
    requested_total = int(session.get("simulacro_requested_total", len(questions)))

    if request.method == "POST":
        corrected_questions = build_corrected_questions(questions, request.form)
        summary = calculate_simulacro_summary(corrected_questions)
        simulacro_id = create_simulacro_id()
        save_simulacro_attempts(simulacro_id, corrected_questions)

        return render_template(
            "simulacro_resultados.html",
            questions=corrected_questions,
            summary=summary,
            requested_total=requested_total,
            warning=warning,
            simulacro_id=simulacro_id,
        )

    return render_template(
        "simulacro_quiz.html",
        questions=questions,
        requested_total=requested_total,
        warning=warning,
    )


@simulacro_bp.route("/reiniciar")
def reiniciar():
    session.pop("simulacro_question_ids", None)
    session.pop("simulacro_requested_total", None)
    session.pop("simulacro_warning", None)
    return redirect(url_for("simulacro.index"))


@simulacro_bp.route("/estadisticas")
def estadisticas():
    repo = get_attempt_repository()
    attempts = repo.get_all_exam_attempts()

    if not attempts:
        return render_template("simulacro_estadisticas.html", attempts=[], error="Todavía no has realizado ningún simulacro.")

    return render_template("simulacro_estadisticas.html", attempts=attempts, error=None)


@simulacro_bp.route("/estadisticas/<int:attempt_id>")
def estadisticas_detalle(attempt_id: int):
    repo = get_attempt_repository()
    attempts = repo.get_all_exam_attempts()
    attempt = next((a for a in attempts if a["id"] == attempt_id or a.get("id") == attempt_id), None)

    if not attempt:
        return redirect(url_for("simulacro.estadisticas"))

    saved_topics = repo.get_exam_attempt_topics(attempt_id)

    # Merge saved_topics with the full list of configured topics so that
    # the detail page shows every possible topic and a dash when the
    # topic did not appear in the simulacro.
    saved_by_topic = {row.get("topic") or row.get("tema") or row.get("topic") : row for row in saved_topics}

    merged_topics = []
    for tema in get_exam_topics():
        row = saved_by_topic.get(tema)
        if row:
            # Normalize keys to expected names in the template
            merged_topics.append(
                {
                    "topic": tema,
                    "total_questions": row.get("total_questions") or row.get("total") or 0,
                    "correct": row.get("correct") or row.get("acertadas") or 0,
                    "wrong": row.get("wrong") or row.get("falladas") or 0,
                    "unanswered": row.get("unanswered") or 0,
                    "accuracy_percentage": row.get("accuracy_percentage") if row.get("accuracy_percentage") is not None else (row.get("porcentaje") if row.get("porcentaje") is not None else None),
                }
            )
        else:
            merged_topics.append(
                {
                    "topic": tema,
                    "total_questions": 0,
                    "correct": 0,
                    "wrong": 0,
                    "unanswered": 0,
                    "accuracy_percentage": None,
                }
            )

    return render_template("simulacro_estadisticas_detalle.html", attempt=attempt, topics=merged_topics)
