from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .question_ids import option_id_for


REQUIRED_COLUMNS = {
    "question_id",
    "enunciado",
    "respuesta_correcta",
    "opcion_falsa_1",
    "opcion_falsa_2",
    "opcion_falsa_3",
    "explicacion",
    "tema",
    "teoria",
}


@dataclass(frozen=True)
class AnswerOption:
    text: str
    is_correct: bool


@dataclass(frozen=True)
class Question:
    question_id: str
    csv_id: int
    enunciado: str
    options: tuple[AnswerOption, AnswerOption, AnswerOption, AnswerOption]
    explicacion: str
    tema: str
    teoria: int

    @property
    def respuesta_correcta(self) -> int:
        for index, option in enumerate(self.options, start=1):
            if option.is_correct:
                return index

        raise ValueError("La pregunta no tiene respuesta correcta")


def validate_csv_header(fieldnames: list[str]) -> None:
    missing_columns = REQUIRED_COLUMNS - set(fieldnames)
    if missing_columns:
        raise ValueError(
            "Faltan columnas en el CSV de preguntas: "
            + ", ".join(sorted(missing_columns))
        )


def question_from_csv_row(
    row: dict[str, Any],
    csv_id: int,
    teoria: int,
) -> Question:
    correct_option = AnswerOption(
        text=str(row.get("respuesta_correcta", "")).strip(),
        is_correct=True,
    )
    false_options = tuple(
        AnswerOption(
            text=str(row.get(f"opcion_falsa_{index}", "")).strip(),
            is_correct=False,
        )
        for index in range(1, 4)
    )

    return _build_question(row, csv_id, teoria, (correct_option, *false_options))


def question_to_app_dict(question: Question) -> dict[str, Any]:
    return {
        "question_id": question.question_id,
        "csv_id": question.csv_id,
        "enunciado": question.enunciado,
        "respuesta_correcta": question.respuesta_correcta,
        "explicacion": question.explicacion,
        "tema": question.tema,
        "teoria": question.teoria,
        "options": [
            {
                "option_id": option_id_for(question.question_id, index),
                "text": option.text,
                "is_correct": option.is_correct,
            }
            for index, option in enumerate(question.options, start=1)
        ],
    }


def _build_question(
    row: dict[str, Any],
    csv_id: int,
    teoria: int,
    options: tuple[AnswerOption, ...],
) -> Question:
    question = Question(
        question_id=_get_question_id(row, csv_id),
        csv_id=csv_id,
        enunciado=str(row.get("enunciado", "")).strip(),
        options=_validate_options(options),
        explicacion=str(row.get("explicacion", "")).strip(),
        tema=str(row.get("tema", "")).strip(),
        teoria=teoria,
    )

    if sum(option.is_correct for option in question.options) != 1:
        raise ValueError("Cada pregunta debe tener exactamente una respuesta correcta")

    return question


def _get_question_id(row: dict[str, Any], csv_id: int) -> str:
    question_id = str(row.get("question_id", "")).strip()
    if question_id:
        return question_id
    return str(csv_id)


def _validate_options(
    options: tuple[AnswerOption, ...],
) -> tuple[AnswerOption, AnswerOption, AnswerOption, AnswerOption]:
    if len(options) != 4:
        raise ValueError("Cada pregunta debe tener 4 opciones")

    option_texts = []
    for option in options:
        if not option.text:
            raise ValueError("Las opciones no deben estar vacias")
        option_texts.append(option.text.strip())

    if len(set(option_texts)) != len(option_texts):
        raise ValueError("Hay opciones duplicadas dentro de la misma pregunta")

    return (options[0], options[1], options[2], options[3])
