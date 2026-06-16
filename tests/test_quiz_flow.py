from __future__ import annotations

import pytest

from quiz_estudio import create_app


def _build_questions(count: int = 73) -> list[dict[str, object]]:
    return [
        {
            "question_id": index,
            "csv_id": index,
            "enunciado": f"Pregunta {index}",
            "opcion_1": "A",
            "opcion_2": "B",
            "opcion_3": "C",
            "opcion_4": "D",
            "respuesta_correcta": 1,
            "explicacion": "Explicacion",
            "tema": "Tema unico",
            "teoria": index % 2,
        }
        for index in range(count)
    ]


def _build_practical_only_questions(count: int = 10) -> list[dict[str, object]]:
    questions = _build_questions(count)

    for question in questions:
        question["teoria"] = 0

    return questions


class _FakeRepository:
    def initialize(self) -> None:
        return None

    def get_seen_question_ids(self) -> set[int]:
        return set()

    def save_attempts(self, attempts) -> None:
        self.saved_attempts = list(attempts)


@pytest.fixture()
def app(monkeypatch):
    fake_repo = _FakeRepository()

    monkeypatch.setattr("quiz_estudio.db.get_attempt_repository", lambda: fake_repo)
    monkeypatch.setattr("quiz_estudio.services.quiz_service.get_attempt_repository", lambda: fake_repo)
    monkeypatch.setattr("quiz_estudio.services.stats_service.get_attempt_repository", lambda: fake_repo)
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.load_questions", lambda: _build_questions())

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def _start_quiz(client, data):
    response = client.post("/", data=data, follow_redirects=True)
    assert response.status_code == 200
    return response


@pytest.mark.parametrize(
    "quiz_size_mode,expected_count",
    [
        ("1", 1),
        ("10", 10),
    ],
)
def test_quiz_quick_sizes_work(client, quiz_size_mode, expected_count):
    response = _start_quiz(client, {"quiz_size_mode": quiz_size_mode})

    with client.session_transaction() as session_data:
        assert len(session_data["question_ids"]) == expected_count
        assert "questions" not in session_data

    assert b"Terminar y corregir" in response.data


def test_quiz_custom_size_overrides_quick_choice(client):
    _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "35"},
    )

    with client.session_transaction() as session_data:
        assert len(session_data["question_ids"]) == 35
        assert "questions" not in session_data


def test_quiz_theory_mode_filters_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "10", "quiz_mode": "theory"},
    )

    with client.session_transaction() as session_data:
        assert session_data["quiz_mode"] == "theory"
        assert len(session_data["question_ids"]) == 10
        assert all(question_id % 2 == 1 for question_id in session_data["question_ids"])

    assert b"Terminar y corregir" in response.data


def test_quiz_practical_mode_filters_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "10", "quiz_mode": "practical"},
    )

    with client.session_transaction() as session_data:
        assert session_data["quiz_mode"] == "practical"
        assert len(session_data["question_ids"]) == 10
        assert all(question_id % 2 == 0 for question_id in session_data["question_ids"])

    assert b"Terminar y corregir" in response.data


def test_quiz_invalid_custom_falls_back_to_quick_choice(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "texto"},
    )

    with client.session_transaction() as session_data:
        assert len(session_data["question_ids"]) == 10
        assert "questions" not in session_data

    assert b"entero mayor que 0" in response.data


def test_quiz_limits_to_available_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "100"},
    )

    with client.session_transaction() as session_data:
        assert len(session_data["question_ids"]) == 73
        assert "questions" not in session_data

    assert b"Solo hay 73 preguntas disponibles" in response.data


def test_quiz_shows_clear_error_when_topics_and_mode_are_empty(client, monkeypatch):
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.load_questions", lambda: _build_practical_only_questions())

    response = client.post(
        "/",
        data={
            "quiz_mode": "theory",
            "temas": "Tema unico",
            "quiz_size_mode": "10",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"No hay preguntas para los temas y modo seleccionados." in response.data
    with client.session_transaction() as session_data:
        assert "question_ids" not in session_data
        assert session_data.get("quiz_mode") is None


def test_quiz_results_page_works(client):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        question_ids = session_data["question_ids"]

    answers = {f"pregunta_{question_id}": "1" for question_id in question_ids}
    response = client.post("/quiz", data=answers, follow_redirects=True)

    assert response.status_code == 200
    assert b"Correcci" in response.data
    assert b"Resultado:" in response.data


def test_otra_mas_rebuilds_questions_from_ids(client):
    _start_quiz(client, {"quiz_size_mode": "10"})

    response = client.get("/otra-mas", follow_redirects=True)

    assert response.status_code == 200
    assert b"Terminar y corregir" in response.data

    with client.session_transaction() as session_data:
        assert len(session_data["question_ids"]) == 10
        assert "questions" not in session_data
