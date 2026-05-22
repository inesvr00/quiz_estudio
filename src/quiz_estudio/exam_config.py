from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SIMULACRO_TOTAL_QUESTIONS = 210
NETAS_FALLADAS_DIVISOR = 3
THEME_JITTER_INTENSITY = 0.12


@dataclass(frozen=True)
class ExamBlock:
    name: str
    base_questions: int
    topics: tuple[str, ...]


EXAM_BLOCKS: tuple[ExamBlock, ...] = (
    ExamBlock(
        name="Bloque 1",
        base_questions=70,
        topics=(
            "Mecánica y Ondas",
            "Electromagnetismo",
            "Termodinámica",
            "Física Molecular",
            "Semiconductores",
            "Óptica",
        ),
    ),
    ExamBlock(
        name="Bloque 2",
        base_questions=105,
        topics=(
            "Cuántica",
            "Nuclear",
            "Interacción Radiación Materia",
            "Aceleradores Lineales y Radioterapia",
            "Desintegraciones",
            "Detectores",
            "Física de Partículas",
            "Protección radiológica",
            "Relatividad",
        ),
    ),
    ExamBlock(
        name="Bloque 3",
        base_questions=25,
        topics=(
            "Matemáticas",
            "Informática",
            "Electrónica",
            "Estadística y probabilidad",
        ),
    ),
    ExamBlock(
        name="Bloque 4",
        base_questions=10,
        topics=(
            "Matemáticas",
            "Probabilidad",
        ),
    ),
)


def get_exam_topics() -> list[str]:
    topics: list[str] = []

    for block in EXAM_BLOCKS:
        for topic in block.topics:
            if topic not in topics:
                topics.append(topic)

    return topics
