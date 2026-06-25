from __future__ import annotations

import logging
import uuid
from typing import Any


logger = logging.getLogger(__name__)


def get_quiz_attempts(session_store) -> dict[str, dict[str, Any]]:
    raw_attempts = session_store.get("quiz_attempts", {})

    if not isinstance(raw_attempts, dict):
        logger.warning("Estado de intentos invalido en la sesion del quiz.")
        return {}

    attempts = {}
    for attempt_id, raw_attempt in raw_attempts.items():
        if isinstance(raw_attempt, dict):
            attempts[str(attempt_id)] = raw_attempt
        else:
            logger.warning("Intento de quiz invalido en la sesion: %s.", attempt_id)

    return attempts


def get_quiz_attempt(session_store, attempt_id: str | None) -> dict[str, Any] | None:
    if not attempt_id:
        return None

    return get_quiz_attempts(session_store).get(str(attempt_id))


def get_attempt_question_ids(attempt: dict[str, Any]) -> list[str]:
    raw_question_ids = attempt.get("question_ids", [])

    if not isinstance(raw_question_ids, list):
        return []

    return [str(question_id) for question_id in raw_question_ids]


def get_quiz_results(session_store) -> dict[str, dict[str, Any]]:
    raw_results = session_store.get("quiz_results", {})

    if not isinstance(raw_results, dict):
        logger.warning("Estado de resultados invalido en la sesion del quiz.")
        return {}

    results = {}
    for attempt_id, raw_result in raw_results.items():
        if isinstance(raw_result, dict):
            results[str(attempt_id)] = raw_result
        else:
            logger.warning("Resultado de quiz invalido en la sesion: %s.", attempt_id)

    return results


def store_quiz_result(
    session_store,
    attempt_id: str,
    answers: dict[str, str | None],
    score: int,
    total: int,
) -> None:
    results = get_quiz_results(session_store)
    results[attempt_id] = {
        "answers": answers,
        "score": score,
        "total": total,
    }
    session_store["quiz_results"] = results


def store_quiz_attempt(
    session_store,
    question_ids: list[str],
    option_order: dict[str, list[str]],
    selected_topics: list[str],
    batch_size: int,
    quiz_mode: str,
    warning: str | None,
) -> str:
    attempt_id = uuid.uuid4().hex
    attempts = get_quiz_attempts(session_store)
    attempts[attempt_id] = {
        "question_ids": question_ids,
        "option_order": option_order,
        "mode": quiz_mode,
        "batch_size": batch_size,
        "selected_topics": selected_topics,
    }

    session_store["quiz_attempts"] = attempts
    session_store["active_attempt_id"] = attempt_id
    session_store.pop("questions", None)

    logger.info(
        "Quiz attempt created: attempt_id=%s question_ids=%s mode=%s batch_size=%s",
        attempt_id,
        question_ids,
        quiz_mode,
        batch_size,
    )

    if warning:
        session_store["quiz_notice"] = warning
    else:
        session_store.pop("quiz_notice", None)

    return attempt_id


def clear_stale_quiz_state(session_store) -> None:
    session_store.pop("questions", None)
