from __future__ import annotations

from quiz_estudio.services.question_parity_service import (
    compare_question_repositories,
    format_parity_report,
)


def make_question(
    question_id: str = "q_000001",
    enunciado: str = "Enunciado",
    explicacion: str = "Explicacion",
    tema: str = "Tema",
    teoria: int = 0,
    options: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    options = options or [
        option(question_id, 1, "Correcta", True),
        option(question_id, 2, "Falsa 1", False),
        option(question_id, 3, "Falsa 2", False),
        option(question_id, 4, "Falsa 3", False),
    ]
    return {
        "question_id": question_id,
        "enunciado": enunciado,
        "explicacion": explicacion,
        "tema": tema,
        "teoria": teoria,
        "options": options,
    }


def option(
    question_id: str,
    index: int,
    text: str,
    is_correct: bool,
) -> dict[str, object]:
    return {
        "option_id": f"{question_id}:option_{index}",
        "text": text,
        "is_correct": is_correct,
        "option_order": index,
    }


def kinds(report):
    return [difference.kind for difference in report.differences]


def test_parity_ok_returns_ok_report() -> None:
    question = make_question()

    report = compare_question_repositories([question], [question])

    assert report.is_ok
    assert "OK: CSV y Supabase estan sincronizados." in format_parity_report(report)


def test_question_missing_in_supabase_is_detected() -> None:
    report = compare_question_repositories([make_question()], [])

    assert kinds(report) == ["missing_question_in_supabase"]


def test_extra_question_in_supabase_is_detected() -> None:
    report = compare_question_repositories([], [make_question()])

    assert kinds(report) == ["extra_question_in_supabase"]


def test_changed_enunciado_is_detected() -> None:
    report = compare_question_repositories(
        [make_question(enunciado="CSV")],
        [make_question(enunciado="Supabase")],
    )

    assert kinds(report) == ["changed_question_field"]
    assert "enunciado" in report.differences[0].detail


def test_changed_explanation_is_detected() -> None:
    report = compare_question_repositories(
        [make_question(explicacion="CSV")],
        [make_question(explicacion="Supabase")],
    )

    assert kinds(report) == ["changed_question_field"]
    assert "explicacion" in report.differences[0].detail


def test_changed_topic_is_detected() -> None:
    report = compare_question_repositories(
        [make_question(tema="CSV")],
        [make_question(tema="Supabase")],
    )

    assert kinds(report) == ["changed_question_field"]
    assert "tema" in report.differences[0].detail


def test_changed_theory_flag_is_detected() -> None:
    report = compare_question_repositories(
        [make_question(teoria=0)],
        [make_question(teoria=1)],
    )

    assert kinds(report) == ["changed_question_field"]
    assert "teoria" in report.differences[0].detail


def test_missing_option_is_detected() -> None:
    report = compare_question_repositories(
        [make_question()],
        [make_question(options=[option("q_000001", 1, "Correcta", True)])],
    )

    assert "changed_option_count" in kinds(report)
    assert "missing_option_in_supabase" in kinds(report)


def test_extra_option_is_detected() -> None:
    report = compare_question_repositories(
        [make_question(options=[option("q_000001", 1, "Correcta", True)])],
        [make_question()],
    )

    assert "changed_option_count" in kinds(report)
    assert "extra_option_in_supabase" in kinds(report)


def test_changed_option_text_is_detected() -> None:
    report = compare_question_repositories(
        [make_question(options=[option("q_000001", 1, "CSV", True)])],
        [make_question(options=[option("q_000001", 1, "Supabase", True)])],
    )

    assert "changed_option_text" in kinds(report)


def test_changed_option_correct_flag_is_detected() -> None:
    report = compare_question_repositories(
        [make_question(options=[option("q_000001", 1, "Respuesta", True)])],
        [make_question(options=[option("q_000001", 1, "Respuesta", False)])],
    )

    assert "changed_option_is_correct" in kinds(report)


def test_differences_have_error_exit_code_semantics() -> None:
    report = compare_question_repositories([make_question()], [])
    exit_code = 0 if report.is_ok else 1

    assert exit_code == 1
