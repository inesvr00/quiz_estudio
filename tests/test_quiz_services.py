from __future__ import annotations

from werkzeug.datastructures import MultiDict

from quiz_estudio.services.quiz_correction_service import get_attempt_questions
from quiz_estudio.services.quiz_form_service import parse_batch_size
from quiz_estudio.services.quiz_session_service import get_quiz_attempt, store_quiz_attempt


def _question(question_id: str) -> dict[str, object]:
    return {
        "question_id": question_id,
        "csv_id": int(question_id.removeprefix("q_")),
        "enunciado": f"Pregunta {question_id}",
        "respuesta_correcta": 1,
        "explicacion": "Explicacion",
        "tema": "Tema unico",
        "teoria": 0,
        "options": [
            {
                "option_id": f"{question_id}:option_1",
                "text": "A",
                "is_correct": True,
            },
            {
                "option_id": f"{question_id}:option_2",
                "text": "B",
                "is_correct": False,
            },
            {
                "option_id": f"{question_id}:option_3",
                "text": "C",
                "is_correct": False,
            },
            {
                "option_id": f"{question_id}:option_4",
                "text": "D",
                "is_correct": False,
            },
        ],
    }


def test_store_and_get_quiz_attempt() -> None:
    session_store = {}

    attempt_id = store_quiz_attempt(
        session_store,
        ["q_000001"],
        {"q_000001": ["q_000001:option_1"]},
        ["Tema unico"],
        10,
        "standard",
        None,
    )

    assert session_store["active_attempt_id"] == attempt_id
    assert get_quiz_attempt(session_store, attempt_id) == {
        "question_ids": ["q_000001"],
        "option_order": {"q_000001": ["q_000001:option_1"]},
        "mode": "standard",
        "batch_size": 10,
        "selected_topics": ["Tema unico"],
    }


def test_get_attempt_questions_preserves_attempt_order(monkeypatch) -> None:
    questions = [_question("q_000001"), _question("q_000002"), _question("q_000003")]
    attempt = {
        "question_ids": ["q_000003", "q_000001", "q_000002"],
        "option_order": {},
    }

    def reversed_get_questions_by_ids(all_questions, question_ids):
        by_id = {question["question_id"]: question for question in all_questions}
        return [by_id[question_id] for question_id in reversed(question_ids)]

    monkeypatch.setattr(
        "quiz_estudio.services.quiz_correction_service.get_questions_by_ids",
        reversed_get_questions_by_ids,
    )

    ordered_questions = get_attempt_questions(questions, attempt)

    assert [question["question_id"] for question in ordered_questions] == [
        "q_000003",
        "q_000001",
        "q_000002",
    ]


def test_get_attempt_questions_falls_back_for_invalid_option_order() -> None:
    question = _question("q_000001")
    attempt = {
        "question_ids": ["q_000001"],
        "option_order": {"q_000001": "q_000001:option_1"},
    }

    questions = get_attempt_questions([question], attempt)

    assert [option["option_id"] for option in questions[0]["display_options"]] == [
        "q_000001:option_1",
        "q_000001:option_2",
        "q_000001:option_3",
        "q_000001:option_4",
    ]


def test_parse_batch_size_accepts_custom_positive_integer() -> None:
    form = MultiDict(
        {
            "quiz_size_mode": "custom",
            "custom_num_preguntas": "35",
        }
    )

    assert parse_batch_size(form) == (35, None)
