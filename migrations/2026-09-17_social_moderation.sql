-- ===========================================================================
-- SmartHR - AI Moderation V1 for the Social Hub
-- ===========================================================================
-- Run AFTER the base dump and the earlier migrations:
--
--     psql -U postgres -d smarthr -f smarthr_backup.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-14_applicant.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-15_ai_interview.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-16_social_hub.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-17_social_moderation.sql
--
-- Every statement is idempotent, so re-running it is harmless.
--
-- ---------------------------------------------------------------------------
-- What this adds, and why each piece exists
-- ---------------------------------------------------------------------------
-- One new table and one new column on each of the three content tables.
-- Nothing existing is altered, renamed or dropped.
--
--   * `social_moderation_reviews` is the moderation RECORD: what the model
--     decided, what a human then decided, and when. One row per piece of
--     content, enforced by a UNIQUE index rather than by a check in the
--     service, so a double submission cannot produce two review queues for
--     one post.
--
--   * `moderation_status` on `social_posts`, `social_comments` and
--     `social_stories` is the VISIBILITY flag the feed filters on.
--
-- Those two could have been one. They are not, deliberately:
--
--   The feed reads ten posts per page and already runs three grouped count
--   queries for them. Deriving visibility from the review table instead would
--   mean a correlated NOT EXISTS against social_moderation_reviews on every
--   row of every feed, comment list and story bar - for a column whose value
--   is 'published' for virtually every row. A single indexed varchar on the
--   content row answers it with no join at all.
--
--   The cost of that choice is two places holding one truth, so every write
--   that changes either goes through `social_moderation_service.apply_*`,
--   which sets both inside one transaction. That is the same arrangement
--   `leave_requests.approved_by` already has with `status`.
--
-- ---------------------------------------------------------------------------
-- What is deliberately NOT here
-- ---------------------------------------------------------------------------
--   * No `categories` child table. A V1 taxonomy of eight fixed tokens stored
--     as a short comma-separated list is read whole, never joined and never
--     aggregated; a table would be three more queries for no question anybody
--     asks. `candidates.skills` already sets this precedent.
--
--   * No copy of the content. The review row references (content_type,
--     content_id) and the words stay in the one table that owns them, so
--     editing a post cannot leave a stale duplicate in the moderation queue.
--
--   * No new audit table. Moderation events are written to `audit_logs`
--     through the existing `record_audit()`.
--
--   * Nothing is ever DELETEd by moderation. "Removed" is a status, so the
--     moderation history stays readable after the fact.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The moderation record
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_moderation_reviews (
    id                  SERIAL PRIMARY KEY,

    -- What was moderated. 'post' | 'comment' | 'story'.
    content_type        VARCHAR(20)  NOT NULL,
    content_id          INTEGER      NOT NULL,

    -- Denormalised from the content row on purpose: it is the one field the
    -- queue always shows, it can never change for a given piece of content,
    -- and carrying it means listing the queue does not have to join three
    -- different content tables to find out who wrote each item.
    author_user_id      INTEGER      NOT NULL REFERENCES users(id),

    -- What the model said. 'allow' | 'flag' | 'unavailable'.
    -- 'unavailable' is a real outcome, not an error swallowed: it means
    -- moderation was required and could not run, which is why the content is
    -- in the queue.
    ai_decision         VARCHAR(20)  NOT NULL,

    -- Comma-separated tokens from the fixed taxonomy. Empty for 'allow' and
    -- for 'unavailable'.
    categories          TEXT,

    -- 'low' | 'medium' | 'high'. NULL when the model did not run.
    severity            VARCHAR(10),

    -- 0.0 - 1.0. NULL when the model did not run.
    confidence          DOUBLE PRECISION,

    -- The model's short explanation, or the reason moderation could not run.
    -- Internal: never sent to the content's author.
    reason              TEXT,

    -- Why the model could not be used, when ai_decision = 'unavailable':
    -- 'llm_not_configured' | 'llm_error' | 'invalid_output' | 'disabled'.
    error_code          VARCHAR(40),

    -- The queue state. 'pending' | 'approved' | 'removed'.
    status              VARCHAR(20)  NOT NULL DEFAULT 'pending',

    -- The human decision. NULL until somebody reviews it.
    reviewer_user_id    INTEGER      REFERENCES users(id),
    reviewer_decision   VARCHAR(20),
    reviewer_note       TEXT,
    reviewed_at         TIMESTAMP,

    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One review per piece of content. This is what makes re-submitting, or a
-- retried request, incapable of producing two queue entries for one post -
-- refused by Postgres rather than by a check that could lose a race.
CREATE UNIQUE INDEX IF NOT EXISTS social_moderation_reviews_content_key
    ON social_moderation_reviews (content_type, content_id);

-- The queue is always read status-first, newest first.
CREATE INDEX IF NOT EXISTS social_moderation_reviews_status_idx
    ON social_moderation_reviews (status, created_at DESC);


-- ---------------------------------------------------------------------------
-- 2. Visibility on the three content tables
-- ---------------------------------------------------------------------------
-- 'published' | 'pending_review' | 'removed'.
--
-- DEFAULT 'published' and NOT NULL, so every row that existed before this
-- migration - and every row written by any code path that has not been taught
-- about moderation - is visible exactly as it was. Moderation can only ever
-- take visibility away from content it has actually looked at.

ALTER TABLE social_posts
    ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) NOT NULL DEFAULT 'published';

ALTER TABLE social_comments
    ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) NOT NULL DEFAULT 'published';

ALTER TABLE social_stories
    ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) NOT NULL DEFAULT 'published';

-- The feed filters on this column on every read.
CREATE INDEX IF NOT EXISTS social_posts_moderation_idx
    ON social_posts (moderation_status);

CREATE INDEX IF NOT EXISTS social_comments_moderation_idx
    ON social_comments (moderation_status);

CREATE INDEX IF NOT EXISTS social_stories_moderation_idx
    ON social_stories (moderation_status);
