from __future__ import annotations

from pathlib import Path

import pytest

from quiz_estudio.services import import_service


CSV_HEADER = (
    "enunciado,opcion_1,opcion_2,opcion_3,opcion_4,respuesta_correcta,explicacion,tema\n"
)


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text(CSV_HEADER + "\n".join(rows) + "\n", encoding="utf-8")


@pytest.fixture()
def isolated_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "preguntas.csv"
    backup_dir = tmp_path / "backups"
    _write_csv(
        csv_path,
        [
            "Capital de Francia,A,Paris,C,D,1,Explicacion,Geografia",
            "Que numero sigue al 2?,A,3,C,D,1,Explicacion,Matematicas",
            "La capital de Francia es Paris,A,Paris,C,D,1,Explicacion,Geografia",
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
        ["Capital de Francia"],
    )

    assert classification == "duplicate"
    assert match is not None
    assert match["score"] == 100.0


def test_classify_import_question_marks_similar_question_for_review() -> None:
    classification, match = import_service.classify_import_question(
        "La capital de Francia es Madrid",
        ["La capital de Francia es Paris"],
    )

    assert classification == "review"
    assert match is not None
    assert match["score"] >= 82.0


def test_classify_import_question_handles_sensitive_negation_with_caution() -> None:
    classification, match = import_service.classify_import_question(
        "Cual NO es la capital de Francia?",
        ["Cual es la capital de Francia?"],
    )

    assert classification == "review"
    assert match is not None
    assert "no" in match["new_sensitive_markers"]


def test_preview_questions_reports_review_rows(isolated_csv) -> None:
    preview = import_service.preview_questions_from_text(
        CSV_HEADER
        + "Cual NO es la capital de Francia?,A,Paris,C,D,1,Explicacion,Geografia\n"
        + "Pregunta totalmente distinta,A,B,C,D,1,Explicacion,General\n"
    )

    assert preview["total_read"] == 2
    assert len(preview["valid"]) == 1
    assert len(preview["duplicates"]) == 0
    assert len(preview["review"]) == 1
    assert preview["review"][0]["matched_question"]