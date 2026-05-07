from __future__ import annotations

import csv
import random
import re
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, redirect, render_template, request, session, url_for

from import_questions import append_questions, preview_questions_from_text


CSV_PATH = Path("preguntas.csv")
DB_PATH = Path("stats.db")
ALLOWED_BATCH_SIZES = {1, 10, 20}
FAILED_QUESTIONS_PER_PAGE = 50


app = Flask(__name__)
app.secret_key = "cambia-esta-clave-en-produccion"


def init_db() -> None:
    """Crea la base de datos de estadisticas si no existe."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS question_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                enunciado TEXT NOT NULL,
                tema TEXT NOT NULL,
                respuesta_correcta INTEGER NOT NULL,
                respuesta_usuario INTEGER NOT NULL,
                es_correcta INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def save_attempts(questions: list[dict[str, Any]]) -> None:
    attempts = [
        (
            question["csv_id"],
            question["enunciado"],
            question["tema"],
            question["respuesta_correcta"],
            question["respuesta_usuario"],
            int(question["es_correcta"]),
        )
        for question in questions
        if question["respuesta_usuario"] is not None
    ]

    if not attempts:
        return

    with sqlite3.connect(DB_PATH) as connection:
        connection.executemany(
            """
            INSERT INTO question_attempts (
                question_id,
                enunciado,
                tema,
                respuesta_correcta,
                respuesta_usuario,
                es_correcta
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            attempts,
        )


def get_seen_question_ids() -> set[int]:
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT question_id
            FROM question_attempts
            """
        ).fetchall()

    return {row["question_id"] for row in rows}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def weighted_sample_without_replacement(
    items: list[dict[str, Any]],
    weights: list[float],
    k: int,
) -> list[dict[str, Any]]:
    if len(items) != len(weights):
        raise ValueError("items y weights deben tener la misma longitud.")

    sample_size = min(k, len(items))
    remaining_items = list(items)
    remaining_weights = list(weights)
    selected_items = []

    for _ in range(sample_size):
        selected_index = random.choices(
            range(len(remaining_items)),
            weights=remaining_weights,
            k=1,
        )[0]
        selected_items.append(remaining_items.pop(selected_index))
        remaining_weights.pop(selected_index)

    return selected_items


def select_quiz_questions(
    questions: list[dict[str, Any]],
    selected_topics: list[str],
    batch_size: int,
) -> list[dict[str, Any]]:
    filtered_questions = [
        question
        for question in questions
        if question["tema"] in selected_topics
    ]

    if not filtered_questions:
        return []

    seen_question_ids = get_seen_question_ids()
    weights = [
        2.0 if question["csv_id"] not in seen_question_ids else 1.0
        for question in filtered_questions
    ]

    return weighted_sample_without_replacement(
        filtered_questions,
        weights,
        batch_size,
    )


def get_statistics() -> dict[str, Any]:
    questions_by_topic = get_questions_by_topic_from_csv()
    seen_enunciados_by_topic = get_seen_question_enunciados_by_topic()

    with get_db_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(es_correcta), 0) AS aciertos
            FROM question_attempts
            """
        ).fetchone()

        topics = connection.execute(
            """
            SELECT
                tema,
                COUNT(*) AS total,
                COALESCE(SUM(es_correcta), 0) AS aciertos
            FROM question_attempts
            GROUP BY tema
            ORDER BY tema
            """
        ).fetchall()

    topic_stats_by_name = {
        row["tema"]: {
            "total": row["total"],
            "aciertos": row["aciertos"],
            "fallos": row["total"] - row["aciertos"],
            "porcentaje": round((row["aciertos"] / row["total"]) * 100, 1),
        }
        for row in topics
    }
    all_topic_names = sorted(set(questions_by_topic) | set(topic_stats_by_name))

    total = totals["total"]
    aciertos = totals["aciertos"]
    fallos = total - aciertos

    return {
        "total": total,
        "aciertos": aciertos,
        "fallos": fallos,
        "porcentaje": round((aciertos / total) * 100, 1) if total else 0,
        "topics": [
            {
                "tema": tema,
                "preguntas_en_repositorio": len(questions_by_topic.get(tema, [])),
                "preguntas_respondidas_distintas": len(
                    {
                        normalize_text(question["enunciado"])
                        for question in questions_by_topic.get(tema, [])
                    }
                    & seen_enunciados_by_topic.get(tema, set())
                ),
                "preguntas_no_hechas": len(questions_by_topic.get(tema, []))
                - len(
                    {
                        normalize_text(question["enunciado"])
                        for question in questions_by_topic.get(tema, [])
                    }
                    & seen_enunciados_by_topic.get(tema, set())
                ),
                "total": topic_stats_by_name.get(tema, {}).get("total", 0),
                "aciertos": topic_stats_by_name.get(tema, {}).get("aciertos", 0),
                "fallos": topic_stats_by_name.get(tema, {}).get("fallos", 0),
                "porcentaje": topic_stats_by_name.get(tema, {}).get("porcentaje"),
            }
            for tema in all_topic_names
        ],
    }


