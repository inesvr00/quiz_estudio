from __future__ import annotations

import pytest

from quiz_estudio import csv_repository
from quiz_estudio.csv_repository import normalize_text
from quiz_estudio.question_model import question_from_csv_row, question_to_app_dict


HEADER = (
    "question_id,enunciado,respuesta_correcta,opcion_falsa_1,opcion_falsa_2,"
    "opcion_falsa_3,explicacion,tema,teoria\n"
)


def test_normalize_text_collapses_whitespace_and_lowercases() -> None:
    assert normalize_text("  Hola\tMundo\nNuevo  ") == "hola mundo nuevo"


def test_question_row_is_converted_to_common_model() -> None:
    row = {
        "question_id": "q_000008",
        "enunciado": "Capital de Francia",
        "respuesta_correcta": "Paris",
        "opcion_falsa_1": "Roma",
        "opcion_falsa_2": "Berlin",
        "opcion_falsa_3": "Lisboa",
        "explicacion": "Paris es la capital de Francia.",
        "tema": "Geografia",
        "teoria": "0",
    }

    question = question_from_csv_row(row, csv_id=8, teoria=0)

    assert question.question_id == "q_000008"
    assert question.options[0].text == "Paris"
    assert [option.is_correct for option in question.options] == [
        True,
        False,
        False,
        False,
    ]


def test_common_model_can_be_projected_to_app_shape() -> None:
    row = {
        "question_id": "q_000007",
        "enunciado": "Capital de Francia",
        "respuesta_correcta": "Paris",
        "opcion_falsa_1": "Roma",
        "opcion_falsa_2": "Berlin",
        "opcion_falsa_3": "Lisboa",
        "explicacion": "Paris es la capital de Francia.",
        "tema": "Geografia",
        "teoria": "0",
    }

    app_question = question_to_app_dict(question_from_csv_row(row, csv_id=7, teoria=0))

    assert app_question["respuesta_correcta"] == 1
    assert app_question["options"][0] == {
        "text": "Paris",
        "is_correct": True,
        "option_id": "q_000007:option_1",
    }


def test_question_adapter_detects_duplicate_options() -> None:
    row = {
        "question_id": "q_000007",
        "enunciado": "Capital de Francia",
        "respuesta_correcta": "Paris",
        "opcion_falsa_1": "Paris",
        "opcion_falsa_2": "Berlin",
        "opcion_falsa_3": "Lisboa",
        "explicacion": "Paris es la capital de Francia.",
        "tema": "Geografia",
        "teoria": "0",
    }

    with pytest.raises(ValueError, match="duplicadas"):
        question_from_csv_row(row, csv_id=7, teoria=0)


def test_question_adapter_duplicate_detection_is_case_sensitive() -> None:
    row = {
        "question_id": "q_000007",
        "enunciado": "Relacion entre variables",
        "respuesta_correcta": "d = 3D",
        "opcion_falsa_1": "D = 3d",
        "opcion_falsa_2": "d = 2D",
        "opcion_falsa_3": "D = 2d",
        "explicacion": "La capitalizacion cambia el significado.",
        "tema": "Fisica",
        "teoria": "0",
    }

    question = question_from_csv_row(row, csv_id=7, teoria=0)

    assert [option.text for option in question.options] == [
        "d = 3D",
        "D = 3d",
        "d = 2D",
        "D = 2d",
    ]


def test_question_adapter_detects_duplicate_options_ignoring_outer_spaces() -> None:
    row = {
        "question_id": "q_000007",
        "enunciado": "Relacion entre variables",
        "respuesta_correcta": "d = 3D",
        "opcion_falsa_1": "  d = 3D  ",
        "opcion_falsa_2": "d = 2D",
        "opcion_falsa_3": "D = 2d",
        "explicacion": "Los espacios exteriores no cuentan.",
        "tema": "Fisica",
        "teoria": "0",
    }

    with pytest.raises(ValueError, match="duplicadas"):
        question_from_csv_row(row, csv_id=7, teoria=0)


def test_load_questions_reads_current_csv_format(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        HEADER
        + "q_000001,Capital de Francia,Paris,Roma,Berlin,Lisboa,"
        "Paris es la capital,Geografia,0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("quiz_estudio.question_repository.QUESTIONS_CSV_PATH", csv_path)

    questions = csv_repository.load_questions()

    assert len(questions) == 1
    assert questions[0]["respuesta_correcta"] == 1
    assert questions[0]["options"][0] == {
        "text": "Paris",
        "is_correct": True,
        "option_id": "q_000001:option_1",
    }
    assert [option["is_correct"] for option in questions[0]["options"][1:]] == [
        False,
        False,
        False,
    ]


def test_load_questions_keeps_false_options_from_current_csv(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        HEADER
        + "q_000001,Valor de μ²,μ²,π³,x⁻¹,10¹,Explicacion,Fisica,0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("quiz_estudio.question_repository.QUESTIONS_CSV_PATH", csv_path)

    questions = csv_repository.load_questions()

    assert [option["text"] for option in questions[0]["options"][1:]] == [
        "π³",
        "x⁻¹",
        "10¹",
    ]


def test_load_questions_logs_invalid_rows_without_breaking(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        HEADER
        + "q_000001,Valida,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n"
        + "q_000002,Invalida,Paris,Paris,Berlin,Lisboa,Explicacion,Geografia,0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("quiz_estudio.question_repository.QUESTIONS_CSV_PATH", csv_path)

    with caplog.at_level("WARNING", logger="quiz_estudio.question_repository"):
        questions = csv_repository.load_questions()

    assert len(questions) == 1
    assert "Pregunta descartada al cargar CSV en fila 3" in caplog.text


def test_normalize_text_removes_quotes_punctuation_and_accents() -> None:
    assert normalize_text('"Cual es la opcion correcta?"') == "cual es la opcion correcta"
