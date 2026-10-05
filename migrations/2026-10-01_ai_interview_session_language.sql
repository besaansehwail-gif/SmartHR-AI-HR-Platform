ALTER TABLE ai_interview_sessions
ADD COLUMN IF NOT EXISTS language VARCHAR(2)
CHECK (language IS NULL OR language IN ('en', 'ar'));
