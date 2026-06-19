from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .csv_repository import parse_teoria
from .question_model import (
    LEGACY_REQUIRED_COLUMNS,
    NEW_REQUIRED_COLUMNS,
    Question,
    question_from_legacy_row,
    question_from_new_row,
)


NEW_CSV_COLUMNS = [
    "question_id",
    "enunciado",
    "respuesta_correcta",
    "opcion_falsa_1",
    "opcion_falsa_2",
    "opcion_falsa_3",
    "explicacion",
    "tema",
    "teoria",
]


@dataclass(frozen=True)
class MigrationIssue:
    row_number: int
    enunciado: str
    detail: str


@dataclass(frozen=True)
class MigrationReport:
    total_rows: int
    migrated_rows: int
    failed_rows: int
    issues: list[MigrationIssue]


def migrate_legacy_csv(input_path: Path, output_path: Path) -> MigrationReport:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("La ruta de salida no puede ser el mismo CSV de entrada.")

    with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        with output_path.open("w", encoding="utf-8", newline="") as output_file:
            return migrate_legacy_file(input_file, output_file)


def migrate_legacy_file(input_file: TextIO, output_file: TextIO) -> MigrationReport:
    reader = csv.DictReader(input_file)
    writer = csv.DictWriter(output_file, fieldnames=NEW_CSV_COLUMNS)
    writer.writeheader()

    if reader.fieldnames is None:
        return MigrationReport(
            total_rows=0,
            migrated_rows=0,
            failed_rows=0,
            issues=[
                MigrationIssue(
                    row_number=1,
                    enunciado="",
                    detail="El CSV esta vacio o no tiene cabecera.",
                )
            ],
        )

    missing_columns = LEGACY_REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing_columns:
        total_rows = sum(1 for _ in reader)
        return MigrationReport(
            total_rows=total_rows,
            migrated_rows=0,
            failed_rows=total_rows,
            issues=[
                MigrationIssue(
                    row_number=1,
                    enunciado="",
                    detail=f"Faltan columnas legacy: {', '.join(sorted(missing_columns))}.",
                )
            ],
        )

    total_rows = 0
    migrated_rows = 0
    issues: list[MigrationIssue] = []

    for csv_id, row in enumerate(reader):
        total_rows += 1
        row_number = csv_id + 2

        try:
            migrated_row = migrate_legacy_row(row, csv_id, row_number)
        except ValueError as exc:
            issues.append(
                MigrationIssue(
                    row_number=row_number,
                    enunciado=_shorten(str(row.get("enunciado", ""))),
                    detail=str(exc),
                )
            )
            continue

        writer.writerow(migrated_row)
        migrated_rows += 1

    return MigrationReport(
        total_rows=total_rows,
        migrated_rows=migrated_rows,
        failed_rows=len(issues),
        issues=issues,
    )


def migrate_legacy_row(
    row: dict[str, str],
    csv_id: int,
    row_number: int,
) -> dict[str, str]:
    teoria = parse_teoria(str(row.get("teoria", "")), row_number)
    question = question_from_legacy_row(row, csv_id, teoria)
    migrated_row = _question_to_new_row(question, row)

    # Validate the exact output shape with the common model before writing it.
    question_from_new_row(migrated_row, csv_id, teoria)

    return migrated_row


def format_migration_report(report: MigrationReport) -> str:
    lines = [
        "Migracion de preguntas",
        f"- filas analizadas: {report.total_rows}",
        f"- filas migradas: {report.migrated_rows}",
        f"- filas con error: {report.failed_rows}",
    ]

    if report.issues:
        lines.append("")
        lines.append("Errores:")
        for issue in report.issues:
            enunciado = issue.enunciado or "-"
            lines.append(f"- fila {issue.row_number}: {issue.detail} | {enunciado}")

    return "\n".join(lines)


def _question_to_new_row(question: Question, source_row: dict[str, str]) -> dict[str, str]:
    correct_option = next(option for option in question.options if option.is_correct)
    false_options = [option for option in question.options if not option.is_correct]

    new_row = {
        "question_id": _question_id_for_output(source_row, question.csv_id),
        "enunciado": question.enunciado,
        "respuesta_correcta": correct_option.text,
        "opcion_falsa_1": false_options[0].text,
        "opcion_falsa_2": false_options[1].text,
        "opcion_falsa_3": false_options[2].text,
        "explicacion": question.explicacion,
        "tema": question.tema,
        "teoria": str(question.teoria),
    }

    missing_columns = NEW_REQUIRED_COLUMNS - set(new_row)
    if missing_columns:
        raise ValueError(f"Faltan columnas nuevas: {', '.join(sorted(missing_columns))}.")

    return new_row


def _question_id_for_output(row: dict[str, str], csv_id: int) -> str:
    question_id = str(row.get("question_id", "")).strip()
    if question_id:
        return question_id

    return f"q_{csv_id + 1:06d}"


def _shorten(value: str, max_length: int = 100) -> str:
    text = " ".join(value.strip().split())
    if len(text) <= max_length:
        return text

    return f"{text[: max_length - 3]}..."
