from __future__ import annotations

import re

import pytest
from werkzeug.datastructures import MultiDict

from quiz_estudio import create_app


def _build_questions(count: int = 73) -> list[dict[str, object]]:
    return [
        {
            "question_id": f"q_{index + 1:06d}",
            "csv_id": index,
            "enunciado": f"Pregunta q_{index + 1:06d}",
            "respuesta_correcta": 1,
            "explicacion": "Explicacion",
            "tema": "Tema unico",
            "teoria": index % 2,
            "options": [
                {
                    "option_id": f"q_{index + 1:06d}:option_1",
                    "text": "A",
                    "is_correct": True,
                },
                {
                    "option_id": f"q_{index + 1:06d}:option_2",
                    "text": "B",
                    "is_correct": False,
                },
                {
                    "option_id": f"q_{index + 1:06d}:option_3",
                    "text": "C",
                    "is_correct": False,
                },
                {
                    "option_id": f"q_{index + 1:06d}:option_4",
                    "text": "D",
                    "is_correct": False,
                },
            ],
        }
        for index in range(count)
    ]


def _build_practical_only_questions(count: int = 10) -> list[dict[str, object]]:
    questions = _build_questions(count)

    for question in questions:
        question["teoria"] = 0

    return questions


class _FakeRepository:
    def __init__(self) -> None:
        self.saved_attempts = []

    def initialize(self) -> None:
        return None

    def get_seen_question_ids(self) -> set[int]:
        return set()

    def save_attempts(self, attempts) -> None:
        self.saved_attempts.extend(attempts)

    def get_seen_question_enunciados_by_topic(self) -> list[dict[str, object]]:
        return [
            {"tema": tema, "enunciado": enunciado}
            for _, enunciado, tema, _, _, _ in self.saved_attempts
        ]

    def get_totals(self) -> dict[str, int]:
        return {
            "total": len(self.saved_attempts),
            "aciertos": sum(1 for *_, es_correcta in self.saved_attempts if es_correcta),
        }

    def get_topic_totals(self) -> list[dict[str, object]]:
        totals: dict[str, dict[str, object]] = {}
        for _, _, tema, _, _, es_correcta in self.saved_attempts:
            row = totals.setdefault(tema, {"tema": tema, "total": 0, "aciertos": 0})
            row["total"] += 1
            row["aciertos"] += int(es_correcta)

        return list(totals.values())

    def get_attempt_topics(self) -> list[str]:
        return sorted({tema for _, _, tema, _, _, _ in self.saved_attempts})

    def count_failed_questions(self, tema: str | None = None) -> int:
        return len(self._failed_question_rows(tema))

    def get_failed_questions(self, tema, order_clause, limit, offset):
        return self._failed_question_rows(tema)[offset : offset + limit]

    def _failed_question_rows(self, tema: str | None = None) -> list[dict[str, object]]:
        grouped: dict[tuple[int, str, str], dict[str, object]] = {}
        for question_id, enunciado, question_tema, _, _, es_correcta in self.saved_attempts:
            if tema and question_tema != tema:
                continue
            row = grouped.setdefault(
                (question_id, enunciado, question_tema),
                {
                    "question_id": question_id,
                    "enunciado": enunciado,
                    "tema": question_tema,
                    "total": 0,
                    "aciertos": 0,
                },
            )
            row["total"] += 1
            row["aciertos"] += int(es_correcta)

        failed_rows = []
        for row in grouped.values():
            fallos = row["total"] - row["aciertos"]
            if fallos <= 0:
                continue
            failed_rows.append(
                {
                    **row,
                    "fallos": fallos,
                    "porcentaje_fallo": (fallos * 100.0) / row["total"],
                }
            )

        return failed_rows


@pytest.fixture()
def app(monkeypatch):
    fake_repo = _FakeRepository()

    monkeypatch.setattr("quiz_estudio.db.get_attempt_repository", lambda: fake_repo)
    monkeypatch.setattr("quiz_estudio.services.quiz_service.get_attempt_repository", lambda: fake_repo)
    monkeypatch.setattr("quiz_estudio.services.stats_service.get_attempt_repository", lambda: fake_repo)
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.load_questions", lambda: _build_questions())
    monkeypatch.setattr(
        "quiz_estudio.services.stats_service.get_questions_by_topic_from_csv",
        lambda: {"Tema unico": _build_questions()},
    )

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    app.config["fake_repo"] = fake_repo
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


