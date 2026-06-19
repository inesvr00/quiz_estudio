from __future__ import annotations

from dataclasses import dataclass
from typing import Any


QUESTION_FIELDS = ("enunciado", "explicacion", "tema", "teoria")
OPTION_FIELDS = ("text", "is_correct", "option_order")


@dataclass(frozen=True)
class ParityDifference:
    kind: str
    question_id: str
    detail: str
    option_id: str = ""


@dataclass(frozen=True)
class ParityReport:
    csv_question_count: int
    supabase_question_count: int
    differences: list[ParityDifference]

    @property
    def is_ok(self) -> bool:
        return not self.differences


def compare_question_repositories(
    csv_questions: list[dict[str, Any]],
    supabase_questions: list[dict[str, Any]],
) -> ParityReport:
    csv_by_id = _questions_by_id(csv_questions)
    supabase_by_id = _questions_by_id(supabase_questions)
    csv_ids = set(csv_by_id)
    supabase_ids = set(supabase_by_id)
    differences: list[ParityDifference] = []

    for question_id in sorted(csv_ids - supabase_ids):
        differences.append(
            ParityDifference(
                kind="missing_question_in_supabase",
                question_id=question_id,
                detail="Pregunta presente en CSV pero ausente en Supabase",
            )
        )

    for question_id in sorted(supabase_ids - csv_ids):
        differences.append(
            ParityDifference(
                kind="extra_question_in_supabase",
                question_id=question_id,
                detail="Pregunta presente en Supabase pero ausente en CSV",
            )
        )

    for question_id in sorted(csv_ids & supabase_ids):
        differences.extend(
            _compare_question_fields(
                question_id,
                csv_by_id[question_id],
                supabase_by_id[question_id],
            )
        )
        differences.extend(
            _compare_options(
                question_id,
                csv_by_id[question_id],
                supabase_by_id[question_id],
            )
        )

    return ParityReport(
        csv_question_count=len(csv_questions),
        supabase_question_count=len(supabase_questions),
        differences=differences,
    )


def format_parity_report(report: ParityReport, max_items: int = 50) -> str:
    if report.is_ok:
        return (
            "OK: CSV y Supabase estan sincronizados.\n"
            f"- preguntas CSV: {report.csv_question_count}\n"
            f"- preguntas Supabase: {report.supabase_question_count}"
        )

    counts_by_kind: dict[str, int] = {}
    for difference in report.differences:
        counts_by_kind[difference.kind] = counts_by_kind.get(difference.kind, 0) + 1

    lines = [
        "Diferencias entre CSV y Supabase:",
        f"- preguntas CSV: {report.csv_question_count}",
        f"- preguntas Supabase: {report.supabase_question_count}",
        f"- diferencias: {len(report.differences)}",
    ]

    for kind, count in sorted(counts_by_kind.items()):
        lines.append(f"- {kind}: {count}")

    lines.append("")
    lines.append("Detalle:")
    for difference in report.differences[:max_items]:
        option_label = f" / {difference.option_id}" if difference.option_id else ""
        lines.append(
            f"- {difference.kind}: {difference.question_id}{option_label}: "
            f"{difference.detail}"
        )

    if len(report.differences) > max_items:
        lines.append(f"- ... y {len(report.differences) - max_items} diferencias mas")

    return "\n".join(lines)


def _questions_by_id(questions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(question["question_id"]): question for question in questions}


def _compare_question_fields(
    question_id: str,
    csv_question: dict[str, Any],
    supabase_question: dict[str, Any],
) -> list[ParityDifference]:
    differences = []
    for field in QUESTION_FIELDS:
        csv_value = _normalize_question_value(field, csv_question.get(field))
        supabase_value = _normalize_question_value(field, supabase_question.get(field))
        if csv_value != supabase_value:
            differences.append(
                ParityDifference(
                    kind="changed_question_field",
                    question_id=question_id,
                    detail=(
                        f"{field}: CSV={csv_value!r}; "
                        f"Supabase={supabase_value!r}"
                    ),
                )
            )

    return differences


def _compare_options(
    question_id: str,
    csv_question: dict[str, Any],
    supabase_question: dict[str, Any],
) -> list[ParityDifference]:
    csv_options = _options_by_id(csv_question)
    supabase_options = _options_by_id(supabase_question)
    csv_option_ids = set(csv_options)
    supabase_option_ids = set(supabase_options)
    differences = []

    if len(csv_options) != len(supabase_options):
        differences.append(
            ParityDifference(
                kind="changed_option_count",
                question_id=question_id,
                detail=(
                    f"CSV tiene {len(csv_options)} opciones; "
                    f"Supabase tiene {len(supabase_options)}"
                ),
            )
        )

    for option_id in sorted(csv_option_ids - supabase_option_ids):
        differences.append(
            ParityDifference(
                kind="missing_option_in_supabase",
                question_id=question_id,
                option_id=option_id,
                detail="Opcion presente en CSV pero ausente en Supabase",
            )
        )

    for option_id in sorted(supabase_option_ids - csv_option_ids):
        differences.append(
            ParityDifference(
                kind="extra_option_in_supabase",
                question_id=question_id,
                option_id=option_id,
                detail="Opcion presente en Supabase pero ausente en CSV",
            )
        )

    for option_id in sorted(csv_option_ids & supabase_option_ids):
        csv_option = csv_options[option_id]
        supabase_option = supabase_options[option_id]
        for field in OPTION_FIELDS:
            csv_value = csv_option.get(field)
            supabase_value = supabase_option.get(field)
            if csv_value != supabase_value:
                differences.append(
                    ParityDifference(
                        kind=f"changed_option_{field}",
                        question_id=question_id,
                        option_id=option_id,
                        detail=(
                            f"{field}: CSV={csv_value!r}; "
                            f"Supabase={supabase_value!r}"
                        ),
                    )
                )

    return differences


def _options_by_id(question: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized_options = {}
    for index, option in enumerate(question.get("options", []), start=1):
        option_id = str(option.get("option_id", "")).strip()
        if not option_id:
            option_id = f"{question['question_id']}:option_{index}"

        normalized_options[option_id] = {
            "text": str(option.get("text", "")).strip(),
            "is_correct": bool(option.get("is_correct", False)),
            "option_order": int(option.get("option_order", index)),
        }

    return normalized_options


def _normalize_question_value(field: str, value: Any) -> object:
    if field == "teoria":
        return int(value)

    return str(value or "").strip()
