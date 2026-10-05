-- ===========================================================================
-- SmartHR - Social Hub
-- ===========================================================================
-- Run AFTER the base dump and the two earlier migrations:
--
--     psql -U postgres -d smarthr -f smarthr_backup.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-14_applicant.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-15_ai_interview.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-16_social_hub.sql
--
-- Every statement is idempotent, so re-running it is harmless.
--
-- ---------------------------------------------------------------------------
-- What is NOT here, and why
-- ---------------------------------------------------------------------------
-- Nothing in this file alters, renames or drops an existing table or column.
-- In particular:
--
--   * `employees` was NOT given a bio, an avatar or a skills column. Those are
--     things a person writes about themselves for a social surface, not HR
--     master data, and `employees` is read by nine other features. They live
--     on `social_profiles` instead.
--
--   * `notifications` is reused exactly as it is. It already has (user_id,
--     title, message, type, is_read) and GET /notifications/ is already scoped
--     to the caller, so a Social Hub notification is an ordinary notifications
--     row whose `type` begins with `social_`. It therefore appears in the
--     existing bell and the existing per-role notification pages without any
--     of them being taught about this feature. A second notification system
--     would have been a second inbox for the same person.
--
-- ---------------------------------------------------------------------------
-- Why every table keys on users.id and not employees.id
-- ---------------------------------------------------------------------------
-- `employees.user_id` is NULLABLE, and in this database most rows on both
-- sides are not always linked. Keying the Social Hub on employees.id would
-- prevent accounts without a linked employee row from using it because
-- `get_current_employee` would 404 before any handler ran.
--
-- The participant in a social network is the signed-in *account*: it is what
-- posts, what reacts and what receives a message. `users.id` is NOT NULL and
-- always exists. The person's name, department and position are still read
-- from the linked `employees` row on every response, through the same
-- `describe_user()` / `employee_identity()` helpers the rest of SmartHR uses,
-- falling back to the email address exactly as `notifications` and
-- `audit_logs` already do.
--
-- Applicants are kept out by RBAC (`require_staff`, roles 1-4) on the router,
-- not by the choice of key - role 5 is refused before a query runs.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. social_profiles - what a person chooses to say about themselves
--
-- 1:1 with a users row (UNIQUE user_id). Everything on it is written by the
-- person themselves and is presentational; nothing here is HR master data and
-- nothing here is read by any HR screen.
--
-- `skills` is free text typed by the employee, deliberately the same shape as
-- `candidates.skills` on the applicant side, so a later AI People Search has
-- one column to read that contains only words a human actually wrote.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_profiles (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL UNIQUE REFERENCES users(id),
    headline    VARCHAR(150),
    bio         TEXT,
    skills      TEXT,
    interests   TEXT,
    location    VARCHAR(150),
    avatar_path TEXT,
    cover_path  TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- 2. social_posts
--
-- `department_id` is the author's department **as it was when they posted**,
-- resolved once from their employees row rather than joined on every read.
-- Two reasons: the "My Department" feed filter would otherwise be a three-hop
-- join (posts -> users -> employees -> departments) on every row, and a post
-- written for a department should stay in that department's feed after its
-- author transfers. NULL is legitimate - an account with no employees row has
-- no department, and its posts simply never match a department filter.
--
-- `audience` is 'company' or 'department'. Neither is a permission: a
-- department post is a feed filter, not a restriction, which is exactly how
-- the UI words it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_posts (
    id             SERIAL PRIMARY KEY,
    author_user_id INTEGER NOT NULL REFERENCES users(id),
    content        TEXT NOT NULL,
    image_path     TEXT,
    audience       VARCHAR(20) NOT NULL DEFAULT 'company',
    department_id  INTEGER REFERENCES departments(id),
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    edited_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_social_posts_created_at
    ON social_posts (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_social_posts_author
    ON social_posts (author_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_social_posts_department
    ON social_posts (department_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 3. social_comments
--
-- ON DELETE CASCADE: deleting your own post takes its comments and reactions
-- with it. Every cascade in this file is contained inside the Social Hub -
-- none of them reaches an HR table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_comments (
    id             SERIAL PRIMARY KEY,
    post_id        INTEGER NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    author_user_id INTEGER NOT NULL REFERENCES users(id),
    content        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_social_comments_post
    ON social_comments (post_id, created_at);

-- ---------------------------------------------------------------------------
-- 4. social_reactions
--
-- UNIQUE (post_id, user_id) is what makes a like idempotent in the database
-- rather than in a handler: a second POST /like cannot create a second row, so
-- a like count is a COUNT and can never be inflated by a repeated request.
--
-- `kind` exists and defaults to 'like'. V1 writes nothing else - the column is
-- there so a richer reaction set later is a new value, not a new table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_reactions (
    id         SERIAL PRIMARY KEY,
    post_id    INTEGER NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    kind       VARCHAR(20) NOT NULL DEFAULT 'like',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_social_reactions_post_user UNIQUE (post_id, user_id)
);

-- ---------------------------------------------------------------------------
-- 5. social_stories
--
-- `expires_at` is STORED rather than derived from created_at + 24h. Expiry is
-- a fact about the story: storing it makes the active-story query one indexed
-- comparison instead of arithmetic on every row, and means changing the window
-- later cannot retroactively resurrect or kill stories published under the old
-- one.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_stories (
    id             SERIAL PRIMARY KEY,
    author_user_id INTEGER NOT NULL REFERENCES users(id),
    caption        TEXT,
    image_path     TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at     TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_social_stories_expires
    ON social_stories (expires_at DESC);

-- ---------------------------------------------------------------------------
-- 6. social_story_views - seen / unseen
--
-- UNIQUE (story_id, viewer_user_id): viewing twice is still one view, so the
-- seen state cannot drift and a viewer count cannot double.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_story_views (
    id             SERIAL PRIMARY KEY,
    story_id       INTEGER NOT NULL REFERENCES social_stories(id) ON DELETE CASCADE,
    viewer_user_id INTEGER NOT NULL REFERENCES users(id),
    viewed_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_social_story_views UNIQUE (story_id, viewer_user_id)
);

-- ---------------------------------------------------------------------------
-- 7. social_connections
--
-- Two constraints do the work that would otherwise be handler logic a race
-- could beat:
--
--   * the CHECK makes a self-connection impossible to store at all;
--   * the unique index on (LEAST, GREATEST) makes ONE row per pair of people,
--     in either direction, ever. "A already asked B" and "B already asked A"
--     are the same row, so a duplicate active request is refused by the
--     database rather than by a check the handler has to remember.
--
-- A rejected request therefore does not leave a tombstone blocking the pair
-- forever: re-requesting updates that same row back to 'pending', swapping
-- requester and receiver if it is the other person asking this time.
--
-- Statuses: pending | accepted | rejected. Disconnecting deletes the row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_connections (
    id                 SERIAL PRIMARY KEY,
    requester_user_id  INTEGER NOT NULL REFERENCES users(id),
    receiver_user_id   INTEGER NOT NULL REFERENCES users(id),
    status             VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT social_connections_not_self
        CHECK (requester_user_id <> receiver_user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_social_connections_pair
    ON social_connections (
        LEAST(requester_user_id, receiver_user_id),
        GREATEST(requester_user_id, receiver_user_id)
    );

CREATE INDEX IF NOT EXISTS ix_social_connections_receiver
    ON social_connections (receiver_user_id, status);
CREATE INDEX IF NOT EXISTS ix_social_connections_requester
    ON social_connections (requester_user_id, status);

-- ---------------------------------------------------------------------------
-- 8-10. Messaging
--
-- Three tables rather than one social_messages(from, to, body), for a reason
-- that is not speculative: an unread count needs a per-participant read
-- marker, and a two-column from/to table has nowhere to put one.
-- `social_conversation_members.last_read_at` is that marker - and the
-- membership row is also what authorises a read. A conversation is readable if
-- and only if the caller has a row in it, which is a WHERE clause rather than
-- a permission check a handler could forget.
--
-- The same shape is what leaves room for group conversations later without a
-- migration: nothing here says a conversation has exactly two members.
--
-- `last_message_at` is denormalised onto the conversation so the conversation
-- list sorts without a correlated subquery per row. It is written in the same
-- transaction as the message it describes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_conversations (
    id                 SERIAL PRIMARY KEY,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_message_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS social_conversation_members (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES social_conversations(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    joined_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_read_at    TIMESTAMP,
    CONSTRAINT uq_social_conversation_member UNIQUE (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_social_conversation_members_user
    ON social_conversation_members (user_id);

CREATE TABLE IF NOT EXISTS social_messages (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES social_conversations(id) ON DELETE CASCADE,
    sender_user_id  INTEGER NOT NULL REFERENCES users(id),
    body            TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_social_messages_conversation
    ON social_messages (conversation_id, created_at);

COMMIT;
