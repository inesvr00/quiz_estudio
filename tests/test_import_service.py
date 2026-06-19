from __future__ import annotations

from pathlib import Path

import pytest

from quiz_estudio.services import import_service


NEW_HEADER = (
    "question_id,enunciado,respuesta_correcta,opcion_falsa_1,opcion_falsa_2,"
    "opcion_falsa_3,explicacion,tema,teoria\n"
)
NEW_HEADER_WITHOUT_ID = (
    "enunciado,respuesta_correcta,opcion_falsa_1,opcion_falsa_2,"
    "opcion_falsa_3,explicacion,tema,teoria\n"
)


def _write_main_csv(path: Path, rows: list[str]) -> None:
    path.write_text(NEW_HEADER + "\n".join(rows) + "\n", encoding="utf-8")


@pytest.fixture()
def isolated_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    backup_dir = tmp_path / "backups"
    _write_main_csv(
        csv_path,
        [
            "q_000001,Capital de Francia,Paris,A,C,D,Explicacion,Geografia,1",
            "q_000002,Que numero sigue al 2?,3,A,C,D,Explicacion,Matematicas,0",
            "q_000003,La capital de Francia es Paris,Paris,A,C,D,Explicacion,Geografia,1",
        ],
    )

    monkeypatch.setattr(import_service, "CSV_PATH", csv_path)
    monkeypatch.setattr(import_service, "BACKUP_DIR", backup_dir)
    return csv_path


def test_classify_import_question_detects_exact_duplicate() -> None:
    classification, match = import_service.classify_import_question(
        "Capital de Francia",
        ["Capital de Francia"],
    )

    assert classification == "duplicate"
    assert match is not None
    assert match["score"] == 100.0


def test_classify_import_question_ignores_format_differences() -> None:
    classification, match = import_service.classify_import_question(
        '  "Capital   de   Francia"  ',
        import_service.build_question_match_index(["Capital de Francia"]),
    )

    assert classification == "duplicate"
    assert match is not None
    assert match["score"] == 100.0


def test_find_best_question_match_works_with_pre_normalized_index() -> None:
    question_index = import_service.build_question_match_index(
        [
            "Capital de Francia",
            "La capital de Francia es Paris",
        ]
    )

    match = import_service.find_best_question_match(
        '  "Capital   de   Francia"  ',
        question_index,
        normalized_existing_questions=[
            entry["normalized"] for entry in question_index
        ],
    )

    assert match is not None
    assert match["question"] == "Capital de Francia"
    assert match["score"] == 100.0


def test_classify_import_question_returns_new_for_distinct_question() -> None:
    classification, match = import_service.classify_import_question(
        "Que color tiene el cielo en un dia despejado?",
        import_service.build_question_match_index(
            [
                "Capital de Francia",
                "La capital de Francia es Paris",
            ]
        ),
    )

    assert classification == "new"
    assert match is None


def test_classify_import_question_marks_similar_question_for_review() -> None:
    classification, match = import_service.classify_import_question(
        "La capital de Francia es Madrid",
        import_service.build_question_match_index(["La capital de Francia es Paris"]),
    )

    assert classification == "review"
    assert match is not None
    assert match["score"] >= 82.0


def test_classify_import_question_handles_sensitive_negation_with_caution() -> None:
    classification, match = import_service.classify_import_question(
        "Cual NO es la capital de Francia?",
        import_service.build_question_match_index(["Cual es la capital de Francia?"]),
    )

    assert classification == "review"
    assert match is not None
    assert "no" in match["new_sensitive_markers"]


@pytest.mark.parametrize("keyword", ["NO", "EXCEPTO", "incorrecta", "falsa"])
def test_sensitive_words_force_review(keyword: str) -> None:
    classification, match = import_service.classify_import_question(
        f"Cual {keyword} es la capital de Francia?",
        import_service.build_question_match_index(["Cual es la capital de Francia?"]),
    )

    assert classification == "review"
    assert match is not None


def test_preview_imports_valid_new_csv(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        NEW_HEADER
        + "q_000010,Pregunta totalmente distinta,Correcta,Falsa 1,Falsa 2,Falsa 3,Explicacion,General,0\n"
    )

    assert preview["total_read"] == 1
    assert len(preview["valid"]) == 1
    assert preview["valid"][0]["question_id"] == "q_000010"
    assert preview["valid"][0]["respuesta_correcta"] == "Correcta"
    assert preview["valid"][0]["opcion_falsa_1"] == "Falsa 1"
    assert preview["valid"][0]["teoria"] == "0"