def get_questions_by_topic_from_csv() -> dict[str, list[dict[str, Any]]]:
    """Lee preguntas.csv y agrupa las preguntas validas por tema."""
    questions_by_topic: dict[str, list[dict[str, Any]]] = {}

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No se encontro el archivo {CSV_PATH}")

    required_columns = {
        "enunciado",
        "opcion_1",
        "opcion_2",
        "opcion_3",
        "opcion_4",
        "respuesta_correcta",
        "explicacion",
        "tema",
    }

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("El CSV esta vacio o no tiene cabecera.")

        missing = required_columns - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Faltan columnas en el CSV: {', '.join(sorted(missing))}")

        for row in reader:
            enunciado = row.get("enunciado", "").strip()
            tema = row.get("tema", "").strip()
            respuesta_correcta = row.get("respuesta_correcta", "").strip()

            if not enunciado or not respuesta_correcta or not tema:
                continue

            try:
                respuesta_correcta_int = int(respuesta_correcta)
            except ValueError:
                continue

            if respuesta_correcta_int not in {1, 2, 3, 4}:
                continue

            question = {
                "enunciado": enunciado,
                "opcion_1": row.get("opcion_1", ""),
                "opcion_2": row.get("opcion_2", ""),
                "opcion_3": row.get("opcion_3", ""),
                "opcion_4": row.get("opcion_4", ""),
                "respuesta_correcta": respuesta_correcta_int,
                "explicacion": row.get("explicacion", ""),
                "tema": tema,
            }

            questions_by_topic.setdefault(tema, []).append(question)

    return questions_by_topic


def get_seen_question_enunciados_by_topic() -> dict[str, set[str]]:
    seen_by_topic: dict[str, set[str]] = {}

    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT tema, enunciado
            FROM question_attempts
            WHERE enunciado IS NOT NULL
            """
        ).fetchall()

    for row in rows:
        tema = row["tema"]
        enunciado = normalize_text(row["enunciado"])

        if not tema or not enunciado:
            continue

        seen_by_topic.setdefault(tema, set()).add(enunciado)

    return seen_by_topic


def get_unseen_questions_by_topic(tema: str) -> list[dict[str, Any]]:
    questions_by_topic = get_questions_by_topic_from_csv()
    seen_enunciados = get_seen_question_enunciados_by_topic().get(tema, set())

    return [
        question
        for question in questions_by_topic.get(tema, [])
        if normalize_text(question["enunciado"]) not in seen_enunciados
    ]


def get_attempt_topics() -> list[str]:
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT tema
            FROM question_attempts
            ORDER BY tema
            """
        ).fetchall()

    return [row["tema"] for row in rows]


