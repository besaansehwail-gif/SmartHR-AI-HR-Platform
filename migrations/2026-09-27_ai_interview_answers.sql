-- AI Interview (rebuild) - Phase 7: the applicant's answers, and their analysis.
--
-- Until Phase 7 an answer lived only in the agent worker's memory. Now every
-- ACCEPTED answer is sent by the worker to
--
--     POST /ai-interview/agent/answers     (agent token, room-bound)
--
-- and stored here against the voice session (ai_interview_sessions) and the
-- interview it belongs to. The worker never writes to the database itself;
-- the backend resolves room -> session -> interview and checks the question
-- against the Question Bank plan before anything is written.
--
-- Two tables, on purpose:
--
--   ai_interview_answers           what was asked and what was said - written
--                                  once, never updated (the record)
--   ai_interview_answer_analyses   GPT-4o's structured reading of one answer -
--                                  may be re-run (derived, replaceable)
--
-- `question_text` is copied from the Question Bank at write time: a bank
-- question can be edited later, and the record must keep the words the
-- applicant actually heard. The text comes from the bank row, never from the
-- worker or the model.
--
-- Duplicate protection is a constraint: UNIQUE (session_id, sequence). The
-- worker numbers answers in the order they were committed, so a retried
-- request for the same answer names the same sequence and cannot create a
-- second row.
--
-- Nothing here holds a score, a match or a decision. The analysis JSON has no
-- field for one (see app/ai/interview_analysis.py).
--
-- Apply after 2026-09-26_ai_interview_sessions.sql:
--
--     psql -U postgres -d smarthr -f migrations/2026-09-27_ai_interview_answers.sql
--
-- or, where psql is not on PATH:
--
--     from pathlib import Path
--     from app.database import engine
--     sql = Path("migrations/2026-09-27_ai_interview_answers.sql").read_text(encoding="utf-8")
--     with engine.begin() as conn:
--         conn.exec_driver_sql(sql)
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS ai_interview_answers (
    id               SERIAL PRIMARY KEY,
    session_id       INTEGER      NOT NULL REFERENCES ai_interview_sessions(id) ON DELETE CASCADE,
    interview_id     INTEGER      NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    question_id      INTEGER      NOT NULL REFERENCES interview_questions(id),
    question_number  SMALLINT     NOT NULL,
    question_text    VARCHAR(500) NOT NULL,
    sequence         SMALLINT     NOT NULL,
    answer_kind      VARCHAR(10)  NOT NULL,
    transcript       TEXT         NOT NULL,
    word_count       INTEGER      NOT NULL,
    answered_at      TIMESTAMP    NOT NULL,
    created_at       TIMESTAMP    NOT NULL,
    CONSTRAINT ai_interview_answers_sequence_unique UNIQUE (session_id, sequence),
    CONSTRAINT ai_interview_answers_number_check CHECK (question_number BETWEEN 1 AND 20),
    CONSTRAINT ai_interview_answers_sequence_check CHECK (sequence BETWEEN 1 AND 200),
    CONSTRAINT ai_interview_answers_kind_check CHECK (answer_kind IN ('answer', 'short', 'filler')),
    CONSTRAINT ai_interview_answers_transcript_check CHECK (length(btrim(transcript)) > 0),
    CONSTRAINT ai_interview_answers_words_check CHECK (word_count >= 0)
);

CREATE INDEX IF NOT EXISTS ix_ai_interview_answers_interview
    ON ai_interview_answers (interview_id, session_id, sequence);

CREATE TABLE IF NOT EXISTS ai_interview_answer_analyses (
    id           SERIAL PRIMARY KEY,
    answer_id    INTEGER     NOT NULL UNIQUE REFERENCES ai_interview_answers(id) ON DELETE CASCADE,
    status       VARCHAR(20) NOT NULL,
    analysis     JSONB       NULL,
    error_code   VARCHAR(40) NULL,
    model        VARCHAR(80) NULL,
    analysed_at  TIMESTAMP   NOT NULL,
    CONSTRAINT ai_interview_answer_analyses_status_check CHECK (status IN ('completed', 'failed')),
    CONSTRAINT ai_interview_answer_analyses_payload_check CHECK ((status = 'completed') = (analysis IS NOT NULL))
);
