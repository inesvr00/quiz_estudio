from __future__ import annotations

from ..config import ALLOWED_BATCH_SIZES
from .quiz_service import QUIZ_MODE_PRACTICAL, QUIZ_MODE_STANDARD, QUIZ_MODE_THEORY


def parse_batch_size(form) -> tuple[int, str | None]:
    mode = (form.get("quiz_size_mode") or form.get("batch_size") or "10").strip()
    custom_raw = (form.get("custom_num_preguntas") or form.get("custom_batch_size") or "").strip()

    if mode == "custom":
        try:
            custom_size = int(custom_raw)
        except ValueError:
            return 10, "El número personalizado debe ser un entero mayor que 0."

        if custom_size <= 0:
            return 10, "El número personalizado debe ser mayor que 0."

        return custom_size, None

    try:
        selected_size = int(mode)
    except ValueError:
        selected_size = 10

    if selected_size not in ALLOWED_BATCH_SIZES:
        selected_size = 10

    return selected_size, None


def parse_quiz_mode(form) -> str:
    mode = (form.get("quiz_mode") or QUIZ_MODE_STANDARD).strip()

    if mode not in {QUIZ_MODE_STANDARD, QUIZ_MODE_THEORY, QUIZ_MODE_PRACTICAL}:
        return QUIZ_MODE_STANDARD

    return mode
