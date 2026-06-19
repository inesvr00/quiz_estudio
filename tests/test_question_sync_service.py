from __future__ import annotations

from dataclasses import asdict

from quiz_estudio.question_ids import option_id_for
from quiz_estudio.services.question_sync_service import (
    build_sync_records,
    plan_question_sync,
)


def make_question(
    question_id: str = "q_000001",
    enunciado: str = "Enunciado original",
    explicacion: str = "Explicacion original",
    correct: str = "Correcta",
    false_1: str = "Falsa 1",
    false_2: str = "Falsa 2",
    false_3: str = "Falsa 3",
) -> dict[str, object]:
    return {
        "question_id": question_id,
        "csv_id": 0,
        "enunciado": enunciado,
        "respuesta_correcta": 1,
        "explicacion": explicacion,
        "tema": "Tema",
        "teoria": 0,
        "options": [
            {
                "option_id": option_id_for(question_id, 1),
                "text": correct,
                "is_correct": True,
            },
            {
                "option_id": option_id_for(question_id, 2),
                "text": false_1,
                "is_correct": False,
            },
            {
                "option_id": option_id_for(question_id, 3),
                "text": false_2,
                "is_correct": False,
            },
            {
                "option_id": option_id_for(question_id, 4),
                "text": false_3,
                "is_correct": False,
            },
        ],
    }


def records_for(question: dict[str, object]):
    return build_sync_records([question])


def test_new_question_is_planned_as_insert() -> None:
    csv_questions, csv_options = records_for(make_question())

    plan = plan_question_sync(csv_questions, csv_options, [], [])

    assert [question.question_id for question in plan.insert_questions] == ["q_000001"]
    assert len(plan.insert_options) == 4


def test_changed_enunciado_is_planned_as_question_update() -> None:
    old_questions, old_options = records_for(make_question(enunciado="Antes"))
    csv_questions, csv_options = records_for(make_question(enunciado="Despues"))

    plan = plan_question_sync(
        csv_questions,
        csv_options,
        [asdict(question) for question in old_questions],
        [asdict(option) for option in old_options],
    )

    assert [question.question_id for question in plan.update_questions] == ["q_000001"]


def test_changed_explanation_is_planned_as_question_update() -> None:
    old_questions, old_options = records_for(make_question(explicacion="Antes"))
    csv_questions, csv_options = records_for(make_question(explicacion="Despues"))

    plan = plan_question_sync(
        csv_questions,
        csv_options,
        [asdict(question) for question in old_questions],
        [asdict(option) for option in old_options],
    )

    assert [question.question_id for question in plan.update_questions] == ["q_000001"]


def test_changed_option_text_is_planned_as_option_update() -> None:
    old_questions, old_options = records_for(make_question(false_2="Antes"))
    csv_questions, csv_options = records_for(make_question(false_2="Despues"))

    plan = plan_question_sync(
        csv_questions,
        csv_options,
        [asdict(question) for question in old_questions],
        [asdict(option) for option in old_options],
    )

    assert [option.option_id for option in plan.update_options] == [
        "q_000001:option_3"
    ]


def test_remote_question_absent_from_csv_is_planned_as_deactivate() -> None:
    remote_questions, remote_options = records_for(make_question(question_id="q_000999"))

    plan = plan_question_sync(
        [],
        [],
        [asdict(question) for question in remote_questions],
        [asdict(option) for option in remote_options],
    )

    assert [question.question_id for question in plan.deactivate_questions] == [
        "q_000999"
    ]
    assert len(plan.deactivate_options) == 4


def test_changed_enunciado_does_not_change_question_id() -> None:
    old_questions, _ = records_for(make_question(enunciado="Antes"))
    new_questions, _ = records_for(make_question(enunciado="Despues"))

    assert old_questions[0].question_id == new_questions[0].question_id == "q_000001"


def test_changed_option_text_does_not_change_option_id() -> None:
    _, old_options = records_for(make_question(false_1="Antes"))
    _, new_options = records_for(make_question(false_1="Despues"))

    assert old_options[1].option_id == new_options[1].option_id
    assert new_options[1].option_id == "q_000001:option_2"
