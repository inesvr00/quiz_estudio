from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_question_backends.py"
spec = importlib.util.spec_from_file_location("check_question_backends", SCRIPT_PATH)
check_question_backends = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_question_backends)


class FakeRepository:
    def __init__(self, questions=None, error: Exception | None = None) -> None:
        self.questions = questions or [make_question("q_000001", "Tema")]
        self.error = error

    def list_questions(self):
        if self.error:
            raise self.error

        return self.questions


def make_question(question_id: str, tema: str) -> dict[str, object]:
    return {
        "question_id": question_id,
        "enunciado": f"Pregunta {question_id}",
        "tema": tema,
        "options": [
            {"option_id": f"{question_id}:option_1", "text": "A", "is_correct": True},
            {"option_id": f"{question_id}:option_2", "text": "B", "is_correct": False},
            {"option_id": f"{question_id}:option_3", "text": "C", "is_correct": False},
            {"option_id": f"{question_id}:option_4", "text": "D", "is_correct": False},
        ],
    }


def supabase_env() -> dict[str, str]:
    return {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "secret",
        "SUPABASE_DATABASE_URL": "postgresql://example",
    }


def test_csv_backend_works() -> None:
    exit_code, output = check_question_backends.run_diagnostics(
        csv_factory=lambda: FakeRepository(),
        supabase_factory=lambda: FakeRepository(),
        fallback_factory=lambda: FakeRepository(),
        env={},
    )

    assert exit_code == 0
    assert "CSV OK:" in output
    assert "preguntas: 1" in output


def test_csv_backend_failure_returns_error() -> None:
    exit_code, output = check_question_backends.run_diagnostics(
        csv_factory=lambda: FakeRepository(error=RuntimeError("csv roto")),
        supabase_factory=lambda: FakeRepository(),
        fallback_factory=lambda: FakeRepository(),
        env={},
    )

    assert exit_code == 1
    assert "CSV ERROR: csv roto" in output


def test_supabase_not_configured_is_skipped() -> None:
    exit_code, output = check_question_backends.run_diagnostics(
        csv_factory=lambda: FakeRepository(),
        supabase_factory=lambda: FakeRepository(error=AssertionError("no llamar")),
        fallback_factory=lambda: FakeRepository(),
        env={},
    )

    assert exit_code == 0
    assert "Supabase no configurado" in output


def test_configured_supabase_backend_works() -> None:
    exit_code, output = check_question_backends.run_diagnostics(
        csv_factory=lambda: FakeRepository(),
        supabase_factory=lambda: FakeRepository(
            [make_question("q_000002", "Supabase")]
        ),
        fallback_factory=lambda: FakeRepository(
            [make_question("q_000002", "Supabase")]
        ),
        env=supabase_env(),
    )

    assert exit_code == 0
    assert "Supabase OK:" in output
    assert "Fallback: origen usado Supabase." in output


def test_configured_supabase_failure_returns_error() -> None:
    exit_code, output = check_question_backends.run_diagnostics(
        csv_factory=lambda: FakeRepository(),
        supabase_factory=lambda: FakeRepository(error=ConnectionError("sin conexion")),
        fallback_factory=lambda: FakeRepository(),
        env=supabase_env(),
    )

    assert exit_code == 1
    assert "Supabase ERROR: sin conexion" in output


def test_fallback_uses_csv_when_supabase_fails() -> None:
    exit_code, output = check_question_backends.run_diagnostics(
        csv_factory=lambda: FakeRepository(),
        supabase_factory=lambda: FakeRepository(error=TimeoutError("timeout")),
        fallback_factory=lambda: FakeRepository([make_question("q_000001", "CSV")]),
        env=supabase_env(),
    )

    assert exit_code == 1
    assert "Fallback OK:" in output
    assert "Fallback: origen usado CSV." in output
