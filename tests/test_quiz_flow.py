from __future__ import annotations

import pytest

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


def _reverse_shuffle(values):
    values.reverse()


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


def test_quiz_options_are_shuffled_when_attempt_is_created(client, monkeypatch):
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.random.shuffle", _reverse_shuffle)

    response = _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        question_id = str(session_data["question_ids"][0])
        assert session_data["option_orders"][question_id] == [
            f"{question_id}:option_4",
            f"{question_id}:option_3",
            f"{question_id}:option_2",
            f"{question_id}:option_1",
        ]

    assert response.data.find(b"1. D") < response.data.find(b"4. A")


def test_quiz_option_order_stays_stable_within_attempt(client, monkeypatch):
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        initial_orders = dict(session_data["option_orders"])

    response = client.get("/quiz")

    with client.session_transaction() as session_data:
        assert session_data["option_orders"] == initial_orders

    assert response.data.find(b"1. D") < response.data.find(b"4. A")


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
        assert all(int(question_id.removeprefix("q_")) % 2 == 0 for question_id in session_data["question_ids"])

    assert b"Terminar y corregir" in response.data


def test_quiz_practical_mode_filters_questions(client):
    response = _start_quiz(
        client,
        {"quiz_size_mode": "10", "quiz_mode": "practical"},
    )

    with client.session_transaction() as session_data:
        assert session_data["quiz_mode"] == "practical"
        assert len(session_data["question_ids"]) == 10
        assert all(int(question_id.removeprefix("q_")) % 2 == 1 for question_id in session_data["question_ids"])

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
        attempt_id = session_data["current_attempt_id"]

    answers = {
        f"pregunta_{question_id}": f"{question_id}:option_1"
        for question_id in question_ids
    }
    answers["attempt_id"] = attempt_id
    answers["question_id"] = question_ids
    response = client.post("/quiz", data=answers, follow_redirects=True)

    assert response.status_code == 200
    assert b"Correcci" in response.data
    assert b"Resultado:" in response.data
    for question_id in question_ids:
        assert f"Pregunta {question_id}".encode() in response.data


