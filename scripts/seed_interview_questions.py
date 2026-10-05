"""Seed the AI Interview Question Bank with a small, controlled TEST set.

    venv\\Scripts\\python.exe -m scripts.seed_interview_questions            # add missing
    venv\\Scripts\\python.exe -m scripts.seed_interview_questions --dry-run  # show, write nothing
    venv\\Scripts\\python.exe -m scripts.seed_interview_questions --remove   # undo

**These are test data for Phase 3, not SmartHR's final interview questions.**
Twelve MAIN questions across the five categories and two FOLLOW_UP examples
(stored now, used in a later phase). The texts are deliberately generic -
job-specific questions arrive with the job context.

Unlike the `DEMO - ` rows elsewhere, these texts carry no prefix: they are
spoken aloud, and an interviewer saying "demo dash" would break the test it
exists for. What identifies them is this file - `--remove` deletes exactly
these texts and nothing else. Idempotent: a question whose exact text already
exists is skipped, never duplicated or overwritten (so HR edits survive a
re-run). Writes go through `question_bank_service`, so the same validation
applies as through the API.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import InterviewQuestion  # noqa: E402
from app.services import question_bank_service as bank  # noqa: E402

#: (position, category, difficulty, English text, Arabic text, evaluation_focus).
#: Positions leave
#: gaps of 10 so HR can insert a question between two without renumbering.
MAIN = [
    (10, "general", "easy", "Tell me about yourself.", "حدّثني عن نفسك.",
     "A clear, relevant summary of background and direction; structure; brevity."),
    (20, "behavioral", "medium", "Tell me about a challenging situation you faced and how you handled it.",
     "صف موقفًا صعبًا واجهته وكيف تعاملت معه.",
     "A concrete situation, the applicant's own actions, and the outcome (STAR)."),
    (30, "behavioral", "medium", "How do you work within a team?", "كيف تعمل ضمن فريق؟",
     "Collaboration habits, communication, and a real example of teamwork."),
    (40, "general", "easy", "What are your main strengths?", "ما أبرز نقاط قوتك؟",
     "Specific strengths supported by evidence, not a list of adjectives."),
    (50, "situational", "medium", "What would you do if you disagreed with a teammate about an important decision?",
     "كيف ستتعامل مع اختلافك مع أحد أعضاء الفريق حول قرار مهم؟",
     "Respectful disagreement, listening, using evidence, and knowing when to escalate."),
    (60, "technical", "medium", "Describe a technical problem you solved recently. What was your approach?",
     "صف مشكلة تقنية حللتها مؤخرًا، وما النهج الذي اتبعته؟",
     "Problem decomposition, reasoning, tools used, and verification of the result."),
    (70, "technical", "medium", "How do you go about learning a new tool or technology?",
     "كيف تتعلم أداة أو تقنية جديدة؟",
     "Learning strategy, resources, practice, and applying it to real work."),
    (80, "behavioral", "medium", "Tell me about a time you made a mistake at work. What did you learn from it?",
     "حدثني عن خطأ ارتكبته في العمل، وما الذي تعلمته منه؟",
     "Ownership, honesty, the corrective action taken, and a concrete lesson."),
    (90, "situational", "hard", "How would you prioritise your work if you had several urgent tasks with the same deadline?",
     "كيف تحدد أولويات عملك إذا كان لديك عدة مهام عاجلة بالموعد النهائي نفسه؟",
     "Prioritisation criteria, communication with stakeholders, and trade-offs."),
    (100, "role_specific", "easy", "Why are you interested in this role?", "ما الذي يجذبك إلى هذه الوظيفة؟",
     "Motivation connected to the role, not only to the company or salary."),
    (110, "general", "medium", "Where would you like to grow professionally over the next few years?",
     "ما الجوانب المهنية التي تود تطويرها خلال السنوات القليلة المقبلة؟",
     "Realistic, specific development goals and self-awareness."),
    (120, "behavioral", "medium", "Tell me about a time you received difficult feedback. How did you respond?",
     "حدثني عن موقف تلقيت فيه ملاحظات صعبة، وكيف استجبت لها؟",
     "Openness to feedback, reflection, and a change in behaviour that followed."),
]

#: (parent's English text, position, difficulty, English text, Arabic text, evaluation_focus)
FOLLOW_UPS = [
    ("Tell me about yourself.", 10, "easy", "What led you to choose that path?",
     "ما الذي دفعك إلى اختيار هذا المسار؟",
     "Motivation behind career choices."),
    ("Tell me about a challenging situation you faced and how you handled it.", 10, "medium",
     "What would you do differently if it happened again?",
     "ما الذي ستفعله بشكل مختلف إذا تكرر الموقف؟",
     "Reflection and learning from the outcome."),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()

    texts = [m[3] for m in MAIN] + [f[3] for f in FOLLOW_UPS]
    db = SessionLocal()
    try:
        existing = {q.question_text: q for q in db.query(InterviewQuestion)
                    .filter(InterviewQuestion.question_text.in_(texts)).all()}

        if args.remove:
            # Follow-ups first: they reference their parents.
            order = [f[3] for f in FOLLOW_UPS] + [m[3] for m in MAIN]
            removed = 0
            for text in order:
                q = existing.get(text)
                if q is None:
                    continue
                if args.dry_run:
                    print(f"  would remove #{q.id}: {text}")
                else:
                    db.delete(q)
                    db.commit()
                removed += 1
            print(f"{'Would remove' if args.dry_run else 'Removed'} {removed} seeded question(s).")
            return 0

        added = skipped = translated = 0
        for position, category, difficulty, text, text_ar, focus in MAIN:
            if text in existing:
                question = existing[text]
                if not question.question_text_ar:
                    if args.dry_run:
                        print(f"  would add Arabic variant for #{question.id}: {text}")
                    else:
                        question.question_text_ar = text_ar
                        db.commit()
                    translated += 1
                skipped += 1
                continue
            if args.dry_run:
                print(f"  would add main   p={position:<4} {category:<13} {text}")
            else:
                existing[text] = bank.create_question(db, {
                    "question_text": text, "question_text_ar": text_ar,
                    "category": category, "difficulty": difficulty,
                    "question_type": "main", "evaluation_focus": focus, "position": position,
                })
            added += 1

        for parent_text, position, difficulty, text, text_ar, focus in FOLLOW_UPS:
            if text in existing:
                question = existing[text]
                if not question.question_text_ar:
                    if args.dry_run:
                        print(f"  would add Arabic variant for #{question.id}: {text}")
                    else:
                        question.question_text_ar = text_ar
                        db.commit()
                    translated += 1
                skipped += 1
                continue
            parent = existing.get(parent_text)
            if args.dry_run:
                print(f"  would add follow_up (parent: {parent_text[:40]}...) {text}")
            elif parent is None:
                print(f"  skipped follow-up, parent missing: {text}")
                continue
            else:
                existing[text] = bank.create_question(db, {
                    "question_text": text, "question_text_ar": text_ar,
                    "category": parent.category, "difficulty": difficulty,
                    "question_type": "follow_up", "parent_question_id": parent.id,
                    "evaluation_focus": focus, "position": position,
                })
            added += 1

        verb = "Would add" if args.dry_run else "Added"
        print(f"{verb} {added}, skipped {skipped} already present.")
        print(f"{'Would add' if args.dry_run else 'Added'} {translated} missing Arabic variant(s).")
        if not args.dry_run:
            plan = bank.interview_plan(db)
            print(f"\nInterview plan now ({len(plan)} main questions, in order):")
            for i, q in enumerate(plan, 1):
                print(f"  Q{i} (#{q['id']}, p={q['position']}, {q['category']}): {q['question_text']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
