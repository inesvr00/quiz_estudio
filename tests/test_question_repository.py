from __future__ import annotations

import pytest

from quiz_estudio import csv_repository
from quiz_estudio.question_repository import (
    CSVQuestionRepository,
    FallbackQuestionRepository,
    SupabaseQuestionRepository,
    get_question_repository,
)


NEW_HEADER = (
    "question_id,enunciado,respuesta_correcta,opcion_falsa_1,opcion_falsa_2,"
    "opcion_falsa_3,explicacion,tema,teoria\n"
)


def test_csv_question_repository_loads_new_format(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + "q_000001,Capital de Francia,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n",
        encoding="utf-8",
    )

    questions = CSVQuestionRepository(csv_path).list_questions()

    assert len(questions) == 1
    assert questions[0]["question_id"] == "q_000001"
    assert questions[0]["respuesta_correcta"] == 1
    assert questions[0]["options"][0]["text"] == "Paris"
    assert questions[0]["options"][0]["is_correct"] is True


def test_csv_question_repository_groups_by_topic(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + "q_000001,Capital de Francia,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n"
        + "q_000002,Dos mas dos,4,3,5,6,Explicacion,Matematicas,0\n",
        encoding="utf-8",
    )

    questions_by_topic = CSVQuestionRepository(csv_path).get_questions_by_topic()

    assert sorted(questions_by_topic) == ["Geografia", "Matematicas"]
    assert questions_by_topic["Geografia"][0]["enunciado"] == "Capital de Francia"


def test_csv_question_repository_filters_by_theory_and_practical(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + "q_000001,Pregunta practica,A,B,C,D,Explicacion,Tema,0\n"
        + "q_000002,Pregunta teorica,A,B,C,D,Explicacion,Tema,1\n",
        encoding="utf-8",
    )
    repository = CSVQuestionRepository(csv_path)
    questions = repository.list_questions()

    theory_questions = repository.filter_by_mode(questions, "theory")
    practical_questions = repository.filter_by_mode(questions, "practical")

    assert [question["enunciado"] for question in theory_questions] == [
        "Pregunta teorica"
    ]
    assert [question["enunciado"] for question in practical_questions] == [
        "Pregunta practica"
    ]


def test_csv_question_repository_gets_question_by_id(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + "q_000010,Capital de Francia,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n",
        encoding="utf-8",
    )

    question = CSVQuestionRepository(csv_path).get_question("q_000010")

    assert question is not None
    assert question["enunciado"] == "Capital de Francia"


