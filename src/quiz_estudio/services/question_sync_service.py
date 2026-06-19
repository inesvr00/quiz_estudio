from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

from ..question_ids import option_id_for


@dataclass(frozen=True)
class SyncQuestion:
    question_id: str
    enunciado: str
    explicacion: str
    tema: str
    teoria: bool
    is_active: bool
    content_hash: str


@dataclass(frozen=True)
class SyncAnswerOption:
    option_id: str
    question_id: str
    texto: str
    is_correct: bool
    option_order: int
    is_active: bool
    content_hash: str


@dataclass(frozen=True)
class SyncPlan:
    insert_questions: list[SyncQuestion]
    update_questions: list[SyncQuestion]
    deactivate_questions: list[SyncQuestion]
    insert_options: list[SyncAnswerOption]
    update_options: list[SyncAnswerOption]
    deactivate_options: list[SyncAnswerOption]

    @property
    def has_changes(self) -> bool:
        return any(
            [
                self.insert_questions,
                self.update_questions,
                self.deactivate_questions,
                self.insert_options,
                self.update_options,
                self.deactivate_options,
            ]
        )


def build_sync_records(
    questions: list[dict[str, Any]],
) -> tuple[list[SyncQuestion], list[SyncAnswerOption]]:
    sync_questions = []
    sync_options = []

    for question in questions:
        question_id = str(question["question_id"])
        sync_question = SyncQuestion(
            question_id=question_id,
            enunciado=str(question["enunciado"]),
            explicacion=str(question.get("explicacion", "")),
            tema=str(question["tema"]),
            teoria=bool(int(question.get("teoria", 0))),
            is_active=True,
            content_hash="",
        )
        sync_questions.append(
            replace(sync_question, content_hash=question_content_hash(sync_question))
        )

        iterable_options = [
            (
                index,
                str(option.get("text", "")),
                bool(option.get("is_correct")),
            )
            for index, option in enumerate(question.get("options", []), start=1)
        ]

        for option_order, text, is_correct in iterable_options:
            sync_option = SyncAnswerOption(
                option_id=option_id_for(question_id, option_order),
                question_id=question_id,
                texto=text,
                is_correct=is_correct,
                option_order=option_order,
                is_active=True,
                content_hash="",
            )
            sync_options.append(
                replace(sync_option, content_hash=option_content_hash(sync_option))
            )

    return sync_questions, sync_options


def plan_question_sync(
    csv_questions: list[SyncQuestion],
    csv_options: list[SyncAnswerOption],
    remote_questions: list[dict[str, Any]],
    remote_options: list[dict[str, Any]],
) -> SyncPlan:
    remote_questions_by_id = {
        str(question["question_id"]): question for question in remote_questions
    }
    remote_options_by_id = {
        str(option["option_id"]): option for option in remote_options
    }
    csv_question_ids = {question.question_id for question in csv_questions}
    csv_option_ids = {option.option_id for option in csv_options}

    insert_questions = []
    update_questions = []
    for question in csv_questions:
        remote_question = remote_questions_by_id.get(question.question_id)
        if remote_question is None:
            insert_questions.append(question)
        elif _question_changed(question, remote_question):
            update_questions.append(question)

    deactivate_questions = [
        _remote_question_to_sync(question)
        for question_id, question in remote_questions_by_id.items()
        if question_id not in csv_question_ids and _is_active(question)
    ]

    insert_options = []
    update_options = []
    for option in csv_options:
        remote_option = remote_options_by_id.get(option.option_id)
        if remote_option is None:
            insert_options.append(option)
        elif _option_changed(option, remote_option):
            update_options.append(option)

    deactivate_options = [
        _remote_option_to_sync(option)
        for option_id, option in remote_options_by_id.items()
        if option_id not in csv_option_ids and _is_active(option)
    ]

    return SyncPlan(
        insert_questions=insert_questions,
        update_questions=update_questions,
        deactivate_questions=deactivate_questions,
        insert_options=insert_options,
        update_options=update_options,
        deactivate_options=deactivate_options,
    )


def format_sync_plan(plan: SyncPlan) -> str:
    lines = [
        "Plan de sincronizacion CSV -> Supabase",
        f"- preguntas nuevas: {len(plan.insert_questions)}",
        f"- preguntas a actualizar: {len(plan.update_questions)}",
        f"- preguntas a desactivar: {len(plan.deactivate_questions)}",
        f"- opciones nuevas: {len(plan.insert_options)}",
        f"- opciones a actualizar: {len(plan.update_options)}",
        f"- opciones a desactivar: {len(plan.deactivate_options)}",
    ]

    sections = [
        ("Preguntas nuevas", plan.insert_questions),
        ("Preguntas actualizadas", plan.update_questions),
        ("Preguntas desactivadas", plan.deactivate_questions),
        ("Opciones nuevas", plan.insert_options),
        ("Opciones actualizadas", plan.update_options),
        ("Opciones desactivadas", plan.deactivate_options),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.append("")
        lines.append(f"{title}:")
        for item in items[:20]:
            identifier = getattr(item, "option_id", None) or getattr(
                item, "question_id"
            )
            label = getattr(item, "enunciado", None) or getattr(item, "texto", "")
            lines.append(f"- {identifier}: {label}")
        if len(items) > 20:
            lines.append(f"- ... y {len(items) - 20} mas")

    return "\n".join(lines)


def question_content_hash(question: SyncQuestion) -> str:
    return _stable_hash(
        [
            question.question_id,
            question.enunciado,
            question.explicacion,
            question.tema,
            str(question.teoria),
            str(question.is_active),
        ]
    )


def option_content_hash(option: SyncAnswerOption) -> str:
    return _stable_hash(
        [
            option.option_id,
            option.question_id,
            option.texto,
            str(option.is_correct),
            str(option.option_order),
            str(option.is_active),
        ]
    )


def _stable_hash(values: list[str]) -> str:
    payload = "\x1f".join(values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _question_changed(question: SyncQuestion, remote_question: dict[str, Any]) -> bool:
    return (
        str(remote_question.get("content_hash", "")) != question.content_hash
        or not _is_active(remote_question)
    )


def _option_changed(option: SyncAnswerOption, remote_option: dict[str, Any]) -> bool:
    return (
        str(remote_option.get("content_hash", "")) != option.content_hash
        or not _is_active(remote_option)
    )


def _is_active(row: dict[str, Any]) -> bool:
    return bool(row.get("is_active", True))


def _remote_question_to_sync(question: dict[str, Any]) -> SyncQuestion:
    return SyncQuestion(
        question_id=str(question["question_id"]),
        enunciado=str(question.get("enunciado", "")),
        explicacion=str(question.get("explicacion", "")),
        tema=str(question.get("tema", "")),
        teoria=bool(question.get("teoria", False)),
        is_active=False,
        content_hash=str(question.get("content_hash", "")),
    )


def _remote_option_to_sync(option: dict[str, Any]) -> SyncAnswerOption:
    return SyncAnswerOption(
        option_id=str(option["option_id"]),
        question_id=str(option.get("question_id", "")),
        texto=str(option.get("texto", "")),
        is_correct=bool(option.get("is_correct", False)),
        option_order=int(option.get("option_order", 0)),
        is_active=False,
        content_hash=str(option.get("content_hash", "")),
    )
