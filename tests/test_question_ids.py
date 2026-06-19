from __future__ import annotations

from quiz_estudio.question_ids import (
    assign_missing_question_ids,
    next_question_id,
    validate_question_ids,
)


def test_validate_question_ids_detects_duplicate_id() -> None:
    issues = validate_question_ids(
        [
            {"question_id": "q_000001"},
            {"question_id": "q_000001"},
        ]
    )

    assert any("duplicado" in issue.detail for issue in issues)


def test_validate_question_ids_detects_empty_id() -> None:
    issues = validate_question_ids([{"question_id": ""}])

    assert issues[0].detail == "question_id esta vacio"


def test_assign_missing_question_ids_only_fills_missing_rows() -> None:
    rows = [
        {"question_id": "q_000010", "enunciado": "Existente"},
        {"question_id": "", "enunciado": "Nueva"},
    ]

    updated_rows, assigned_count = assign_missing_question_ids(rows)

    assert assigned_count == 1
    assert updated_rows[0]["question_id"] == "q_000010"
    assert updated_rows[1]["question_id"] == "q_000011"


def test_next_question_id_uses_highest_existing_id() -> None:
    assert next_question_id({"q_000001", "q_002661"}) == "q_002662"
