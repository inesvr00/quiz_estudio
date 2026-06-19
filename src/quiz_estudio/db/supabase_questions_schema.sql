-- Banco de preguntas sincronizado desde CSV.
--
-- El CSV preguntas_nuevo_formato.csv sigue siendo la fuente de verdad.
-- Estas tablas almacenan una copia sincronizada del banco de preguntas en
-- Supabase para consulta futura.
--
-- Este script es aditivo y no debe tocar las tablas de estadisticas/intentos
-- existentes, por ejemplo:
-- - question_attempts
-- - simulacro_attempts
-- - exam_attempts
-- - exam_attempt_topic_stats

CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    enunciado TEXT NOT NULL,
    explicacion TEXT,
    tema TEXT NOT NULL,
    teoria BOOLEAN NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS answer_options (
    option_id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE RESTRICT,
    texto TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    option_order INTEGER NOT NULL CHECK (option_order BETWEEN 1 AND 4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (question_id, option_order)
);

CREATE INDEX IF NOT EXISTS idx_answer_options_question_id
ON answer_options (question_id);

CREATE INDEX IF NOT EXISTS idx_questions_tema
ON questions (tema);

CREATE INDEX IF NOT EXISTS idx_questions_is_active
ON questions (is_active);
