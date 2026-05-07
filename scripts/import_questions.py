from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.services.import_service import import_questions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa preguntas validas y no duplicadas a preguntas.csv.",
        epilog=(
            "Validacion manual tras importar: "
            ".\\.venv\\Scripts\\python.exe -c \"from quiz_estudio.csv_repository "
            "import load_questions; print(len(load_questions()))\""
        ),
    )
    parser.add_argument("csv_path", type=Path, help="Ruta del CSV externo a importar.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return import_questions(args.csv_path)
    except (FileNotFoundError, ValueError, csv.Error) as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