def get_failed_questions(
    tema: str | None = None,
    orden: str = "porcentaje",
    page: int = 1,
) -> dict[str, Any]:
    where_clause = ""
    params = ()
    order_clause = (
        "fallos DESC, porcentaje_fallo DESC, total DESC"
        if orden == "fallos"
        else "porcentaje_fallo DESC, fallos DESC, total DESC"
    )

    if tema:
        where_clause = "WHERE tema = ?"
        params = (tema,)

    with get_db_connection() as connection:
        total_rows = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM (
                SELECT
                    COUNT(*) - COALESCE(SUM(es_correcta), 0) AS fallos
                FROM question_attempts
                {where_clause}
                GROUP BY question_id, enunciado, tema
                HAVING fallos > 0
            )
            """,
            params,
        ).fetchone()["total"]

        total_pages = max((total_rows + FAILED_QUESTIONS_PER_PAGE - 1) // FAILED_QUESTIONS_PER_PAGE, 1)
        page = min(page, total_pages)
        offset = (page - 1) * FAILED_QUESTIONS_PER_PAGE

        rows = connection.execute(
            f"""
            SELECT
                question_id,
                enunciado,
                tema,
                COUNT(*) AS total,
                COALESCE(SUM(es_correcta), 0) AS aciertos,
                COUNT(*) - COALESCE(SUM(es_correcta), 0) AS fallos,
                ((COUNT(*) - COALESCE(SUM(es_correcta), 0)) * 100.0 / COUNT(*)) AS porcentaje_fallo
            FROM question_attempts
            {where_clause}
            GROUP BY question_id, enunciado, tema
            HAVING fallos > 0
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
            """,
            (*params, FAILED_QUESTIONS_PER_PAGE, offset),
        ).fetchall()

    return {
        "questions": [
            {
                "question_id": row["question_id"],
                "enunciado": row["enunciado"],
                "tema": row["tema"],
                "total": row["total"],
                "aciertos": row["aciertos"],
                "fallos": row["fallos"],
                "porcentaje_fallo": round(row["porcentaje_fallo"], 1),
            }
            for row in rows
        ],
        "page": page,
        "total_pages": total_pages,
        "total_rows": total_rows,
    }


def load_questions() -> list[dict[str, Any]]:
    """
    Carga y valida las preguntas desde preguntas.csv.

    El CSV debe tener las columnas:
    enunciado, opcion_1, opcion_2, opcion_3, opcion_4,
    respuesta_correcta, explicacion, tema
    """
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No se encontró el archivo {CSV_PATH}")

    required_columns = {
        "enunciado",
        "opcion_1",
        "opcion_2",
        "opcion_3",
        "opcion_4",
        "respuesta_correcta",
        "explicacion",
        "tema",
    }

    questions = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("El CSV está vacío o no tiene cabecera.")

        missing = required_columns - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Faltan columnas en el CSV: {', '.join(sorted(missing))}")

        for index, row in enumerate(reader):
            if not row["enunciado"] or not row["respuesta_correcta"] or not row["tema"]:
                continue

            question = {
                "csv_id": index,
                "enunciado": row["enunciado"],
                "opcion_1": row["opcion_1"],
                "opcion_2": row["opcion_2"],
                "opcion_3": row["opcion_3"],
                "opcion_4": row["opcion_4"],
                "respuesta_correcta": int(row["respuesta_correcta"]),
                "explicacion": row["explicacion"],
                "tema": row["tema"],
            }

            questions.append(question)

    return questions


def get_question_counts_by_topic() -> dict[str, int]:
    """Cuenta cuantas preguntas existen en preguntas.csv por tema."""
    counts: dict[str, int] = {}

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No se encontrÃ³ el archivo {CSV_PATH}")

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("El CSV estÃ¡ vacÃ­o o no tiene cabecera.")

        if "tema" not in reader.fieldnames:
            raise ValueError("Falta la columna tema en el CSV.")

        for row in reader:
            tema = row.get("tema", "").strip()
            if not tema:
                continue

            counts[tema] = counts.get(tema, 0) + 1

    return counts


def get_topics(questions: list[dict[str, Any]]) -> list[str]:
    """Devuelve los temas disponibles ordenados alfabéticamente."""
    return sorted({question["tema"] for question in questions})


@app.route("/", methods=["GET", "POST"])
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

        return redirect(url_for("quiz"))

    return render_template("index.html", topics=topics)


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    questions: list[dict[str, Any]] = session.get("questions", [])

    if not questions:
        return redirect(url_for("index"))

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


@app.route("/reiniciar")
def reiniciar():
    session.clear()
    return redirect(url_for("index"))


@app.route("/estadisticas")
def estadisticas():
    return render_template("estadisticas.html", stats=get_statistics())


@app.route("/preguntas-no-hechas")
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


@app.route("/preguntas-falladas")
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


@app.route("/importar-preguntas", methods=["GET", "POST"])
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
                    else "No había preguntas válidas nuevas para importar."
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


@app.route("/otra-mas")
def otra_mas():
    questions = load_questions()

    selected_topics = session.get("selected_topics", [])
    batch_size = session.get("batch_size", 10)

    if not selected_topics:
        return redirect(url_for("index"))

    selected_questions = select_quiz_questions(
        questions,
        selected_topics,
        batch_size,
    )

    if not selected_questions:
        return redirect(url_for("index"))

    session["questions"] = selected_questions

    return redirect(url_for("quiz"))


init_db()


if __name__ == "__main__":
    app.run(debug=True)
