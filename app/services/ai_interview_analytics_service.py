"""AI Interview analytics (Phase 11.5.3) - counts over what is stored.

    GET /ai-interview/analytics      Admin and HR only (the router's guard)

**Read-only and deterministic.** No model, no LiveKit, no write, no migration.
Every number is a COUNT (or a maximum question number) over the stored rows
of `interviews`, `ai_interview_sessions`, `ai_interview_answers`,
`ai_interview_answer_analyses` and `interview_questions`; the same database
gives the same answer. Nothing here reads a transcript, the analysis prose,
anything about the candidate, or a score - the queries select ids, statuses,
question numbers and the stored `meta.context` booleans only, so there is
nothing of that kind to leak.

What each figure means:

* `overview` - the interviews that have at least one AI Interview session
  (`total_interviews`), by their CURRENT status. `scheduled` / `in_progress` /
  `completed` are buckets of that total; `cancelled` interviews are in the
  total but have no bucket, so the buckets may sum to less than the total.
* `activity` - `answers_recorded`: stored answers. `main_questions_reached`:
  distinct MAIN Question Bank ids answered, per session, summed (a main
  question answered in two parts counts once). `follow_ups_answered`: stored
  answers to follow-up questions. `highest_question_reached`: the largest
  `question_number` of a stored MAIN answer (null when there is none).
* `analysis` - `completed` / `failed`: stored analysis rows by status;
  `pending`: stored answers with no analysis row yet.
* `context` - completed analyses whose stored `meta.context` says the Job,
  CV or Matching context was present. Matching there is skills only (the
  analysis is never given the Match Score, Phase 7), and no context content
  is read.
* `question_flow` - `main_questions`: distinct main Question Bank ids ever
  answered; `follow_ups`: distinct follow-up Question Bank ids ever answered;
  `not_reached`: main questions of the CURRENT Question Bank plan that no
  session in scope answered. The plan a session used is not stored (Phase 8),
  so this is measured against today's plan and no planned total is claimed.
  `order_comparable`: true when at least one main question was answered and
  every answered main question is still in the current plan - i.e. an order
  against today's bank can be stated; false otherwise.

`interview_ids` narrows every figure to those interviews. The endpoint does
not expose it; it exists so the figures can be checked against known
fixtures.
"""

import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    AiInterviewAnswer,
    AiInterviewAnswerAnalysis,
    AiInterviewSession,
    Interview,
    InterviewQuestion,
)
from app.routers.interviews import read_status
from app.services import question_bank_service

logger = logging.getLogger("smarthr.interview.analytics")

#: The response's shape - asserted by the tests, so a new field (a "score",
#: say) is a deliberate change rather than a side effect.
ANALYTICS_FIELDS = {
    "overview": ("total_interviews", "scheduled", "in_progress", "completed"),
    "activity": ("answers_recorded", "main_questions_reached", "follow_ups_answered", "highest_question_reached"),
    "analysis": ("completed", "pending", "failed"),
    "context": ("job", "cv", "matching"),
    "question_flow": ("main_questions", "follow_ups", "not_reached", "order_comparable"),
}
CONTEXT_KINDS = ("job", "cv", "matching")


def _scoped(query, column, interview_ids: list[int] | None):
    return query if interview_ids is None else query.filter(column.in_(interview_ids))


def interview_analytics(db: Session, interview_ids: Iterable[int] | None = None) -> dict[str, Any]:
    scope = None if interview_ids is None else sorted(set(interview_ids))

    # --- overview: interviews with an AI Interview session -----------------------------
    with_session = _scoped(db.query(AiInterviewSession.interview_id).distinct(),
                           AiInterviewSession.interview_id, scope).subquery()
    statuses = [read_status(s) for (s,) in db.query(Interview.status)
                .filter(Interview.id.in_(db.query(with_session.c.interview_id))).all()]

    # --- answers: id, session, question, number - and each question's type -----------
    answers = (_scoped(db.query(AiInterviewAnswer.id, AiInterviewAnswer.session_id,
                                AiInterviewAnswer.question_id, AiInterviewAnswer.question_number),
                       AiInterviewAnswer.interview_id, scope)
               .order_by(AiInterviewAnswer.id).all())
    question_ids = {a.question_id for a in answers}
    types = dict(db.query(InterviewQuestion.id, InterviewQuestion.question_type)
                 .filter(InterviewQuestion.id.in_(question_ids)).all()) if question_ids else {}
    main = [a for a in answers if types.get(a.question_id) == "main"]
    follow = [a for a in answers if types.get(a.question_id) == "follow_up"]

    # --- analyses: status, and ONLY the stored meta.context booleans ----------------------
    context_expr = AiInterviewAnswerAnalysis.analysis["meta"]["context"]
    analysed = (_scoped(db.query(AiInterviewAnswerAnalysis.status, context_expr)
                        .join(AiInterviewAnswer, AiInterviewAnswer.id == AiInterviewAnswerAnalysis.answer_id),
                        AiInterviewAnswer.interview_id, scope).all())
    by_status = {"completed": 0, "failed": 0}
    context = {k: 0 for k in CONTEXT_KINDS}
    for status, flags in analysed:
        if status in by_status:
            by_status[status] += 1
        if status == "completed" and isinstance(flags, dict):
            for k in CONTEXT_KINDS:
                context[k] += 1 if flags.get(k) is True else 0

    # --- question flow against TODAY's plan (the session's plan is not stored) --------
    plan_ids = [q["id"] for q in question_bank_service.interview_plan(db)]
    main_ids = {a.question_id for a in main}
    result = {
        "overview": {
            "total_interviews": len(statuses),
            "scheduled": statuses.count("scheduled"),
            "in_progress": statuses.count("in_progress"),
            "completed": statuses.count("completed"),
        },
        "activity": {
            "answers_recorded": len(answers),
            "main_questions_reached": len({(a.session_id, a.question_id) for a in main}),
            "follow_ups_answered": len(follow),
            "highest_question_reached": max((a.question_number for a in main), default=None),
        },
        "analysis": {
            "completed": by_status["completed"],
            "pending": len(answers) - len(analysed),
            "failed": by_status["failed"],
        },
        "context": context,
        "question_flow": {
            "main_questions": len(main_ids),
            "follow_ups": len({a.question_id for a in follow}),
            "not_reached": len([q for q in plan_ids if q not in main_ids]),
            "order_comparable": bool(main_ids) and main_ids <= set(plan_ids),
        },
    }
    logger.info("interview analytics built: scope=%s interviews=%d answers=%d",
                "all" if scope is None else len(scope), len(statuses), len(answers))
    return result
