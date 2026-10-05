-- AI Interview (rebuild) - Phase 4: which interview a voice room belongs to.
--
-- The browser asks for a voice session FOR ONE INTERVIEW (`interviews.id`).
-- The backend checks that the interview's application belongs to the signed-in
-- applicant, mints a random LiveKit room, and records the binding here. The
-- agent worker later presents a token for that room and the backend resolves
--
--     room -> interview -> application -> job
--
-- from THIS table - never from anything the browser or LiveKit metadata says.
--
-- One row per voice session, nothing else: no transcript, no answers, no
-- scores. Job/application/interview data is NOT copied here; it stays in the
-- tables that own it and is re-read (and re-authorised) on every lookup.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS ai_interview_sessions (
    id            SERIAL PRIMARY KEY,
    room_name     VARCHAR(64) NOT NULL UNIQUE,
    interview_id  INTEGER     NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    candidate_id  INTEGER     NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at    TIMESTAMP   NOT NULL,
    CONSTRAINT ai_interview_sessions_expiry_check CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS ix_ai_interview_sessions_interview
    ON ai_interview_sessions (interview_id);
