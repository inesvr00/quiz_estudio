from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


QUESTION_ID_PATTERN = re.compile(r"q_\d{6}")


@dataclass(frozen=True)
class QuestionIdIssue:
    row_number: int
    question_id: str
    detail: str


def is_valid_question_id(question_id: str) -> bool:
    return bool(QUESTION_ID_PATTERN.fullmatch(question_id.strip()))


def question_id_number(question_id: str) -> int:
    raw_question_id = question_id.strip()
    if not is_valid_question_id(raw_question_id):
        raise ValueError(f"question_id invalido: {question_id}")

    return int(raw_question_id.removeprefix("q_"))


def question_id_to_storage_id(question_id: object, fallback: int) -> int:
    raw_question_id = str(question_id).strip()
    if is_valid_question_id(raw_question_id):
        return question_id_number(raw_question_id)

    try:
        return int(raw_question_id)
    except ValueError:
        return fallback


def next_question_id(used_question_ids: set[str]) -> str:
    next_number = max(
        (
            question_id_number(question_id)
            for question_id in used_question_ids
            if is_valid_question_id(question_id)
        ),
        default=0,
    ) + 1

    while True:
        candidate = f"q_{next_number:06d}"
        if candidate not in used_question_ids:
            return candidate
        next_number += 1


def validate_question_ids(rows: list[dict[str, str]]) -> list[QuestionIdIssue]:
    issues: list[QuestionIdIssue] = []
    seen: dict[str, int] = {}

    for index, row in enumerate(rows, start=2):
        question_id = str(row.get("question_id", "")).strip()
        if not question_id:
            issues.append(
                QuestionIdIssue(index, question_id, "question_id esta vacio")
            )
            continue

        if not is_valid_question_id(question_id):
            issues.append(
                QuestionIdIssue(
                    index,
                    question_id,
                    "question_id debe tener formato q_000001",
                )
            )

        if question_id in seen:
            issues.append(
                QuestionIdIssue(
                    index,
                    question_id,
                    f"question_id duplicado; ya aparece en la fila {seen[question_id]}",
                )
            )
        else:
            seen[question_id] = index

    return issues


def assign_missing_question_ids(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    used_question_ids = {
        str(row.get("question_id", "")).strip()
        for row in rows
        if str(row.get("question_id", "")).strip()
    }
    updated_rows = []
    assigned_count = 0

    for row in rows:
        updated_row = dict(row)
        if not str(updated_row.get("question_id", "")).strip():
            generated_question_id = next_question_id(used_question_ids)
            updated_row["question_id"] = generated_question_id
            used_question_ids.add(generated_question_id)
            assigned_count += 1
        updated_rows.append(updated_row)

    return updated_rows, assigned_count


def option_id_for(question_id: object, option_index: int) -> str:
    return f"{question_id}:option_{option_index}"


def option_index_from_id(option_id: object) -> int | None:
    match = re.fullmatch(r".+:option_([1-4])", str(option_id))
    if not match:
        return None

    return int(match.group(1))


def path_identity(path: Path) -> str:
    return str(path.resolve())
