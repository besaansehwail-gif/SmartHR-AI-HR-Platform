-- ===========================================================================
-- SmartHR - employee celebration dates (AI Employee Celebration, extended)
-- ===========================================================================
-- Run AFTER the base dump and the earlier migrations, in particular
-- 2026-09-24_celebration_drafts.sql.
--
-- Every statement is idempotent, so re-running it is harmless. `psql` is not
-- on PATH on the development machine; apply it through the app's engine:
--
--     from pathlib import Path
--     from app.database import engine
--     sql = Path("migrations/2026-09-27_employee_celebration_dates.sql").read_text(encoding="utf-8")
--     with engine.begin() as conn:
--         conn.exec_driver_sql(sql)
--
-- ---------------------------------------------------------------------------
-- WHY
-- ---------------------------------------------------------------------------
-- The celebration workflow could evidence only one occasion - the work
-- anniversary, from `employees.hire_date` - because the schema held no other
-- date about a person. These five columns are the records the other occasions
-- are detected from:
--
--     birth_date        -> birthday          (every year, on the month/day)
--     hire_date         -> work_anniversary  (unchanged, every year)
--     promotion_date    -> promotion         (once, on that date)
--     graduation_date   -> graduation        (once, on that date)
--     wedding_date      -> wedding           (once, on that date)
--     new_baby_date     -> new_baby          (once, on that date)
--
-- Named `<thing>_date` to match the existing `hire_date`. All NULLABLE with
-- no default: an existing employee has none of these recorded, and NULL means
-- exactly that - the workflow then reports the occasion as not recorded for
-- that person rather than guessing. No existing row is changed.
--
-- They live on `employees` (not a new table) because each is one current
-- fact about one person, like `hire_date`; a promotion history or a second
-- wedding is out of scope, and `position_id` still carries the current role.
-- `celebration_drafts.occasion` is VARCHAR(30) with no CHECK, so the new
-- occasion tokens need no change there, and its UNIQUE (employee_id,
-- occasion, occasion_date) already de-duplicates every new occasion.
-- ===========================================================================

ALTER TABLE employees ADD COLUMN IF NOT EXISTS birth_date      DATE;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS promotion_date  DATE;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS graduation_date DATE;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS wedding_date    DATE;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS new_baby_date   DATE;
