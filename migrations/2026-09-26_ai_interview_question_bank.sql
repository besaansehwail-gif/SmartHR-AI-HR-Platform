-- ===========================================================================
-- SmartHR - AI Interview Question Bank (the rebuilt AI Interview, Phase 3)
-- ===========================================================================
-- Run AFTER the base dump and the earlier migrations. Every statement is
-- idempotent, so re-running it is harmless.
--
-- `psql` is not on PATH on the development machine; apply it through the
-- application's own engine:
--
--     from pathlib import Path
--     from app.database import engine
--     sql = Path("migrations/2026-09-26_ai_interview_question_bank.sql").read_text(encoding="utf-8")
--     with engine.begin() as conn:
--         conn.exec_driver_sql(sql)
--
-- The controlled test questions are NOT inserted here - they are data, not
-- schema: `python -m scripts.seed_interview_questions` adds them.
--
-- ---------------------------------------------------------------------------
-- WHY THESE COLUMNS
-- ---------------------------------------------------------------------------
--   question_text      what is asked, spoken word for word by the interviewer
--   category           general | behavioral | technical | situational | role_specific
--   difficulty         easy | medium | hard
--   question_type      main | follow_up   (lowercase tokens, like jobs.status
--                      and applications.status)
--   evaluation_focus   what a good answer shows - for HR and for the later
--                      analysis phase; never spoken, never sent to the applicant
--   parent_question_id a follow_up belongs to exactly one main question. NULL
--                      for main questions - enforced by a CHECK, not by hope.
--   position           the deterministic order the controller asks main
--                      questions in (then id, so ties are still stable)
--   is_active          deactivated questions are never selected. There is no
--                      delete: later phases will store answers against
--                      questions, and a deleted question would orphan them.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS interview_questions (
    id                  SERIAL PRIMARY KEY,
    question_text       TEXT NOT NULL,
    question_text_ar    TEXT,
    category            VARCHAR(30) NOT NULL DEFAULT 'general',
    difficulty          VARCHAR(20) NOT NULL DEFAULT 'medium',
    question_type       VARCHAR(20) NOT NULL DEFAULT 'main',
    evaluation_focus    TEXT,
    parent_question_id  INTEGER REFERENCES interview_questions(id),
    position            INTEGER NOT NULL DEFAULT 0,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT interview_questions_text_check
        CHECK (char_length(btrim(question_text)) BETWEEN 5 AND 500),
    CONSTRAINT interview_questions_text_ar_check
        CHECK (question_text_ar IS NULL
            OR char_length(btrim(question_text_ar)) BETWEEN 5 AND 500),
    CONSTRAINT interview_questions_category_check
        CHECK (category IN ('general', 'behavioral', 'technical', 'situational', 'role_specific')),
    CONSTRAINT interview_questions_difficulty_check
        CHECK (difficulty IN ('easy', 'medium', 'hard')),
    CONSTRAINT interview_questions_type_check
        CHECK (question_type IN ('main', 'follow_up')),
    CONSTRAINT interview_questions_parent_check
        CHECK ((question_type = 'main' AND parent_question_id IS NULL)
            OR (question_type = 'follow_up' AND parent_question_id IS NOT NULL)),
    CONSTRAINT interview_questions_position_check
        CHECK (position >= 0)
);

-- The interview plan query: active main questions in (position, id) order.
CREATE INDEX IF NOT EXISTS ix_interview_questions_plan
    ON interview_questions (question_type, is_active, position, id);
