from __future__ import annotations

import pytest

from quiz_estudio import create_app


def _build_questions(count: int = 73) -> list[dict[str, object]]:
    return [
        {
            "csv_id": index,
            "enunciado": f"Pregunta {index}",
            "opcion_1": "A",
            "opcion_2": "B",
            "opcion_3": "C",
            "opcion_4": "D",
            "respuesta_correcta": 1,
            "explicacion": "Explicacion",
            "tema": "Tema unico",
        }
        for index in range(count)
    ]


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
    _start_quiz(client, {"quiz_size_mode": quiz_size_mode})

    with client.session_transaction() as session_data:
        assert len(session_data["questions"]) == expected_count


def test_quiz_custom_size_overrides_quick_choice(client):
    _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "35"},
    )

    with client.session_transaction() as session_data:
        assert len(session_data["questions"]) == 35


def test_quiz_invalid_custom_falls_back_to_quick_choice(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "texto"},
    )

    with client.session_transaction() as session_data:
        assert len(session_data["questions"]) == 10

    assert b"entero mayor que 0" in response.data


def test_quiz_limits_to_available_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "100"},
    )

    with client.session_transaction() as session_data:
        assert len(session_data["questions"]) == 73

    assert b"Solo hay 73 preguntas disponibles" in response.data


def test_quiz_results_page_works(client):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        questions = session_data["questions"]

    answers = {f"pregunta_{question['csv_id']}": "1" for question in questions}
    response = client.post("/quiz", data=answers, follow_redirects=True)

    assert response.status_code == 200
    assert b"Correcci" in response.data
    assert b"Resultado:" in response.data
