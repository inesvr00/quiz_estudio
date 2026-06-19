from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.config import DB_PATH
from quiz_estudio.question_repository import get_question_repository
from quiz_estudio.services.stats_question_audit_service import (
    audit_stats_question_ids,
    format_stats_question_audit_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita referencias de preguntas en la base de estadisticas.",
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        type=Path,
        default=DB_PATH,
        help="Ruta de la base SQLite de estadisticas. Por defecto usa local_data/stats.db.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Crea backup y deja preparado el modo escritura. No borra estadisticas.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()

    try:
        questions = get_question_repository("csv").list_questions()
        report = audit_stats_question_ids(args.db_path, questions, write=args.write)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Error auditando estadisticas: {error}")
        return 1

    print(format_stats_question_audit_report(report))
    return 0 if report.is_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
