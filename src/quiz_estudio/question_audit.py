from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .csv_repository import parse_teoria
from .question_model import REQUIRED_COLUMNS, question_from_csv_row


@dataclass(frozen=True)
class AuditIssue:
    row_number: int
    question_id: str | None
    enunciado: str
    problem_type: str
    detail: str


@dataclass(frozen=True)
class AuditReport:
    total_rows: int
    valid_rows: int
    issues: list[AuditIssue]

    @property
    def invalid_rows(self) -> int:
        return len({issue.row_number for issue in self.issues})


def audit_questions_csv(csv_path: Path) -> AuditReport:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            return AuditReport(
                total_rows=0,
                valid_rows=0,
                issues=[
                    AuditIssue(
                        row_number=1,
                        question_id=None,
                        enunciado="",
                        problem_type="missing_columns",
                        detail="El CSV esta vacio o no tiene cabecera.",
                    )
                ],
            )

        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing_columns:
            return AuditReport(
                total_rows=0,
                valid_rows=0,
                issues=[
                    AuditIssue(
                        row_number=1,
                        question_id=None,
                        enunciado="",
                        problem_type="missing_columns",
                        detail="Faltan columnas: " + ", ".join(sorted(missing_columns)),
                    )
                ],
            )

        rows = list(reader)

    issues = []
    valid_rows = 0
    for csv_id, row in enumerate(rows):
        row_number = csv_id + 2
        row_issues = audit_question_row(row, csv_id, row_number)
        if row_issues:
            issues.extend(row_issues)
        else:
            valid_rows += 1

    return AuditReport(total_rows=len(rows), valid_rows=valid_rows, issues=issues)


def audit_question_row(
    row: dict[str, str],
    csv_id: int,
    row_number: int,
) -> list[AuditIssue]:
    question_id = row.get("question_id", "").strip()
    enunciado = _shorten(row.get("enunciado", ""))
    issues = []

    try:
        teoria = parse_teoria(row.get("teoria", ""), row_number)
    except ValueError as exc:
        issues.append(
            AuditIssue(row_number, question_id, enunciado, "invalid_teoria", str(exc))
        )
        teoria = 0

    option_columns = [
        "respuesta_correcta",
        "opcion_falsa_1",
        "opcion_falsa_2",
        "opcion_falsa_3",
    ]
    option_texts = []
    for column in option_columns:
        value = row.get(column, "")
        stripped_value = value.strip()
        if not stripped_value:
            issues.append(
                AuditIssue(
                    row_number,
                    question_id,
                    enunciado,
                    "empty_option",
                    f"{column} esta vacia",
                )
            )
        option_texts.append(stripped_value)

    duplicated_options = sorted(
        text for text in set(option_texts) if text and option_texts.count(text) > 1
    )
    if duplicated_options:
        issues.append(
            AuditIssue(
                row_number,
                question_id,
                enunciado,
                "duplicate_options",
                "Opciones duplicadas: " + ", ".join(duplicated_options),
            )
        )

    if len(option_texts) != 4:
        issues.append(
            AuditIssue(
                row_number,
                question_id,
                enunciado,
                "invalid_option_count",
                f"La pregunta tiene {len(option_texts)} opciones; se esperaban 4.",
            )
        )

    if not question_id:
        issues.append(
            AuditIssue(
                row_number,
                question_id,
                enunciado,
                "empty_question_id",
                "question_id esta vacio",
            )
        )

    if issues:
        return issues

    try:
        question = question_from_csv_row(row, csv_id, teoria)
    except ValueError as exc:
        return [
            AuditIssue(
                row_number,
                question_id,
                enunciado,
                _problem_type_from_model_error(str(exc)),
                str(exc),
            )
        ]

    correct_count = sum(option.is_correct for option in question.options)
    if correct_count != 1:
        return [
            AuditIssue(
                row_number,
                question_id,
                enunciado,
                "invalid_correct_count",
                f"La pregunta tiene {correct_count} respuestas correctas.",
            )
        ]

    return []


def format_audit_report(report: AuditReport) -> str:
    lines = [
        "Auditoria del CSV de preguntas",
        f"- filas analizadas: {report.total_rows}",
        f"- preguntas validas: {report.valid_rows}",
        f"- preguntas invalidas: {report.invalid_rows}",
        f"- errores: {len(report.issues)}",
    ]

    if not report.issues:
        lines.append("OK: no se han encontrado problemas.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Errores encontrados:")
    for issue in report.issues:
        question_id = issue.question_id if issue.question_id else "-"
        enunciado = issue.enunciado or "-"
        lines.append(
            f"- fila {issue.row_number} | question_id {question_id} | "
            f"{issue.problem_type}: {issue.detail} | {enunciado}"
        )

    return "\n".join(lines)


def _shorten(text: str, max_length: int = 80) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3] + "..."


def _problem_type_from_model_error(error: str) -> str:
    if "duplicadas" in error:
        return "duplicate_options"
    if "vacias" in error:
        return "empty_option"
    if "4 opciones" in error:
        return "invalid_option_count"
    if "correcta" in error:
        return "invalid_correct_count"
    return "invalid_question"