def test_csv_wrappers_delegate_to_question_repository(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + "q_000001,Capital de Francia,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("quiz_estudio.question_repository.QUESTIONS_CSV_PATH", csv_path)

    questions = csv_repository.load_questions()
    questions_by_topic = csv_repository.get_questions_by_topic_from_csv()

    assert len(questions) == 1
    assert csv_repository.get_topics(questions) == ["Geografia"]
    assert questions_by_topic["Geografia"][0]["enunciado"] == "Capital de Francia"


def test_repository_detects_duplicate_question_id(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + "q_000001,Pregunta 1,A,B,C,D,Explicacion,Tema,0\n"
        + "q_000001,Pregunta 2,A,B,C,D,Explicacion,Tema,0\n",
        encoding="utf-8",
    )

    try:
        CSVQuestionRepository(csv_path).list_questions()
    except ValueError as exc:
        assert "duplicado" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError por question_id duplicado")


def test_repository_detects_empty_question_id(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + ",Pregunta 1,A,B,C,D,Explicacion,Tema,0\n",
        encoding="utf-8",
    )

    try:
        CSVQuestionRepository(csv_path).list_questions()
    except ValueError as exc:
        assert "question_id esta vacio" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError por question_id vacio")


def test_repository_detects_missing_question_id_column_in_new_csv(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        "enunciado,respuesta_correcta,opcion_falsa_1,opcion_falsa_2,opcion_falsa_3,explicacion,tema,teoria\n"
        "Pregunta 1,A,B,C,D,Explicacion,Tema,0\n",
        encoding="utf-8",
    )

    try:
        CSVQuestionRepository(csv_path).list_questions()
    except ValueError as exc:
        assert "question_id" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError por columna question_id ausente")


def test_changing_question_text_does_not_change_question_id(tmp_path) -> None:
    csv_path = tmp_path / "preguntas_nuevo_formato.csv"
    csv_path.write_text(
        NEW_HEADER
        + "q_000001,Capital de Francia,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n",
        encoding="utf-8",
    )
    before = CSVQuestionRepository(csv_path).get_question("q_000001")

    csv_path.write_text(
        NEW_HEADER
        + "q_000001,Capital de Francia corregida,Paris,Roma,Berlin,Lisboa,Explicacion,Geografia,0\n",
        encoding="utf-8",
    )
    after = CSVQuestionRepository(csv_path).get_question("q_000001")

    assert before["question_id"] == after["question_id"] == "q_000001"
    assert after["enunciado"] == "Capital de Francia corregida"


class FakeSupabaseQuestionClient:
    def __init__(self, questions=None, options=None) -> None:
        self.questions = questions or [supabase_question_row()]
        self.options = options or supabase_option_rows()

    def fetch_questions(self):
        return self.questions

    def fetch_answer_options(self):
        return self.options


class FakeQuestionRepository:
    def __init__(self, questions=None, error: Exception | None = None) -> None:
        self.questions = questions or []
        self.error = error

    def list_questions(self):
        if self.error:
            raise self.error

        return self.questions

    def get_question(self, question_id: str):
        questions_by_id = {
            str(question["question_id"]): question for question in self.list_questions()
        }
        return questions_by_id.get(question_id)

    def get_questions_by_ids(self, question_ids: list[str]):
        questions_by_id = {
            str(question["question_id"]): question for question in self.list_questions()
        }
        return [
            questions_by_id[question_id]
            for question_id in question_ids
            if question_id in questions_by_id
        ]

    def list_topics(self):
        return sorted({question["tema"] for question in self.list_questions()})

    def get_questions_by_topic(self):
        questions_by_topic = {}
        for question in self.list_questions():
            questions_by_topic.setdefault(question["tema"], []).append(question)
        return questions_by_topic

    def filter_by_mode(self, questions, quiz_mode: str):
        if self.error:
            raise self.error

        if quiz_mode == "theory":
            return [
                question
                for question in questions
                if int(question.get("teoria", 0)) == 1
            ]

        if quiz_mode == "practical":
            return [
                question
                for question in questions
                if int(question.get("teoria", 0)) == 0
            ]

        return questions


def repository_question(question_id: str, tema: str = "Tema") -> dict[str, object]:
    return {
        "question_id": question_id,
        "enunciado": f"Pregunta {question_id}",
        "tema": tema,
        "teoria": 0,
    }


def supabase_question_row(
    question_id: str = "q_000001",
    is_active: bool = True,
) -> dict[str, object]:
    return {
        "question_id": question_id,
        "enunciado": "Capital de Francia",
        "explicacion": "Paris es la capital.",
        "tema": "Geografia",
        "teoria": False,
        "is_active": is_active,
    }


def supabase_option_rows(
    question_id: str = "q_000001",
    *,
    correct_count: int = 1,
) -> list[dict[str, object]]:
    return [
        {
            "option_id": f"{question_id}:option_3",
            "question_id": question_id,
            "texto": "Berlin",
            "is_correct": correct_count > 2,
            "option_order": 3,
            "is_active": True,
        },
        {
            "option_id": f"{question_id}:option_1",
            "question_id": question_id,
            "texto": "Paris",
            "is_correct": True,
            "option_order": 1,
            "is_active": True,
        },
        {
            "option_id": f"{question_id}:option_4",
            "question_id": question_id,
            "texto": "Lisboa",
            "is_correct": correct_count > 1,
            "option_order": 4,
            "is_active": True,
        },
        {
            "option_id": f"{question_id}:option_2",
            "question_id": question_id,
            "texto": "Roma",
            "is_correct": False,
            "option_order": 2,
            "is_active": True,
        },
    ]


def test_supabase_repository_rebuilds_valid_question_with_four_options() -> None:
    repository = SupabaseQuestionRepository(FakeSupabaseQuestionClient())

    questions = repository.list_questions()

    assert len(questions) == 1
    assert questions[0]["question_id"] == "q_000001"
    assert questions[0]["enunciado"] == "Capital de Francia"
    assert len(questions[0]["options"]) == 4
    assert questions[0]["options"][0]["option_id"] == "q_000001:option_1"
    assert questions[0]["options"][0]["is_correct"] is True


def test_supabase_repository_ignores_inactive_questions() -> None:
    repository = SupabaseQuestionRepository(
        FakeSupabaseQuestionClient(questions=[supabase_question_row(is_active=False)])
    )

    assert repository.list_questions() == []


def test_supabase_repository_orders_options_by_option_order() -> None:
    repository = SupabaseQuestionRepository(FakeSupabaseQuestionClient())

    question = repository.list_questions()[0]

    assert [option["option_id"] for option in question["options"]] == [
        "q_000001:option_1",
        "q_000001:option_2",
        "q_000001:option_3",
        "q_000001:option_4",
    ]
    assert [option["text"] for option in question["options"]] == [
        "Paris",
        "Roma",
        "Berlin",
        "Lisboa",
    ]


def test_supabase_repository_detects_question_with_less_than_four_options() -> None:
    repository = SupabaseQuestionRepository(
        FakeSupabaseQuestionClient(options=supabase_option_rows()[:3])
    )

    with pytest.raises(ValueError, match="exactamente 4 opciones"):
        repository.list_questions()


def test_supabase_repository_detects_more_than_one_correct_option() -> None:
    repository = SupabaseQuestionRepository(
        FakeSupabaseQuestionClient(options=supabase_option_rows(correct_count=2))
    )

    with pytest.raises(ValueError, match="exactamente una opcion correcta"):
        repository.list_questions()


def test_question_repository_factory_returns_csv_by_default(monkeypatch) -> None:
    monkeypatch.delenv("QUESTION_REPOSITORY_BACKEND", raising=False)

    repository = get_question_repository()

    assert isinstance(repository, CSVQuestionRepository)


def test_question_repository_factory_returns_supabase_when_configured(
    monkeypatch,
) -> None:
    monkeypatch.setenv("QUESTION_REPOSITORY_BACKEND", "supabase")
    monkeypatch.setattr(
        "quiz_estudio.supabase_question_client.SupabaseQuestionClient.from_env",
        lambda: FakeSupabaseQuestionClient(),
    )

    repository = get_question_repository()

    assert isinstance(repository, SupabaseQuestionRepository)


def test_question_repository_factory_returns_fallback_when_configured(
    monkeypatch,
) -> None:
    monkeypatch.setenv("QUESTION_REPOSITORY_BACKEND", "supabase_with_csv_fallback")

    repository = get_question_repository()

    assert isinstance(repository, FallbackQuestionRepository)


def test_question_repository_factory_reports_missing_supabase_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("QUESTION_REPOSITORY_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="Faltan variables de entorno"):
        get_question_repository()


def test_fallback_repository_uses_supabase_when_available() -> None:
    supabase_question = repository_question("q_000001", "Supabase")
    csv_question = repository_question("q_000002", "CSV")
    repository = FallbackQuestionRepository(
        primary_factory=lambda: FakeQuestionRepository([supabase_question]),
        fallback_repository=FakeQuestionRepository([csv_question]),
        primary_label="Supabase",
    )

    assert repository.list_questions() == [supabase_question]
    assert repository.get_question("q_000001") == supabase_question
    assert repository.get_questions_by_ids(["q_000001"]) == [supabase_question]
    assert repository.list_topics() == ["Supabase"]
    assert repository.get_questions_by_topic() == {"Supabase": [supabase_question]}


def test_fallback_repository_uses_csv_when_supabase_fails() -> None:
    csv_question = repository_question("q_000002", "CSV")
    repository = FallbackQuestionRepository(
        primary_factory=lambda: FakeQuestionRepository(
            error=ConnectionError("sin conexion")
        ),
        fallback_repository=FakeQuestionRepository([csv_question]),
        primary_label="Supabase",
    )

    assert repository.list_questions() == [csv_question]
    assert repository.get_question("q_000002") == csv_question
    assert repository.get_questions_by_ids(["q_000002"]) == [csv_question]
    assert repository.list_topics() == ["CSV"]
    assert repository.get_questions_by_topic() == {"CSV": [csv_question]}


def test_fallback_repository_logs_warning_when_supabase_fails(caplog) -> None:
    repository = FallbackQuestionRepository(
        primary_factory=lambda: FakeQuestionRepository(
            error=TimeoutError("timeout")
        ),
        fallback_repository=FakeQuestionRepository([repository_question("q_000002")]),
        primary_label="Supabase",
    )

    with caplog.at_level("WARNING", logger="quiz_estudio.question_repository"):
        repository.list_questions()

    assert "Supabase no disponible" in caplog.text
    assert "Se usa CSV como fallback" in caplog.text


def test_strict_supabase_mode_propagates_errors(monkeypatch) -> None:
    monkeypatch.setenv("QUESTION_REPOSITORY_BACKEND", "supabase")
    monkeypatch.setattr(
        "quiz_estudio.supabase_question_client.SupabaseQuestionClient.from_env",
        lambda: (_ for _ in ()).throw(ConnectionError("sin conexion")),
    )

    with pytest.raises(ConnectionError, match="sin conexion"):
        get_question_repository()


def test_csv_mode_does_not_initialize_supabase(monkeypatch) -> None:
    monkeypatch.setenv("QUESTION_REPOSITORY_BACKEND", "csv")
    monkeypatch.setattr(
        "quiz_estudio.supabase_question_client.SupabaseQuestionClient.from_env",
        lambda: (_ for _ in ()).throw(AssertionError("no debe llamarse")),
    )

    repository = get_question_repository()

    assert isinstance(repository, CSVQuestionRepository)