def _start_quiz_without_follow(client, data):
    response = client.post("/", data=data, follow_redirects=False)
    assert response.status_code == 302
    return response


def _reverse_shuffle(values):
    values.reverse()


def _quiz_answer_data(attempt_id: str, question_ids: list[str], option_number: int = 1) -> MultiDict:
    return MultiDict(
        [
            ("attempt_id", attempt_id),
            *[("question_id", question_id) for question_id in question_ids],
            *[
                (f"pregunta_{question_id}", f"{question_id}:option_{option_number}")
                for question_id in question_ids
            ],
        ]
    )


def _active_attempt(session_data):
    attempt_id = session_data["active_attempt_id"]
    return attempt_id, session_data["quiz_attempts"][attempt_id]


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
        _, attempt = _active_attempt(session_data)
        assert len(attempt["question_ids"]) == expected_count
        assert "question_ids" not in session_data
        assert "option_orders" not in session_data
        assert "questions" not in session_data

    assert b"Terminar y corregir" in response.data


def test_quiz_options_are_shuffled_when_attempt_is_created(client, monkeypatch):
    monkeypatch.setattr("quiz_estudio.services.quiz_correction_service.random.shuffle", _reverse_shuffle)

    response = _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        question_id = str(attempt["question_ids"][0])
        assert attempt["option_order"][question_id] == [
            f"{question_id}:option_4",
            f"{question_id}:option_3",
            f"{question_id}:option_2",
            f"{question_id}:option_1",
        ]

    assert response.data.find(b"1. D") < response.data.find(b"4. A")


def test_quiz_option_order_stays_stable_within_attempt(client, monkeypatch):
    monkeypatch.setattr("quiz_estudio.services.quiz_correction_service.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        initial_orders = dict(attempt["option_order"])

    response = client.get("/quiz")

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        assert attempt["option_order"] == initial_orders

    assert response.data.find(b"1. D") < response.data.find(b"4. A")


def test_quiz_custom_size_overrides_quick_choice(client):
    _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "35"},
    )

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        assert len(attempt["question_ids"]) == 35
        assert "question_ids" not in session_data
        assert "questions" not in session_data


def test_quiz_theory_mode_filters_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "10", "quiz_mode": "theory"},
    )

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        assert attempt["mode"] == "theory"
        assert len(attempt["question_ids"]) == 10
        assert all(int(question_id.removeprefix("q_")) % 2 == 0 for question_id in attempt["question_ids"])

    assert b"Terminar y corregir" in response.data


def test_quiz_practical_mode_filters_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "10", "quiz_mode": "practical"},
    )

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        assert attempt["mode"] == "practical"
        assert len(attempt["question_ids"]) == 10
        assert all(int(question_id.removeprefix("q_")) % 2 == 1 for question_id in attempt["question_ids"])

    assert b"Terminar y corregir" in response.data


def test_quiz_invalid_custom_falls_back_to_quick_choice(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "texto"},
    )

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        assert len(attempt["question_ids"]) == 10
        assert "question_ids" not in session_data
        assert "questions" not in session_data

    assert b"entero mayor que 0" in response.data


def test_quiz_limits_to_available_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "custom", "custom_num_preguntas": "100"},
    )

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        assert len(attempt["question_ids"]) == 73
        assert "question_ids" not in session_data
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
        assert "quiz_attempts" not in session_data


def test_quiz_results_page_works(client):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_ids = attempt["question_ids"]

    answers = _quiz_answer_data(attempt_id, question_ids)
    response = client.post("/quiz", data=answers, follow_redirects=True)

    assert response.status_code == 200
    assert b"Correcci" in response.data
    assert b"Resultado:" in response.data
    for question_id in question_ids:
        assert f"Pregunta {question_id}".encode() in response.data


def test_quiz_results_use_exact_question_ids_from_started_attempt(client):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_ids = list(attempt["question_ids"])

    answers = _quiz_answer_data(attempt_id, question_ids)
    response = client.post("/quiz", data=answers, follow_redirects=True)

    assert response.status_code == 200
    rendered_question_ids = [
        match.decode()
        for match in re.findall(rb"Pregunta (q_\d{6})", response.data)
    ]
    assert rendered_question_ids == question_ids
    assert b"Resultado: 10/10" in response.data