def test_correct_option_scores_even_when_visual_position_changes(client, app, monkeypatch):
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        question_id = session_data["question_ids"][0]
        attempt_id = session_data["current_attempt_id"]

    response = client.post(
        f"/quiz?attempt_id={attempt_id}",
        data={
            "attempt_id": attempt_id,
            "question_id": [question_id],
            f"pregunta_{question_id}": f"{question_id}:option_1",
        },
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
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        question_id = session_data["question_ids"][0]
        attempt_id = session_data["current_attempt_id"]

    response = client.post(
        f"/quiz?attempt_id={attempt_id}",
        data={
            "attempt_id": attempt_id,
            "question_id": [question_id],
            f"pregunta_{question_id}": f"{question_id}:option_4",
        },
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
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        question_id = session_data["question_ids"][0]
        attempt_id = session_data["current_attempt_id"]
        assert session_data["option_orders"][str(question_id)][0] == f"{question_id}:option_4"

    client.post(
        f"/quiz?attempt_id={attempt_id}",
        data={
            "attempt_id": attempt_id,
            "question_id": [question_id],
            f"pregunta_{question_id}": f"{question_id}:option_4",
        },
        follow_redirects=True,
    )

    assert app.config["fake_repo"].saved_attempts[-1][-1] is False


def test_multiple_question_quiz_records_all_attempts(client, app):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        question_ids = session_data["question_ids"]
        attempt_id = session_data["current_attempt_id"]

    answers = {
        f"pregunta_{question_id}": f"{question_id}:option_1"
        for question_id in question_ids
    }
    answers["attempt_id"] = attempt_id
    answers["question_id"] = question_ids
    response = client.post("/quiz", data=answers, follow_redirects=True)

    assert response.status_code == 200
    assert b"Resultado: 10/10" in response.data
    assert len(app.config["fake_repo"].saved_attempts) == 10


def test_post_quiz_does_not_select_new_questions(client, monkeypatch):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        question_ids = session_data["question_ids"]
        attempt_id = session_data["current_attempt_id"]

    def fail_selection(*_args, **_kwargs):
        raise AssertionError("POST /quiz must not select a new quiz")

    monkeypatch.setattr("quiz_estudio.blueprints.quiz.select_quiz_questions", fail_selection)

    response = client.post(
        f"/quiz?attempt_id={attempt_id}",
        data={
            "attempt_id": attempt_id,
            "question_id": question_ids,
            **{
                f"pregunta_{question_id}": f"{question_id}:option_1"
                for question_id in question_ids
            },
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Resultado: 10/10" in response.data


def test_missing_attempt_does_not_select_new_questions(client, monkeypatch):
    def fail_selection(*_args, **_kwargs):
        raise AssertionError("Missing attempts must fail safely")

    monkeypatch.setattr("quiz_estudio.blueprints.quiz.select_quiz_questions", fail_selection)

    response = client.post(
        "/quiz?attempt_id=missing",
        data={
            "attempt_id": "missing",
            "question_id": ["q_000001"],
            "pregunta_q_000001": "q_000001:option_1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"intento" in response.data.lower()


def test_two_tabs_corrects_original_attempt_after_second_attempt(client, app):
    _start_quiz(client, {"quiz_size_mode": "10"})
    with client.session_transaction() as session_data:
        attempt_a = session_data["current_attempt_id"]
        question_ids_a = list(session_data["question_ids"])

    _start_quiz(client, {"quiz_size_mode": "1"})
    with client.session_transaction() as session_data:
        attempt_b = session_data["current_attempt_id"]
        question_ids_b = list(session_data["question_ids"])

    assert attempt_a != attempt_b
    assert question_ids_a != question_ids_b

    response = client.post(
        f"/quiz?attempt_id={attempt_a}",
        data={
            "attempt_id": attempt_a,
            "question_id": question_ids_a,
            **{
                f"pregunta_{question_id}": f"{question_id}:option_1"
                for question_id in question_ids_a
            },
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert len(app.config["fake_repo"].saved_attempts) == 10
    saved_ids = [f"q_{attempt[0]:06d}" for attempt in app.config["fake_repo"].saved_attempts]
    assert saved_ids == question_ids_a
    assert saved_ids != question_ids_b


def test_refreshing_first_attempt_after_opening_second_keeps_first_attempt(client):
    _start_quiz(client, {"quiz_size_mode": "10"})
    with client.session_transaction() as session_data:
        attempt_a = session_data["current_attempt_id"]
        question_ids_a = list(session_data["question_ids"])

    _start_quiz(client, {"quiz_size_mode": "1"})

    response = client.get(f"/quiz?attempt_id={attempt_a}")

    assert response.status_code == 200
    for question_id in question_ids_a:
        assert f"Pregunta {question_id}".encode() in response.data


def test_attempt_questions_keep_original_order_when_repository_returns_unordered(client, monkeypatch):
    _start_quiz(client, {"quiz_size_mode": "10"})

    with client.session_transaction() as session_data:
        attempt_id = session_data["current_attempt_id"]
        question_ids = list(session_data["question_ids"])

    monkeypatch.setattr(
        "quiz_estudio.blueprints.quiz.load_questions",
        lambda: list(reversed(_build_questions())),
    )

    response = client.get(f"/quiz?attempt_id={attempt_id}")
    positions = [response.data.find(f"Pregunta {question_id}".encode()) for question_id in question_ids]

    assert all(position >= 0 for position in positions)
    assert positions == sorted(positions)


def test_invalid_option_order_falls_back_safely(client):
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id = session_data["current_attempt_id"]
        question_id = session_data["question_ids"][0]
        session_data["quiz_attempts"][attempt_id]["option_orders"][question_id] = ["invalid-option"]

    response = client.get(f"/quiz?attempt_id={attempt_id}")

    assert response.status_code == 200
    assert b"Pregunta" in response.data
    assert b"Terminar y corregir" in response.data


def test_refreshing_results_does_not_duplicate_statistics(client, app):
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        attempt_id = session_data["current_attempt_id"]
        question_id = session_data["question_ids"][0]

    response = client.post(
        f"/quiz?attempt_id={attempt_id}",
        data={
            "attempt_id": attempt_id,
            "question_id": [question_id],
            f"pregunta_{question_id}": f"{question_id}:option_1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    response = client.get(f"/quiz?attempt_id={attempt_id}&results=1")

    assert response.status_code == 200
    assert len(app.config["fake_repo"].saved_attempts) == 1


def test_session_limits_stored_attempts(client):
    attempt_ids = []

    for _ in range(12):
        _start_quiz(client, {"quiz_size_mode": "1"})
        with client.session_transaction() as session_data:
            attempt_ids.append(session_data["current_attempt_id"])

    with client.session_transaction() as session_data:
        stored_attempt_ids = list(session_data["quiz_attempts"])

    assert len(stored_attempt_ids) <= 5
    assert set(stored_attempt_ids) == set(attempt_ids[-5:])
    assert session_data["quiz_attempt_order"] == attempt_ids[-5:]


def test_failed_questions_are_recorded_after_wrong_answer(client, app, monkeypatch):
    monkeypatch.setattr("quiz_estudio.blueprints.quiz.random.shuffle", _reverse_shuffle)
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        question_id = session_data["question_ids"][0]
        attempt_id = session_data["current_attempt_id"]

    client.post(
        f"/quiz?attempt_id={attempt_id}",
        data={
            "attempt_id": attempt_id,
            "question_id": [question_id],
            f"pregunta_{question_id}": f"{question_id}:option_4",
        },
        follow_redirects=True,
    )
    response = client.get("/preguntas-falladas")

    assert response.status_code == 200
    assert f"Pregunta {question_id}".encode() in response.data
    assert app.config["fake_repo"].count_failed_questions() == 1


def test_statistics_are_updated_after_answer(client, app):
    _start_quiz(client, {"quiz_size_mode": "1"})

    with client.session_transaction() as session_data:
        question_id = session_data["question_ids"][0]
        attempt_id = session_data["current_attempt_id"]

    client.post(
        f"/quiz?attempt_id={attempt_id}",
        data={
            "attempt_id": attempt_id,
            "question_id": [question_id],
            f"pregunta_{question_id}": f"{question_id}:option_1",
        },
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
        assert len(session_data["question_ids"]) == 10
        assert "questions" not in session_data
