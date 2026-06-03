from __future__ import annotations

import csv
import io
import shutil
from datetime import datetime
from pathlib import Path

from rapidfuzz import fuzz, process

from ..config import BACKUP_DIR, CSV_PATH
from ..csv_repository import normalize_text


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

duplicate_threshold = 92.0
review_threshold = 82.0
SENSITIVE_MARKERS = {"no", "excepto", "incorrecta", "falsa", "verdadera"}


def normalize_enunciado(enunciado: str) -> str:
    return normalize_text(enunciado)


def _extract_sensitive_markers(normalized_text: str) -> list[str]:
    return sorted(set(normalized_text.split()) & SENSITIVE_MARKERS)


def build_question_match_index(existing_questions: list[str]) -> list[dict[str, object]]:
    return [
        {
            "original": original_question,
            "normalized": normalized_question,
            "index": index,
            "sensitive_markers": _extract_sensitive_markers(normalized_question),
        }
        for index, original_question in enumerate(existing_questions)
        for normalized_question in [normalize_text(original_question)]
    ]


def _build_question_match_lookup(
    existing_question_index: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    return {
        entry["normalized"]: entry
        for entry in existing_question_index
    }


def _coerce_question_index(
    existing_question_index: list[dict[str, object]] | list[str],
) -> list[dict[str, object]]:
    if not existing_question_index:
        return []

    first_entry = existing_question_index[0]
    if isinstance(first_entry, dict):
        return existing_question_index  # type: ignore[return-value]

    return build_question_match_index(existing_question_index)  # type: ignore[arg-type]


def find_best_question_match(
    new_question: str,
    existing_question_index: list[dict[str, object]] | list[str],
    normalized_existing_questions: list[str] | None = None,
    score_cutoff: float = review_threshold,
) -> dict[str, object] | None:
    existing_question_index = _coerce_question_index(existing_question_index)
    if not existing_question_index:
        return None

    normalized_new_question = normalize_text(new_question)
    normalized_choices = (
        normalized_existing_questions
        if normalized_existing_questions is not None
        else [entry["normalized"] for entry in existing_question_index]
    )

    best_match = process.extractOne(
        normalized_new_question,
        normalized_choices,
        scorer=fuzz.token_set_ratio,
        score_cutoff=score_cutoff,
    )

    if best_match is None:
        return None

    matched_normalized_question, score, matched_index = best_match
    matched_entry = existing_question_index[matched_index]
    return {
        "question": matched_entry["original"],
        "score": float(score),
        "normalized_question": matched_normalized_question,
        "new_normalized_question": normalized_new_question,
        "index": int(matched_entry["index"]),
        "sensitive_markers": matched_entry["sensitive_markers"],
        "new_sensitive_markers": _extract_sensitive_markers(normalized_new_question),
    }


def classify_import_question(
    new_question: str,
    existing_question_index: list[dict[str, object]] | list[str],
    duplicate_threshold: float = duplicate_threshold,
    review_threshold: float = review_threshold,
    normalized_existing_questions: list[str] | None = None,
) -> tuple[str, dict[str, object] | None]:
    existing_question_index = _coerce_question_index(existing_question_index)
    best_match = find_best_question_match(
        new_question,
        existing_question_index,
        normalized_existing_questions=normalized_existing_questions,
        score_cutoff=review_threshold,
    )
    if best_match is None:
        return "new", None

    score = float(best_match["score"])
    new_markers = set(best_match["new_sensitive_markers"])
    matched_markers = set(best_match["sensitive_markers"])
    sensitive_mismatch = bool(new_markers ^ matched_markers)

    if score >= duplicate_threshold and not sensitive_mismatch:
        return "duplicate", best_match

    if score >= review_threshold or sensitive_mismatch:
        return "review", best_match

    return "new", None


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
    existing_rows = validate_main_csv_rows()
    existing_question_index = build_question_match_index(
        [row["enunciado"] for row in existing_rows]
    )
    normalized_existing_questions = [
        entry["normalized"] for entry in existing_question_index
    ]
    existing_question_lookup = _build_question_match_lookup(existing_question_index)
    valid_rows = []
    duplicates = []
    review_rows = []
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

            existing_match = existing_question_lookup.get(normalized_enunciado)
            if existing_match is not None:
                duplicates.append(
                    {
                        "row_number": row_number,
                        "enunciado": enunciado,
                        "tema": cleaned["tema"],
                        "matched_question": existing_match["original"],
                        "similarity": 100.0,
                    }
                )
                continue

            classification, best_match = classify_import_question(
                enunciado,
                existing_question_index,
                normalized_existing_questions=normalized_existing_questions,
            )

            if classification == "duplicate":
                duplicates.append(
                    {
                        "row_number": row_number,
                        "enunciado": enunciado,
                        "tema": cleaned["tema"],
                        "matched_question": best_match["question"] if best_match else enunciado,
                        "similarity": best_match["score"] if best_match else 100.0,
                    }
                )
                continue

            if classification == "review":
                review_rows.append(
                    {
                        "row_number": row_number,
                        **cleaned,
                        "matched_question": best_match["question"] if best_match else "",
                        "similarity": best_match["score"] if best_match else 0.0,
                        "new_sensitive_markers": best_match["new_sensitive_markers"] if best_match else [],
                        "matched_sensitive_markers": best_match["sensitive_markers"] if best_match else [],
                    }
                )
                continue

            valid_rows.append(
                {
                    "row_number": row_number,
                    **cleaned,
                }
            )
            new_index_entry = {
                "original": enunciado,
                "normalized": normalized_enunciado,
                "index": len(existing_question_index),
                "sensitive_markers": _extract_sensitive_markers(
                    normalized_enunciado
                ),
            }
            existing_question_index.append(new_index_entry)
            normalized_existing_questions.append(normalized_enunciado)
            existing_question_lookup[normalized_enunciado] = new_index_entry

    return {
        "total_read": total_read,
        "valid": valid_rows,
        "duplicates": duplicates,
        "review": review_rows,
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
    print(f"- preguntas importadas: {len(rows_to_add)}")
    print(f"- duplicadas ignoradas: {len(preview['duplicates'])}")
    print(f"- pendientes de revision: {len(preview['review'])}")
    print(f"- filas con errores: {len(preview['errors'])}")

    if backup_path:
        print(f"- copia de seguridad: {backup_path}")

    if preview["review"]:
        print("\nPendientes de revision:")
        for row in preview["review"]:
            print(
                "- Fila {row_number}: {enunciado} | similar a: {matched_question} | similitud: {similarity:.1f}%".format(
                    row_number=row["row_number"],
                    enunciado=row["enunciado"],
                    matched_question=row["matched_question"],
                    similarity=float(row["similarity"]),
                )
            )

    if preview["errors"]:
        print("\nErrores:")
        for row_error in preview["errors"]:
            for error in row_error["errors"]:
                print(f"- {error}")

    return 1 if preview["errors"] else 0
