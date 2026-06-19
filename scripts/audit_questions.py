from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.config import QUESTIONS_CSV_PATH
from quiz_estudio.question_audit import audit_questions_csv, format_audit_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita un CSV de preguntas y muestra errores de datos.",
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=QUESTIONS_CSV_PATH,
        help="Ruta del CSV a auditar. Por defecto usa preguntas_nuevo_formato.csv.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()

    try:
        report = audit_questions_csv(args.csv_path)
    except (FileNotFoundError, csv.Error, OSError) as error:
        print(f"Error: {error}")
        return 1

    print(format_audit_report(report))
    return 1 if report.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
