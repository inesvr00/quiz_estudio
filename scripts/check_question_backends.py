from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.config import QUESTIONS_CSV_PATH
from quiz_estudio.question_repository import (
    CSVQuestionRepository,
    QuestionRepository,
    SupabaseQuestionRepository,
    get_question_repository,
)
from quiz_estudio.supabase_question_client import REQUIRED_ENV_VARS


RepositoryFactory = Callable[[], QuestionRepository]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    exit_code, output = run_diagnostics()
    print(output)
    return exit_code


def run_diagnostics(
    *,
    csv_factory: RepositoryFactory | None = None,
    supabase_factory: RepositoryFactory | None = None,
    fallback_factory: RepositoryFactory | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    env = env if env is not None else os.environ
    csv_factory = csv_factory or (lambda: CSVQuestionRepository(QUESTIONS_CSV_PATH))
    supabase_factory = supabase_factory or SupabaseQuestionRepository
    fallback_factory = fallback_factory or (
        lambda: get_question_repository("supabase_with_csv_fallback")
    )

    lines = ["Diagnostico de backends de preguntas"]
    exit_code = 0
    supabase_configured = _has_supabase_config(env)
    supabase_ok = False

    try:
        csv_questions = csv_factory().list_questions()
    except Exception as exc:
        lines.append(f"CSV ERROR: {exc}")
        return 1, "\n".join(lines)

    lines.append(_format_backend_summary("CSV", csv_questions))

    if not supabase_configured:
        lines.append("Supabase no configurado: se omite comprobacion de Supabase.")
    else:
        try:
            supabase_questions = supabase_factory().list_questions()
            supabase_ok = True
            lines.append(_format_backend_summary("Supabase", supabase_questions))
        except Exception as exc:
            exit_code = 1
            lines.append(f"Supabase ERROR: {exc}")

    try:
        fallback_questions = fallback_factory().list_questions()
        expected_source = "Supabase" if supabase_ok else "CSV"
        lines.append(_format_backend_summary("Fallback", fallback_questions))
        lines.append(f"Fallback: origen usado {expected_source}.")
    except Exception as exc:
        exit_code = 1
        lines.append(f"Fallback ERROR: {exc}")

    return exit_code, "\n".join(lines)


def _format_backend_summary(label: str, questions: list[dict[str, Any]]) -> str:
    topic_count = len({str(question.get("tema", "")) for question in questions})
    lines = [
        f"{label} OK:",
        f"- preguntas: {len(questions)}",
        f"- temas: {topic_count}",
    ]

    if questions:
        sample = questions[0]
        lines.append(
            "- ejemplo: "
            f"question_id={sample.get('question_id')}; "
            f"opciones={len(sample.get('options', []))}"
        )
    else:
        lines.append("- ejemplo: sin preguntas")

    return "\n".join(lines)


def _has_supabase_config(env: Mapping[str, str]) -> bool:
    return all(env.get(name) for name in REQUIRED_ENV_VARS)


if __name__ == "__main__":
    raise SystemExit(main())
