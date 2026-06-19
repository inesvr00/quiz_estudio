from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.config import QUESTIONS_CSV_PATH
from quiz_estudio.question_repository import (
    CSVQuestionRepository,
    SupabaseQuestionRepository,
)
from quiz_estudio.services.question_parity_service import (
    compare_question_repositories,
    format_parity_report,
)
from quiz_estudio.supabase_question_client import MissingSupabaseConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comprueba paridad de preguntas entre CSV y Supabase.",
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=QUESTIONS_CSV_PATH,
        help="Ruta del CSV fuente de verdad. Por defecto usa preguntas_nuevo_formato.csv.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()

    try:
        csv_questions = CSVQuestionRepository(args.csv_path).list_questions()
        supabase_questions = SupabaseQuestionRepository().list_questions()
    except MissingSupabaseConfig as error:
        print(f"Configuracion incompleta: {error}")
        return 1
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"Error comprobando paridad: {error}")
        return 1

    report = compare_question_repositories(csv_questions, supabase_questions)
    print(format_parity_report(report))
    return 0 if report.is_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
