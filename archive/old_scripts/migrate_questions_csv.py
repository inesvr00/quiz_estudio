from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.config import PROJECT_ROOT
from quiz_estudio.question_migration import (
    format_migration_report,
    migrate_legacy_csv,
)


DEFAULT_INPUT_PATH = PROJECT_ROOT / "preguntas.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "preguntas_nuevo_formato.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra preguntas.csv legacy al nuevo formato legible.",
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="CSV legacy de entrada. Por defecto usa preguntas.csv.",
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="CSV nuevo de salida. Por defecto usa preguntas_nuevo_formato.csv.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()

    try:
        report = migrate_legacy_csv(args.input_path, args.output_path)
    except (FileNotFoundError, ValueError, csv.Error, OSError) as error:
        print(f"Error: {error}")
        return 1

    print(format_migration_report(report))
    print(f"\nArchivo generado: {args.output_path}")
    return 1 if report.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
