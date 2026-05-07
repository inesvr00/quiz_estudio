from __future__ import annotations

import csv
import io
import re
import shutil
from datetime import datetime
from pathlib import Path

from ..config import BACKUP_DIR, CSV_PATH


EXPECTED_COLUMNS = [
    "enunciado",
    "opcion_1",
    "opcion_2",
    "opcion_3",
    "opcion_4",
    "respuesta_correcta",
    "explicacion",
    "tema",
]
REQUIRED_NON_EMPTY = [
    "enunciado",
    "opcion_1",
    "opcion_2",
    "opcion_3",
    "opcion_4",
    "respuesta_correcta",
    "tema",
]


def normalize_enunciado(enunciado: str) -> str:
    return re.sub(r"\s+", " ", enunciado.strip()).lower()


def validate_main_csv_rows() -> list[dict[str, str]]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No existe el CSV principal: {CSV_PATH}")

    rows = []
    errors = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        validate_header(reader.fieldnames)

        for row_number, row in enumerate(reader, start=2):
            row_errors = validate_row(row, row_number)
            if row_errors:
                errors.extend(row_errors)
            else:
                rows.append(clean_row(row))

    if errors:
        raise ValueError(
            "preguntas.csv contiene filas invalidas:\n" + "\n".join(errors)
        )

    return rows


def read_existing_questions() -> set[str]:
    return {
        normalize_enunciado(row["enunciado"])
        for row in validate_main_csv_rows()
    }


def validate_header(fieldnames: list[str] | None) -> None:
    if fieldnames != EXPECTED_COLUMNS:
        received = ", ".join(fieldnames or [])
        expected = ", ".join(EXPECTED_COLUMNS)
        raise ValueError(
            "El CSV externo debe tener exactamente estas columnas y en este orden:\n"
            f"{expected}\n"
            f"Columnas recibidas: {received or '(ninguna)'}"
        )


def validate_row(row: dict[str, str], row_number: int) -> list[str]:
    errors = []

    if None in row:
        errors.append("tiene mas columnas que la cabecera")

    for column in REQUIRED_NON_EMPTY:
        if not row.get(column, "").strip():
            errors.append(f"{column} esta vacio")

    raw_answer = row.get("respuesta_correcta", "").strip()
    if raw_answer:
        try:
            answer = int(raw_answer)
        except ValueError:
            errors.append("respuesta_correcta debe ser un entero entre 1 y 4")
        else:
            if answer < 1 or answer > 4:
                errors.append("respuesta_correcta debe estar entre 1 y 4")

    return [f"Fila {row_number}: {error}" for error in errors]


def clean_row(row: dict[str, str]) -> dict[str, str]:
    cleaned = {column: row.get(column, "").strip() for column in EXPECTED_COLUMNS}
    cleaned["respuesta_correcta"] = str(int(cleaned["respuesta_correcta"]))
    return cleaned


def create_backup() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"preguntas_{timestamp}.csv"
    shutil.copy2(CSV_PATH, backup_path)
    return backup_path


def ensure_csv_ends_with_newline() -> None:
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return

    with CSV_PATH.open("rb") as file:
        file.seek(-1, 2)
        last_byte = file.read(1)

    if last_byte != b"\n":
        with CSV_PATH.open("a", encoding="utf-8-sig", newline="") as file:
            file.write("\n")


def preview_questions_from_text(csv_text: str) -> dict[str, object]:
    existing_questions = read_existing_questions()
    valid_rows = []
    duplicates = []
    errors = []
    total_read = 0

    with io.StringIO(csv_text.strip().lstrip("\ufeff")) as file:
        reader = csv.DictReader(file)
        validate_header(reader.fieldnames)

        for row_number, row in enumerate(reader, start=2):
            total_read += 1
            row_errors = validate_row(row, row_number)

            if row_errors:
                errors.append(
                    {
                        "row_number": row_number,
                        "enunciado": row.get("enunciado", ""),
                        "errors": row_errors,
                    }
                )
                continue

            cleaned = clean_row(row)
            enunciado = cleaned["enunciado"]
            normalized_enunciado = normalize_enunciado(enunciado)

            if normalized_enunciado in existing_questions:
                duplicates.append(
                    {
                        "row_number": row_number,
                        "enunciado": enunciado,
                        "tema": cleaned["tema"],
                    }
                )
                continue

            valid_rows.append(
                {
                    "row_number": row_number,
                    **cleaned,
                }
            )
            existing_questions.add(normalized_enunciado)

    return {
        "total_read": total_read,
        "valid": valid_rows,
        "duplicates": duplicates,
        "errors": errors,
    }


def append_questions(rows: list[dict[str, str]]) -> Path | None:
    if not rows:
        return None

    backup_path = create_backup()
    ensure_csv_ends_with_newline()
    with CSV_PATH.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EXPECTED_COLUMNS)
        writer.writerows(
            {column: row[column] for column in EXPECTED_COLUMNS}
            for row in rows
        )

    validate_main_csv_rows()
    return backup_path


def rewrite_main_csv(rows: list[dict[str, str]]) -> None:
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def deduplicate_main_csv() -> dict[str, object]:
    rows = validate_main_csv_rows()
    last_index_by_enunciado = {
        normalize_enunciado(row["enunciado"]): index
        for index, row in enumerate(rows)
    }
    final_rows = [
        row
        for index, row in enumerate(rows)
        if last_index_by_enunciado[normalize_enunciado(row["enunciado"])] == index
    ]
    duplicates_removed = len(rows) - len(final_rows)

    backup_path = create_backup()
    if duplicates_removed:
        rewrite_main_csv(final_rows)
        validate_main_csv_rows()

    return {
        "original_rows": len(rows),
        "duplicates_removed": duplicates_removed,
        "final_rows": len(final_rows),
        "backup_path": backup_path,
    }


def import_questions(import_path: Path) -> int:
    if not import_path.exists():
        raise FileNotFoundError(f"No existe el CSV externo: {import_path}")

    with import_path.open("r", encoding="utf-8-sig", newline="") as file:
        preview = preview_questions_from_text(file.read())

    rows_to_add = preview["valid"]
    backup_path = append_questions(rows_to_add)

    print("Resumen de importacion")
    print(f"- preguntas leidas: {preview['total_read']}")
    print(f"- preguntas anadidas: {len(rows_to_add)}")
    print(f"- duplicadas ignoradas: {len(preview['duplicates'])}")
    print(f"- filas con errores: {len(preview['errors'])}")

    if backup_path:
        print(f"- copia de seguridad: {backup_path}")

    if preview["errors"]:
        print("\nErrores:")
        for row_error in preview["errors"]:
            for error in row_error["errors"]:
                print(f"- {error}")

    return 1 if preview["errors"] else 0
