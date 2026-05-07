from __future__ import annotations

import csv

from flask import Blueprint, render_template, request

from ..services.import_service import append_questions, preview_questions_from_text


import_bp = Blueprint("import_questions", __name__)


@import_bp.route("/importar-preguntas", methods=["GET", "POST"])
def importar_preguntas():
    csv_text = ""
    preview = None
    error = None
    success = None

    if request.method == "POST":
        csv_text = request.form.get("csv_text", "")
        action = request.form.get("action", "validate")

        try:
            preview = preview_questions_from_text(csv_text)
        except (ValueError, FileNotFoundError, csv.Error) as exc:
            error = str(exc)
        else:
            if action == "confirm":
                valid_rows = preview["valid"]
                backup_path = append_questions(valid_rows)
                success = (
                    f"Se importaron {len(valid_rows)} preguntas."
                    if valid_rows
                    else "No habia preguntas validas nuevas para importar."
                )
                if backup_path:
                    success = f"{success} Backup creado: {backup_path}"

    return render_template(
        "importar_preguntas.html",
        csv_text=csv_text,
        preview=preview,
        error=error,
        success=success,
    )
