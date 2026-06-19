from __future__ import annotations

from quiz_estudio.question_audit import audit_questions_csv


HEADER = (
    "question_id,enunciado,respuesta_correcta,opcion_falsa_1,opcion_falsa_2,"
    "opcion_falsa_3,explicacion,tema,teoria\n"
)


def _audit(tmp_path, csv_text: str):
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    return audit_questions_csv(csv_path)


def test_audit_valid_csv_has_no_issues(tmp_path) -> None:
    report = _audit(
        tmp_path,
        HEADER
        + "q_000001,Capital de Francia,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n",
    )

    assert report.total_rows == 1
    assert report.valid_rows == 1
    assert report.invalid_rows == 0
    assert report.issues == []


def test_audit_detects_duplicate_options(tmp_path) -> None:
    report = _audit(
        tmp_path,
        HEADER
        + "q_000001,Capital de Francia,Paris,Paris,Berlin,Lisboa,Explicacion,Geografia,0\n",
    )

    assert report.invalid_rows == 1
    assert any(issue.problem_type == "duplicate_options" for issue in report.issues)


def test_audit_detects_empty_option(tmp_path) -> None:
    report = _audit(
        tmp_path,
        HEADER
        + "q_000001,Capital de Francia,Paris,,Berlin,Lisboa,Explicacion,Geografia,0\n",
    )

    assert report.invalid_rows == 1
    assert any(issue.problem_type == "empty_option" for issue in report.issues)


def test_audit_duplicate_detection_is_case_sensitive(tmp_path) -> None:
    report = _audit(
        tmp_path,
        HEADER
        + "q_000001,Relacion entre variables,d = 3D,D = 3d,Berlin,Lisboa,Explicacion,Fisica,0\n",
    )

    assert report.invalid_rows == 0
    assert report.issues == []


def test_audit_detects_duplicate_options_ignoring_outer_spaces(tmp_path) -> None:
    report = _audit(
        tmp_path,
        HEADER
        + "q_000001,Relacion entre variables,d = 3D,  d = 3D  ,Berlin,Lisboa,Explicacion,Fisica,0\n",
    )

    assert report.invalid_rows == 1
    assert any(issue.problem_type == "duplicate_options" for issue in report.issues)


def test_audit_detects_missing_required_columns(tmp_path) -> None:
    report = _audit(tmp_path, "enunciado,respuesta_correcta,tema\nCapital,Paris,Geografia\n")

    assert report.total_rows == 0
    assert report.valid_rows == 0
    assert report.invalid_rows == 1
    assert report.issues[0].problem_type == "missing_columns"
