from __future__ import annotations

import random
from itertools import groupby

from quiz_estudio.exam_config import EXAM_BLOCKS, DEFAULT_SIMULACRO_TOTAL_QUESTIONS, get_exam_topics
from quiz_estudio.services import stats_service
from quiz_estudio.services.simulacro_service import (
    build_corrected_questions,
    calculate_simulacro_summary,
    generate_simulacro_plan,
    scale_block_sizes,
)


def _build_questions(per_theme: int = 40) -> list[dict[str, object]]:
    questions: list[dict[str, object]] = []
    csv_id = 0

    for topic in get_exam_topics():
        for index in range(per_theme):
            questions.append(
                {
                    "csv_id": csv_id,
                    "enunciado": f"Pregunta {csv_id}",
                    "opcion_1": "A",
                    "opcion_2": "B",
                    "opcion_3": "C",
                    "opcion_4": "D",
                    "respuesta_correcta": 1,
                    "explicacion": "Explicacion",
                    "tema": topic,
                }
            )
            csv_id += 1

    return questions


def test_scale_block_sizes_preserves_total_and_reference_distribution() -> None:
    assert scale_block_sizes(DEFAULT_SIMULACRO_TOTAL_QUESTIONS) == [70, 105, 25, 10]
    assert sum(scale_block_sizes(137)) == 137


def test_generate_simulacro_plan_groups_questions_by_block_and_theme() -> None:
    plan = generate_simulacro_plan(_build_questions(), DEFAULT_SIMULACRO_TOTAL_QUESTIONS, rng=random.Random(7))

    assert len(plan["questions"]) == DEFAULT_SIMULACRO_TOTAL_QUESTIONS
    assert [len(block["questions"]) for block in plan["blocks"]] == [70, 105, 25, 10]

    for block in plan["blocks"]:
        themes = [question["tema"] for question in block["questions"]]
        last_theme = None
        seen_themes: set[str] = set()

        for theme in themes:
            if theme != last_theme:
                assert theme not in seen_themes
                seen_themes.add(theme)
                last_theme = theme


def test_all_available_topics_are_included_when_possible() -> None:
    # Build enough questions per topic so every configured topic can appear.
    questions = _build_questions(per_theme=30)
    plan = generate_simulacro_plan(questions, DEFAULT_SIMULACRO_TOTAL_QUESTIONS, rng=random.Random(1))

    for block, block_def in zip(plan["blocks"], EXAM_BLOCKS):
        block_topics = set(block_def.topics)
        present_topics = {q["tema"] for q in block["questions"]}

        # Every topic that has available questions in the block must appear.
        assert block_topics.issubset(present_topics)


def test_topic_without_questions_not_forced() -> None:
    # Build questions but remove all of 'Óptica' to simulate missing topic
    questions = _build_questions(per_theme=30)
    questions = [q for q in questions if q['tema'] != 'Óptica']

    plan = generate_simulacro_plan(questions, DEFAULT_SIMULACRO_TOTAL_QUESTIONS, rng=random.Random(2))

    # Ensure that 'Óptica' does not appear
    all_themes = {q['tema'] for q in plan['questions']}
    assert 'Óptica' not in all_themes


def test_block_with_less_slots_than_topics_chooses_distinct_themes() -> None:
    # Force a very small simulacro so block1 will have fewer slots than topics
    questions = _build_questions(per_theme=5)
    # choose total small so block1 size maybe less than its topics count
    small_total = 6
    plan = generate_simulacro_plan(questions, small_total, rng=random.Random(3))

    block1 = plan['blocks'][0]
    block1_target = block1['target']
    themes = [q['tema'] for q in block1['questions']]

    # Number of distinct themes should be as large as possible but <= block1_target
    assert len(set(themes)) <= block1_target
    # No duplicate questions
    ids = [q['csv_id'] for q in plan['questions']]
    assert len(ids) == len(set(ids))


