from __future__ import annotations

import csv
import re
from typing import Any

from .config import CSV_PATH


REQUIRED_COLUMNS = {
    "enunciado",
    "opcion_1",
    "opcion_2",
    "opcion_3",
    "opcion_4",
    "respuesta_correcta",
    "explicacion",
    "tema",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def load_questions() -> list[dict[str, Any]]:
    """
    Carga y valida las preguntas desde preguntas.csv.

    El CSV debe tener las columnas:
    enunciado, opcion_1, opcion_2, opcion_3, opcion_4,
    respuesta_correcta, explicacion, tema
    """
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No se encontro el archivo {CSV_PATH}")

    questions = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("El CSV esta vacio o no tiene cabecera.")

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
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


def get_topics(questions: list[dict[str, Any]]) -> list[str]:
    """Devuelve los temas disponibles ordenados alfabeticamente."""
    return sorted({question["tema"] for question in questions})


def get_questions_by_topic_from_csv() -> dict[str, list[dict[str, Any]]]:
    """Lee preguntas.csv y agrupa las preguntas validas por tema."""
    questions_by_topic: dict[str, list[dict[str, Any]]] = {}

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No se encontro el archivo {CSV_PATH}")

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("El CSV esta vacio o no tiene cabecera.")

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
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
