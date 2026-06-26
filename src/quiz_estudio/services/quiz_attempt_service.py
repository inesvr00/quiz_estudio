from __future__ import annotations

from collections.abc import MutableMapping
from secrets import token_urlsafe
from typing import Any, Callable

from ..csv_repository import get_questions_by_ids
from ..question_repository import get_question_id
from .quiz_correction_service import build_option_orders, normalize_option_orders


MAX_STORED_ATTEMPTS = 5


def create_attempt(
    session_data: MutableMapping[str, Any],
    selected_questions: list[dict[str, object]],
    selected_topics: list[str],
    batch_size: int,
    quiz_mode: str,
    warning: str | None,
    shuffle_options: Callable[[list[str]], None],
) -> str:
    attempt_id = token_urlsafe(12)
    question_ids = [get_question_id(question) for question in selected_questions]
    option_orders = build_option_orders(selected_questions, shuffle_options)
    attempts = _get_attempts(session_data)
    attempts[attempt_id] = {
        "question_ids": question_ids,
        "option_orders": option_orders,
        "selected_topics": selected_topics,
        "batch_size": batch_size,
        "quiz_mode": quiz_mode,
        "answers": {},
        "stats_saved": False,
    }

    attempt_order = _get_attempt_order(session_data)
    attempt_order = [stored_attempt_id for stored_attempt_id in attempt_order if stored_attempt_id in attempts]
    attempt_order.append(attempt_id)
    _limit_attempts(attempts, attempt_order)
    session_data["quiz_attempts"] = attempts
    session_data["quiz_attempt_order"] = attempt_order
    session_data["current_attempt_id"] = attempt_id
    _sync_legacy_quiz_state(
        session_data,
        question_ids,
        option_orders,
        selected_topics,
        batch_size,
        quiz_mode,
        warning,
    )
    session_data.pop("questions", None)

    return attempt_id


def get_attempt(session_data: MutableMapping[str, Any], attempt_id: str | None) -> dict[str, Any] | None:
    if not attempt_id:
        attempt_id = session_data.get("current_attempt_id")

    attempts = _get_attempts(session_data)
    attempt = attempts.get(str(attempt_id)) if attempt_id else None
    if attempt is None:
        return None

    attempt["attempt_id"] = str(attempt_id)
    return attempt


def get_attempt_id_from_request(args, form) -> str | None:
    return args.get("attempt_id") or form.get("attempt_id")


def get_attempt_questions(
    all_questions: list[dict[str, Any]],
    attempt: dict[str, Any],
) -> list[dict[str, Any]]:
    question_ids = get_attempt_question_ids(attempt)
    return get_questions_by_ids(all_questions, question_ids)


def get_attempt_question_ids(attempt: dict[str, Any]) -> list[str]:
    raw_question_ids = attempt.get("question_ids", [])
    if not isinstance(raw_question_ids, list):
        return []
    return [str(question_id) for question_id in raw_question_ids]


def get_attempt_option_orders(attempt: dict[str, Any]) -> dict[str, list[str]]:
    return normalize_option_orders(attempt.get("option_orders", {}))


def validate_submitted_question_ids(attempt: dict[str, Any], submitted_question_ids: list[str]) -> bool:
    return [str(question_id) for question_id in submitted_question_ids] == get_attempt_question_ids(attempt)


def store_answers(
    session_data: MutableMapping[str, Any],
    attempt: dict[str, Any],
    answers: dict[str, str | None],
) -> None:
    attempt_id = attempt["attempt_id"]
    attempts = _get_attempts(session_data)
    if attempt_id not in attempts:
        return

    attempts[attempt_id]["answers"] = answers
    session_data["quiz_attempts"] = attempts


def mark_stats_saved(session_data: MutableMapping[str, Any], attempt: dict[str, Any]) -> None:
    attempt_id = attempt["attempt_id"]
    attempts = _get_attempts(session_data)
    if attempt_id not in attempts:
        return

    attempts[attempt_id]["stats_saved"] = True
    session_data["quiz_attempts"] = attempts


def stats_were_saved(attempt: dict[str, Any]) -> bool:
    return bool(attempt.get("stats_saved"))


def clear_stale_quiz_state(session_data: MutableMapping[str, Any]) -> None:
    session_data.pop("questions", None)


def clear_missing_attempt_notice(session_data: MutableMapping[str, Any]) -> str | None:
    return session_data.pop("quiz_error", None)


def set_missing_attempt_notice(session_data: MutableMapping[str, Any], message: str) -> None:
    session_data["quiz_error"] = message


def copy_attempt_settings_to_legacy_state(session_data: MutableMapping[str, Any], attempt: dict[str, Any]) -> None:
    _sync_legacy_quiz_state(
        session_data,
        get_attempt_question_ids(attempt),
        get_attempt_option_orders(attempt),
        list(attempt.get("selected_topics", [])),
        int(attempt.get("batch_size", 10)),
        str(attempt.get("quiz_mode", "standard")),
        None,
    )


def _get_attempts(session_data: MutableMapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_attempts = session_data.get("quiz_attempts", {})
    if not isinstance(raw_attempts, dict):
        return {}
    return dict(raw_attempts)


def _get_attempt_order(session_data: MutableMapping[str, Any]) -> list[str]:
    raw_attempt_order = session_data.get("quiz_attempt_order", [])
    if not isinstance(raw_attempt_order, list):
        return []
    return [str(attempt_id) for attempt_id in raw_attempt_order]


def _limit_attempts(attempts: dict[str, dict[str, Any]], attempt_order: list[str]) -> None:
    while len(attempt_order) > MAX_STORED_ATTEMPTS:
        oldest_attempt_id = attempt_order.pop(0)
        attempts.pop(oldest_attempt_id, None)

    for attempt_id in list(attempts):
        if attempt_id not in attempt_order:
            attempts.pop(attempt_id, None)


def _sync_legacy_quiz_state(
    session_data: MutableMapping[str, Any],
    question_ids: list[str],
    option_orders: dict[str, list[str]],
    selected_topics: list[str],
    batch_size: int,
    quiz_mode: str,
    warning: str | None,
) -> None:
    session_data["question_ids"] = question_ids
    session_data["option_orders"] = option_orders
    session_data["selected_topics"] = selected_topics
    session_data["batch_size"] = batch_size
    session_data["quiz_mode"] = quiz_mode

    if warning:
        session_data["quiz_notice"] = warning
    else:
        session_data.pop("quiz_notice", None)