def test_preview_rejects_csv_without_question_id_column(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        NEW_HEADER_WITHOUT_ID
        + "Pregunta sin id,Correcta,Falsa 1,Falsa 2,Falsa 3,Explicacion,General,0\n"
    )

    assert len(preview["valid"]) == 0
    assert "question_id" in "\n".join(preview["errors"][0]["errors"])


def test_preview_avoids_duplicate_question_id(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        NEW_HEADER
        + "q_000002,Pregunta con id repetido,Correcta,Falsa 1,Falsa 2,Falsa 3,Explicacion,General,0\n"
    )

    assert len(preview["valid"]) == 1
    assert preview["valid"][0]["question_id"] == "q_000004"


def test_preview_reports_invalid_question(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        NEW_HEADER
        + "q_000010,Pregunta invalida,Correcta,Correcta,Falsa 2,Falsa 3,Explicacion,General,0\n"
    )

    assert preview["total_read"] == 1
    assert len(preview["valid"]) == 0
    assert "duplicadas" in preview["errors"][0]["errors"][0]


def test_preview_preserves_unicode(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        NEW_HEADER
        + "q_000010,Valor de μ²,μ²,π³,x⁻¹,10¹,Explicacion,Fisica,0\n"
    )

    row = preview["valid"][0]
    assert row["enunciado"] == "Valor de μ²"
    assert row["respuesta_correcta"] == "μ²"
    assert row["opcion_falsa_1"] == "π³"


def test_append_questions_writes_new_format_columns(isolated_csv) -> None:
    rows = [
        {
            "row_number": 2,
            "question_id": "q_000004",
            "enunciado": "Pregunta nueva",
            "respuesta_correcta": "Correcta",
            "opcion_falsa_1": "Falsa 1",
            "opcion_falsa_2": "Falsa 2",
            "opcion_falsa_3": "Falsa 3",
            "explicacion": "Explicacion",
            "tema": "General",
            "teoria": "0",
        }
    ]

    import_service.append_questions(rows)
    header = isolated_csv.read_text(encoding="utf-8").splitlines()[0]

    assert header.split(",") == import_service.NEW_COLUMNS
    assert "q_000004,Pregunta nueva,Correcta,Falsa 1,Falsa 2,Falsa 3" in isolated_csv.read_text(
        encoding="utf-8"
    )


def test_preview_questions_reports_review_rows(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        NEW_HEADER
        + "q_000010,Cual NO es la capital de Francia?,Paris,A,C,D,Explicacion,Geografia,1\n"
        + "q_000011,Pregunta totalmente distinta,Correcta,Falsa 1,Falsa 2,Falsa 3,Explicacion,General,0\n"
    )

    assert preview["total_read"] == 2
    assert len(preview["valid"]) == 1
    assert preview["valid"][0]["teoria"] == "0"
    assert len(preview["duplicates"]) == 0
    assert len(preview["review"]) == 1
    assert preview["review"][0]["teoria"] == "1"
    assert preview["review"][0]["matched_question"]


def test_preview_rejects_rows_without_header(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        '"Sea una lente cuya potencia es 0,5 dioptrias...", "0,5 cm", "0,25 cm", "1 m", "2 m", "4", "explicacion...", "Optica", "0"\n'
    )

    assert preview["total_read"] == 1
    assert len(preview["valid"]) == 0
    assert preview["errors"]


def test_preview_reports_missing_header(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        "Pregunta incompleta,A,B,C,D,1,Explicacion,General\n"
    )

    assert preview["total_read"] == 1
    assert len(preview["valid"]) == 0
    assert "El CSV externo debe tener las columnas" in preview["errors"][0]["errors"][0]


def test_preview_builds_match_index_once(isolated_csv, monkeypatch) -> None:
    calls = {"count": 0}
    original_builder = import_service.build_question_match_index

    def wrapped_builder(existing_questions):
        calls["count"] += 1
        return original_builder(existing_questions)

    monkeypatch.setattr(import_service, "build_question_match_index", wrapped_builder)

    import_service.preview_questions_from_text(
        NEW_HEADER
        + "q_000010,Nueva pregunta 1,Correcta,Falsa 1,Falsa 2,Falsa 3,Explicacion,General,0\n"
        + "q_000011,Nueva pregunta 2,Correcta,Falsa 1,Falsa 2,Falsa 3,Explicacion,General,1\n"
    )

    assert calls["count"] == 1


def test_preview_questions_reports_invalid_teoria(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        NEW_HEADER
        + "q_000010,Pregunta con teoria invalida,Correcta,Falsa 1,Falsa 2,Falsa 3,Explicacion,General,2\n"
    )

    assert preview["total_read"] == 1
    assert len(preview["valid"]) == 0
    assert preview["errors"][0]["errors"] == ["Fila 2: teoria debe ser 0 o 1"]