def test_quiz_post_does_not_select_random_questions(client, monkeypatch):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_ids = list(attempt["question_ids"])

    def fail_if_selected(*args, **kwargs):
        raise AssertionError("POST /quiz must not select quiz questions")

    monkeypatch.setattr("quiz_estudio.blueprints.quiz.select_quiz_questions", fail_if_selected)
    response = client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, question_ids),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Resultado: 10/10" in response.data


def test_quiz_post_without_attempt_does_not_silently_select_new_questions(client, monkeypatch):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_ids = list(attempt["question_ids"])
        session_data.clear()

    def fail_if_selected(*args, **kwargs):
        raise AssertionError("Missing attempts must not select quiz questions")

    monkeypatch.setattr("quiz_estudio.blueprints.quiz.select_quiz_questions", fail_if_selected)
    response = client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, question_ids),
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert b"intento" in response.data.lower()
    assert b"Resultado:" not in response.data


def test_two_quizzes_in_different_tabs_are_corrected_by_attempt_id(client):
    _start_quiz(client, {"quiz_size_mode": "10", "quiz_mode": "theory"})

    with client.session_transaction() as session_data:
        first_attempt_id, first_attempt = _active_attempt(session_data)
        first_question_ids = list(first_attempt["question_ids"])

    _start_quiz(client, {"quiz_size_mode": "10", "quiz_mode": "practical"})

    with client.session_transaction() as session_data:
        second_attempt_id, second_attempt = _active_attempt(session_data)
        second_question_ids = list(second_attempt["question_ids"])

    assert first_attempt_id != second_attempt_id
    assert first_question_ids != second_question_ids

    response = client.post(
        "/quiz",
        data=_quiz_answer_data(first_attempt_id, first_question_ids),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Resultado: 10/10" in response.data
    for question_id in first_question_ids:
        assert f"Pregunta {question_id}".encode() in response.data
    for question_id in second_question_ids:
        assert f"Pregunta {question_id}".encode() not in response.data


def test_refreshing_first_quiz_tab_uses_query_attempt_id_after_second_quiz(client):
    first_response = _start_quiz_without_follow(client, {"quiz_size_mode": "10", "quiz_mode": "theory"})
    first_quiz_url = first_response.headers["Location"]

    with client.session_transaction() as session_data:
        first_attempt_id = session_data["active_attempt_id"]
        first_question_ids = list(session_data["quiz_attempts"][first_attempt_id]["question_ids"])

    second_response = _start_quiz_without_follow(client, {"quiz_size_mode": "10", "quiz_mode": "practical"})
    second_quiz_url = second_response.headers["Location"]

    with client.session_transaction() as session_data:
        second_attempt_id = session_data["active_attempt_id"]
        second_question_ids = list(session_data["quiz_attempts"][second_attempt_id]["question_ids"])

    assert first_attempt_id != second_attempt_id
    assert first_quiz_url.endswith(f"/quiz?attempt_id={first_attempt_id}")
    assert second_quiz_url.endswith(f"/quiz?attempt_id={second_attempt_id}")

    response = client.get(first_quiz_url)

    assert response.status_code == 200
    for question_id in first_question_ids:
        assert f"Pregunta {question_id}".encode() in response.data
    for question_id in second_question_ids:
        assert f"Pregunta {question_id}".encode() not in response.data


def test_attempt_questions_preserve_attempt_order_when_repository_returns_unordered(client, monkeypatch):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_ids = list(attempt["question_ids"])

    def reversed_get_questions_by_ids(questions, requested_question_ids):
        questions_by_id = {question["question_id"]: question for question in questions}
        return [
            questions_by_id[question_id]
            for question_id in reversed(requested_question_ids)
            if question_id in questions_by_id
        ]

    monkeypatch.setattr("quiz_estudio.services.quiz_correction_service.get_questions_by_ids", reversed_get_questions_by_ids)
    response = client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, question_ids),
        follow_redirects=True,
    )

    rendered_question_ids = [
        match.decode()
        for match in re.findall(rb"Pregunta (q_\d{6})", response.data)
    ]
    assert rendered_question_ids == question_ids