def test_block_order_is_preserved() -> None:
    questions = _build_questions(per_theme=30)
    plan = generate_simulacro_plan(questions, DEFAULT_SIMULACRO_TOTAL_QUESTIONS, rng=random.Random(4))

    # Each block is emitted in the configured order and carries the configured target.
    assert [block['name'] for block in plan['blocks']] == [block.name for block in EXAM_BLOCKS]
    assert [block['target'] for block in plan['blocks']] == [70, 105, 25, 10]


def test_no_duplicate_questions_in_simulacro() -> None:
    questions = _build_questions(per_theme=30)
    plan = generate_simulacro_plan(questions, DEFAULT_SIMULACRO_TOTAL_QUESTIONS, rng=random.Random(5))

    ids = [q['csv_id'] for q in plan['questions']]
    assert len(ids) == len(set(ids))


def test_calculate_simulacro_summary_counts_unanswered_and_netas() -> None:
    corrected_questions = build_corrected_questions(
        [
            {
                "csv_id": 1,
                "enunciado": "P1",
                "opcion_1": "A",
                "opcion_2": "B",
                "opcion_3": "C",
                "opcion_4": "D",
                "respuesta_correcta": 1,
                "explicacion": "E",
                "tema": "Mecánica y Ondas",
            },
            {
                "csv_id": 2,
                "enunciado": "P2",
                "opcion_1": "A",
                "opcion_2": "B",
                "opcion_3": "C",
                "opcion_4": "D",
                "respuesta_correcta": 2,
                "explicacion": "E",
                "tema": "Mecánica y Ondas",
            },
            {
                "csv_id": 3,
                "enunciado": "P3",
                "opcion_1": "A",
                "opcion_2": "B",
                "opcion_3": "C",
                "opcion_4": "D",
                "respuesta_correcta": 3,
                "explicacion": "E",
                "tema": "Electromagnetismo",
            },
        ],
        {
            "pregunta_1": "1",
            "pregunta_2": "1",
        },
    )

    summary = calculate_simulacro_summary(corrected_questions)

    assert summary["acertadas"] == 1
    assert summary["falladas"] == 1
    assert summary["sin_responder"] == 1
    assert summary["netas"] == 0.67


def test_simulacro_topic_stats_show_dash_for_missing_topic() -> None:
    corrected_questions = build_corrected_questions(
        [
            {
                "csv_id": 1,
                "enunciado": "P1",
                "opcion_1": "A",
                "opcion_2": "B",
                "opcion_3": "C",
                "opcion_4": "D",
                "respuesta_correcta": 1,
                "explicacion": "E",
                "tema": "Mecánica y Ondas",
            }
        ],
        {"pregunta_1": "1"},
    )

    summary = calculate_simulacro_summary(corrected_questions)
    topic_rows = {row["tema"]: row for row in summary["topics"]}

    assert topic_rows["Mecánica y Ondas"]["porcentaje"] == 100.0
    assert topic_rows["Electromagnetismo"]["porcentaje"] is None
    assert topic_rows["Electromagnetismo"]["total"] == 0


def test_normal_save_attempts_still_ignores_unanswered_questions(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeRepository:
        def save_attempts(self, attempts):
            captured["attempts"] = list(attempts)

        def save_simulacro_attempts(self, attempts):
            captured["simulacro_attempts"] = list(attempts)

    monkeypatch.setattr(stats_service, "get_attempt_repository", lambda: FakeRepository())

    stats_service.save_attempts(
        [
            {
                "csv_id": 1,
                "enunciado": "P1",
                "tema": "Mecánica y Ondas",
                "respuesta_correcta": 1,
                "respuesta_usuario": 1,
                "es_correcta": True,
            },
            {
                "csv_id": 2,
                "enunciado": "P2",
                "tema": "Electromagnetismo",
                "respuesta_correcta": 2,
                "respuesta_usuario": None,
                "es_correcta": False,
            },
        ]
    )

    assert len(captured["attempts"]) == 1
    assert "simulacro_attempts" not in captured
