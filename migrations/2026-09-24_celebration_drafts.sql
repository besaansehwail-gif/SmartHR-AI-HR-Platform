-- ===========================================================================
-- SmartHR - AI Employee Celebration drafts
-- ===========================================================================
-- Run AFTER the base dump and the earlier migrations:
--
--     psql -U postgres -d smarthr -f smarthr_backup.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-14_applicant.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-15_ai_interview.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-16_social_hub.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-17_social_moderation.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-20_interview_video_analysis.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-21_interview_question_bank.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-24_celebration_drafts.sql
--
-- Every statement is idempotent, so re-running it is harmless.
--
-- `psql` is not on PATH on the development machine. The file is applied
-- through the application's own engine instead - psycopg 3 runs a
-- multi-statement file:
--
--     from pathlib import Path
--     from app.database import engine
--     sql = Path("migrations/2026-09-24_celebration_drafts.sql").read_text(encoding="utf-8")
--     with engine.begin() as conn:
--         conn.exec_driver_sql(sql)
--
-- ---------------------------------------------------------------------------
-- WHY A TABLE AT ALL
-- ---------------------------------------------------------------------------
-- The celebration workflow used to hand its result straight back in the HTTP
-- response HR had asked for. A scheduled job has nobody to answer, so what it
-- produces has to outlive the run - and neither existing table can hold it:
--
--   * `social_posts` is the feed. A draft that nobody has approved is not a
--     post, and putting one there would mean every feed, profile and comment
--     query had to learn a new status to keep it hidden.
--   * `notifications` has one line of text and no room for the occasion, the
--     years, the review verdict or the reviewer's reason.
--
-- ---------------------------------------------------------------------------
-- WHY THE UNIQUE CONSTRAINT IS THE DUPLICATE PROTECTION
-- ---------------------------------------------------------------------------
-- A daily job gets run twice: by a retry, by an operator checking it works,
-- by a machine that woke up late. `UNIQUE (employee_id, occasion,
-- occasion_date)` means the second run *cannot* create a second draft for the
-- same person's same anniversary - Postgres refuses it, rather than a handler
-- remembering to check. That is the rule `social_reactions` already follows
-- with UNIQUE (post_id, user_id).
--
-- The service checks for the row first as well, so a second run costs no
-- model calls; the constraint is what holds when two runs race.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS celebration_drafts (
    id                  SERIAL PRIMARY KEY,

    -- The person being celebrated. CASCADE because a draft about somebody who
    -- has been deleted is not a record worth keeping.
    employee_id         INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

    -- What the Occasion Agent decided, and the date it decided it for. The
    -- date is stored rather than derived so the uniqueness of "this person's
    -- 2026 anniversary" is a fact in the row.
    occasion            VARCHAR(30) NOT NULL,
    occasion_date       DATE NOT NULL,
    years               INTEGER,

    -- What the Message Agent wrote and what the Review Agent decided. The
    -- message is kept even when it was rejected: "the AI tried and could not
    -- produce something publishable" is a different thing from "nothing
    -- happened", and HR should be able to tell them apart.
    message             TEXT,
    review_approved     BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason       TEXT,
    review_suggestions  TEXT,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    error_code          VARCHAR(40),

    -- pending | posted | dismissed | no_occasion
    --
    -- `no_occasion` is recorded rather than skipped so the same day is not
    -- re-asked of the model on every run.
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',

    -- Set only when HR posts it. The FK is the evidence that what reached the
    -- feed went through the ordinary post path.
    post_id             INTEGER REFERENCES social_posts(id) ON DELETE SET NULL,
    decided_by          INTEGER REFERENCES users(id),
    decided_at          TIMESTAMP,

    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_celebration_drafts_employee_occasion
        UNIQUE (employee_id, occasion, occasion_date)
);

-- HR's queue is "everything still waiting", newest first.
CREATE INDEX IF NOT EXISTS ix_celebration_drafts_status
    ON celebration_drafts (status, created_at DESC);
