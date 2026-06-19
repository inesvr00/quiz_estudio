from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.config import QUESTIONS_CSV_PATH
from quiz_estudio.question_ids import assign_missing_question_ids, validate_question_ids
from quiz_estudio.services.import_service import NEW_COLUMNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Asigna question_id solo a filas que no lo tengan.",
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=QUESTIONS_CSV_PATH,
        help="CSV de preguntas. Por defecto usa preguntas_nuevo_formato.csv.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe los cambios. Sin esta opcion solo muestra el reporte.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with args.csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    updated_rows, assigned_count = assign_missing_question_ids(rows)
    issues = validate_question_ids(updated_rows)

    print(f"Filas leidas: {len(rows)}")
    print(f"IDs asignados: {assigned_count}")
    print(f"Problemas restantes: {len(issues)}")
    for issue in issues:
        print(f"- fila {issue.row_number}: {issue.detail} ({issue.question_id or '-'})")

    if args.write and assigned_count:
        with args.csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=NEW_COLUMNS)
            writer.writeheader()
            writer.writerows({column: row.get(column, "") for column in NEW_COLUMNS} for row in updated_rows)
        print(f"Archivo actualizado: {args.csv_path}")

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
