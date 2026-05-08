from __future__ import annotations

import random
from typing import Any

from ..db import get_attempt_repository


def get_seen_question_ids() -> set[int]:
    return get_attempt_repository().get_seen_question_ids()


def weighted_sample_without_replacement(
    items: list[dict[str, Any]],
    weights: list[float],
    k: int,
) -> list[dict[str, Any]]:
    if len(items) != len(weights):
        raise ValueError("items y weights deben tener la misma longitud.")

    sample_size = min(k, len(items))
    remaining_items = list(items)
    remaining_weights = list(weights)
    selected_items = []

    for _ in range(sample_size):
        selected_index = random.choices(
            range(len(remaining_items)),
            weights=remaining_weights,
            k=1,
        )[0]
        selected_items.append(remaining_items.pop(selected_index))
        remaining_weights.pop(selected_index)

    return selected_items


def select_quiz_questions(
    questions: list[dict[str, Any]],
    selected_topics: list[str],
    batch_size: int,
) -> list[dict[str, Any]]:
    filtered_questions = [
        question
        for question in questions
        if question["tema"] in selected_topics
    ]

    if not filtered_questions:
        return []

    seen_question_ids = get_seen_question_ids()
    weights = [
        2.0 if question["csv_id"] not in seen_question_ids else 1.0
        for question in filtered_questions
    ]

    return weighted_sample_without_replacement(
        filtered_questions,
        weights,
        batch_size,
    )
