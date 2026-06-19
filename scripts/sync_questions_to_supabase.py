from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.config import QUESTIONS_CSV_PATH
from quiz_estudio.question_repository import CSVQuestionRepository
from quiz_estudio.services.question_sync_service import (
    build_sync_records,
    format_sync_plan,
    plan_question_sync,
)
from quiz_estudio.supabase_question_client import (
    MissingSupabaseConfig,
    SupabaseQuestionClient,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Planifica o aplica la sincronizacion de preguntas desde el CSV "
            "principal hacia Supabase."
        ),
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=QUESTIONS_CSV_PATH,
        help="Ruta del CSV fuente de verdad. Por defecto usa preguntas_nuevo_formato.csv.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Escribe los cambios en Supabase. Sin esta opcion solo hace dry-run.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()

    try:
        questions = CSVQuestionRepository(args.csv_path).list_questions()
        csv_questions, csv_options = build_sync_records(questions)
        client = SupabaseQuestionClient.from_env()
        remote_questions = client.fetch_questions()
        remote_options = client.fetch_answer_options()
    except MissingSupabaseConfig as error:
        print(f"Configuracion incompleta: {error}")
        return 1
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"Error preparando la sincronizacion: {error}")
        return 1

    plan = plan_question_sync(
        csv_questions=csv_questions,
        csv_options=csv_options,
        remote_questions=remote_questions,
        remote_options=remote_options,
    )
    print(format_sync_plan(plan))

    if not args.apply:
        print("")
        print("Dry-run: no se ha escrito nada en Supabase.")
        return 0

    try:
        client.upsert_questions(plan.insert_questions + plan.update_questions)
        client.upsert_answer_options(plan.insert_options + plan.update_options)
        client.deactivate_answer_options(plan.deactivate_options)
        client.deactivate_questions(plan.deactivate_questions)
    except OSError as error:
        print(f"Error escribiendo en Supabase: {error}")
        return 1

    print("")
    print("Sincronizacion aplicada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
