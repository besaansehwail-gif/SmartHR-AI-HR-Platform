-- Add Arabic variants without changing question ids, English text, or
-- parent_question_id relationships. Re-running is safe.
ALTER TABLE interview_questions
    ADD COLUMN IF NOT EXISTS question_text_ar TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'interview_questions_text_ar_check'
          AND conrelid = 'interview_questions'::regclass
    ) THEN
        ALTER TABLE interview_questions
            ADD CONSTRAINT interview_questions_text_ar_check
            CHECK (question_text_ar IS NULL
                OR char_length(btrim(question_text_ar)) BETWEEN 5 AND 500);
    END IF;
END
$$;

UPDATE interview_questions
SET question_text_ar = CASE question_text
    WHEN 'Tell me about yourself.'
        THEN 'حدّثني عن نفسك.'
    WHEN 'Tell me about a challenging situation you faced and how you handled it.'
        THEN 'صف موقفًا صعبًا واجهته وكيف تعاملت معه.'
    WHEN 'How do you work within a team?'
        THEN 'كيف تعمل ضمن فريق؟'
    WHEN 'What are your main strengths?'
        THEN 'ما أبرز نقاط قوتك؟'
    WHEN 'What would you do if you disagreed with a teammate about an important decision?'
        THEN 'كيف ستتعامل مع اختلافك مع أحد أعضاء الفريق حول قرار مهم؟'
    WHEN 'Describe a technical problem you solved recently. What was your approach?'
        THEN 'صف مشكلة تقنية حللتها مؤخرًا، وما النهج الذي اتبعته؟'
    WHEN 'How do you go about learning a new tool or technology?'
        THEN 'كيف تتعلم أداة أو تقنية جديدة؟'
    WHEN 'Tell me about a time you made a mistake at work. What did you learn from it?'
        THEN 'حدثني عن خطأ ارتكبته في العمل، وما الذي تعلمته منه؟'
    WHEN 'How would you prioritise your work if you had several urgent tasks with the same deadline?'
        THEN 'كيف تحدد أولويات عملك إذا كان لديك عدة مهام عاجلة بالموعد النهائي نفسه؟'
    WHEN 'Why are you interested in this role?'
        THEN 'ما الذي يجذبك إلى هذه الوظيفة؟'
    WHEN 'Where would you like to grow professionally over the next few years?'
        THEN 'ما الجوانب المهنية التي تود تطويرها خلال السنوات القليلة المقبلة؟'
    WHEN 'Tell me about a time you received difficult feedback. How did you respond?'
        THEN 'حدثني عن موقف تلقيت فيه ملاحظات صعبة، وكيف استجبت لها؟'
    WHEN 'What led you to choose that path?'
        THEN 'ما الذي دفعك إلى اختيار هذا المسار؟'
    WHEN 'What would you do differently if it happened again?'
        THEN 'ما الذي ستفعله بشكل مختلف إذا تكرر الموقف؟'
    ELSE question_text_ar
END
WHERE question_text_ar IS NULL
  AND question_text IN (
    'Tell me about yourself.',
    'Tell me about a challenging situation you faced and how you handled it.',
    'How do you work within a team?',
    'What are your main strengths?',
    'What would you do if you disagreed with a teammate about an important decision?',
    'Describe a technical problem you solved recently. What was your approach?',
    'How do you go about learning a new tool or technology?',
    'Tell me about a time you made a mistake at work. What did you learn from it?',
    'How would you prioritise your work if you had several urgent tasks with the same deadline?',
    'Why are you interested in this role?',
    'Where would you like to grow professionally over the next few years?',
    'Tell me about a time you received difficult feedback. How did you respond?',
    'What led you to choose that path?',
    'What would you do differently if it happened again?'
  );
