from __future__ import annotations

from flask import Blueprint, render_template, request

from ..services.stats_service import (
    get_attempt_topics,
    get_failed_questions,
    get_statistics,
    get_unseen_questions_by_topic,
)


stats_bp = Blueprint("stats", __name__)


@stats_bp.route("/estadisticas")
def estadisticas():
    return render_template("estadisticas.html", stats=get_statistics())


@stats_bp.route("/preguntas-no-hechas")
def preguntas_no_hechas():
    selected_tema = request.args.get("tema", "").strip()

    if not selected_tema:
        return render_template(
            "preguntas_no_hechas.html",
            error="Elige un tema desde la pagina de estadisticas para ver sus preguntas no hechas.",
            selected_tema="",
            questions=[],
            total=0,
        )

    questions = get_unseen_questions_by_topic(selected_tema)

    return render_template(
        "preguntas_no_hechas.html",
        error=None,
        selected_tema=selected_tema,
        questions=questions,
        total=len(questions),
    )


@stats_bp.route("/preguntas-falladas")
def preguntas_falladas():
    selected_tema = request.args.get("tema", "").strip()
    selected_orden = request.args.get("orden", "porcentaje").strip()

    if selected_orden not in {"porcentaje", "fallos"}:
        selected_orden = "porcentaje"

    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1

    if page < 1:
        page = 1

    failed_questions = get_failed_questions(
        selected_tema or None,
        selected_orden,
        page,
    )

    return render_template(
        "preguntas_falladas.html",
        questions=failed_questions["questions"],
        topics=get_attempt_topics(),
        selected_tema=selected_tema,
        selected_orden=selected_orden,
        page=failed_questions["page"],
        total_pages=failed_questions["total_pages"],
        total_rows=failed_questions["total_rows"],
    )
