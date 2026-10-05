-- ===========================================================================
-- SmartHR - Applicant / Job Seeker experience
-- ===========================================================================
-- Run AFTER restoring smarthr_backup.sql:
--
--     psql -U postgres -d smarthr -f smarthr_backup.sql
--     psql -U postgres -d smarthr -f migrations/2026-09-14_applicant.sql
--
-- Every statement is idempotent, so re-running it is harmless.
--
-- Design note: nothing here duplicates an existing structure. An applicant is
-- a `users` row (role 5) linked to the `candidates` row that recruitment
-- already uses, so an application an applicant files and an application HR
-- keys in by hand are the same row in the same table, seen from two sides.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. The Applicant role
--
-- roles has no identity/default on id, so the id is given explicitly - 1-4 are
-- already seeded (Admin, HR, Manager, Employee) and are referenced as literal
-- integers throughout the application.
-- ---------------------------------------------------------------------------
INSERT INTO public.roles (id, name)
VALUES (5, 'Applicant')
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 2. candidates.user_id  - the link that makes self-service possible
--
-- This is the only structurally necessary change. `employees.user_id` already
-- ties a staff account to the person; `candidates` had no equivalent, so a
-- signed-in applicant could not be resolved to their own candidate row.
--
-- Nullable, because every candidate HR has ever keyed in by hand has no
-- account and must stay valid. UNIQUE, because one account is one applicant.
-- ---------------------------------------------------------------------------
ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS user_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'candidates_user_id_fkey'
    ) THEN
        ALTER TABLE public.candidates
            ADD CONSTRAINT candidates_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES public.users(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'candidates_user_id_key'
    ) THEN
        ALTER TABLE public.candidates
            ADD CONSTRAINT candidates_user_id_key UNIQUE (user_id);
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 3. candidates.skills - what the applicant says they can do
--
-- The input for AI matching that does not require a language model, and the
-- only source of candidate skills that is never inferred: the applicant types
-- it on their own profile. CV-extracted skills are offered as a suggestion
-- the applicant accepts, never written behind their back.
--
-- Free text (comma-separated) rather than a skills table: SmartHR has no
-- skills taxonomy, and inventing one would be a bigger change than the
-- feature needs.
-- ---------------------------------------------------------------------------
ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS skills TEXT;


-- ---------------------------------------------------------------------------
-- 4. jobs - three public fields an opportunity listing needs
--
-- `jobs` already carries title, department, description, requirements and
-- status, which is most of an opportunity. These three are what a job seeker
-- looks for and the table could not answer.
--
-- employment_type is what separates "Jobs" from "Internships" in the
-- applicant's Opportunities section - one column instead of a second table
-- holding the same shape of row.
-- ---------------------------------------------------------------------------
ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS employment_type VARCHAR(30) NOT NULL DEFAULT 'full_time';

ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS location VARCHAR(150);

ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS deadline DATE;


-- ---------------------------------------------------------------------------
-- 5. trainings - telling a paid course from a free one
--
-- `trainings` already has title, description, provider and duration_hours.
-- category separates "Training Opportunities" from "Free Courses"; url is how
-- an external applicant actually reaches a course, since they cannot be
-- enrolled through employee_trainings (that table keys on employees.id, and
-- an applicant is not an employee).
-- ---------------------------------------------------------------------------
ALTER TABLE public.trainings
    ADD COLUMN IF NOT EXISTS category VARCHAR(30) NOT NULL DEFAULT 'training';

ALTER TABLE public.trainings
    ADD COLUMN IF NOT EXISTS url VARCHAR(500);

COMMIT;