def test_invalid_option_order_falls_back_without_breaking_quiz(client):
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_id = attempt["question_ids"][0]
        attempt["option_order"][question_id] = f"{question_id}:option_1"
        session_data["quiz_attempts"] = {
            **session_data["quiz_attempts"],
            attempt_id: attempt,
        }

    response = client.get(f"/quiz?attempt_id={attempt_id}")

    assert response.status_code == 200
    assert f"Pregunta {question_id}".encode() in response.data
    for option_text in (b"1. A</span>", b"2. B</span>", b"3. C</span>", b"4. D</span>"):
        assert option_text in response.data


def test_correct_option_scores_even_when_visual_position_changes(client, app, monkeypatch):
    monkeypatch.setattr("quiz_estudio.services.quiz_correction_service.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_id = attempt["question_ids"][0]

    response = client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, [question_id]),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Resultado: 1/1" in response.data
    assert app.config["fake_repo"].saved_attempts[-1] == (
        int(question_id.removeprefix("q_")),
        f"Pregunta {question_id}",
        "Tema unico",
        1,
        1,
        True,
    )


def test_false_option_fails_even_if_it_is_first_visual_option(client, app, monkeypatch):
    monkeypatch.setattr("quiz_estudio.services.quiz_correction_service.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_id = attempt["question_ids"][0]

    response = client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, [question_id], option_number=4),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Resultado: 0/1" in response.data
    assert app.config["fake_repo"].saved_attempts[-1] == (
        int(question_id.removeprefix("q_")),
        f"Pregunta {question_id}",
        "Tema unico",
        1,
        4,
        False,
    )


def test_quiz_correction_does_not_use_visual_position(client, app, monkeypatch):
    monkeypatch.setattr("quiz_estudio.services.quiz_correction_service.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_id = attempt["question_ids"][0]
        assert attempt["option_order"][str(question_id)][0] == f"{question_id}:option_4"

    client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, [question_id], option_number=4),
        follow_redirects=True,
    )

    assert app.config["fake_repo"].saved_attempts[-1][-1] is False


def test_multiple_question_quiz_records_all_attempts(client, app):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_ids = attempt["question_ids"]

    answers = _quiz_answer_data(attempt_id, question_ids)
    response = client.post("/quiz", data=answers, follow_redirects=True)

    assert response.status_code == 200
    assert b"Resultado: 10/10" in response.data
    assert len(app.config["fake_repo"].saved_attempts) == 10


def test_refreshing_results_does_not_duplicate_attempt_stats(client, app):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_ids = attempt["question_ids"]

    response = client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, question_ids),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert len(app.config["fake_repo"].saved_attempts) == 10

    results_url = response.headers["Location"]
    first_refresh = client.get(results_url)
    second_refresh = client.get(results_url)

    assert first_refresh.status_code == 200
    assert second_refresh.status_code == 200
    assert b"Resultado: 10/10" in second_refresh.data
    assert len(app.config["fake_repo"].saved_attempts) == 10


def test_failed_questions_are_recorded_after_wrong_answer(client, app, monkeypatch):
    monkeypatch.setattr("quiz_estudio.services.quiz_correction_service.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_id = attempt["question_ids"][0]

    client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, [question_id], option_number=4),
        follow_redirects=True,
    )
    response = client.get("/preguntas-falladas")

    assert response.status_code == 200
    assert f"Pregunta {question_id}".encode() in response.data
    assert app.config["fake_repo"].count_failed_questions() == 1


def test_statistics_are_updated_after_answer(client, app):
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id, attempt = _active_attempt(session_data)
        question_id = attempt["question_ids"][0]

    client.post(
        "/quiz",
        data=_quiz_answer_data(attempt_id, [question_id]),
        follow_redirects=True,
    )
    response = client.get("/estadisticas")

    assert response.status_code == 200
    assert app.config["fake_repo"].get_totals() == {"total": 1, "aciertos": 1}


def test_otra_mas_rebuilds_questions_from_ids(client):
    _start_quiz(client, {"quiz_size_mode": "10"})

    response = client.get("/otra-mas", follow_redirects=True)

    assert response.status_code == 200
    assert b"Terminar y corregir" in response.data

    with client.session_transaction() as session_data:
        _, attempt = _active_attempt(session_data)
        assert len(attempt["question_ids"]) == 10
        assert "question_ids" not in session_data
        assert "questions" not in session_data
