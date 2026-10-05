"""AI Interview Question Bank - the controlled source of MAIN questions.

    Question Bank   "what could be asked?"     this module + interview_questions
    Controller      "which question is next?"  app/ai/interview/controller.py
    GPT-4o          "how to acknowledge it"    never the source of a question

Vocabulary is lowercase tokens, strict on write (like jobs and applications):
anything else is a 422, never silently coerced. The same rules are CHECK
constraints on the table, so the database refuses what this module would.

`interview_plan()` is the only selection rule in Phase 3, and it is
deliberately boring: active MAIN questions in (position, id) order, the first
`question_count()` of them. Same bank, same plan, every time. Adaptive
selection (by job, CV or matching) is a later phase and will change this
function, not the controller.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.interview.config import interview_setting
from app.models import InterviewQuestion

CATEGORIES = ("general", "behavioral", "technical", "situational", "role_specific")
DIFFICULTIES = ("easy", "medium", "hard")
QUESTION_TYPES = ("main", "follow_up")

TEXT_MIN, TEXT_MAX = 5, 500
FOCUS_MAX = 1000
POSITION_MAX = 100_000

#: Main questions per interview. Five is a short, complete practice interview
#: (~10 minutes with answers); the bank can hold more without all of them
#: being asked. Override with SMARTHR_INTERVIEW_QUESTION_COUNT (1-20).
DEFAULT_QUESTION_COUNT = 5
MAX_QUESTION_COUNT = 20


class QuestionBankError(Exception):
    """A refusal with a `code` the router maps to an HTTP status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def question_count() -> int:
    raw = interview_setting("SMARTHR_INTERVIEW_QUESTION_COUNT")
    try:
        value = int(raw) if raw else DEFAULT_QUESTION_COUNT
    except ValueError:
        return DEFAULT_QUESTION_COUNT
    return value if 1 <= value <= MAX_QUESTION_COUNT else DEFAULT_QUESTION_COUNT


def question_to_dict(q: InterviewQuestion) -> dict:
    """The HR view - every column. Applicants never receive this."""
    return {
        "id": q.id,
        "question_text": q.question_text,
        "question_text_ar": q.question_text_ar,
        "category": q.category,
        "difficulty": q.difficulty,
        "question_type": q.question_type,
        "evaluation_focus": q.evaluation_focus,
        "parent_question_id": q.parent_question_id,
        "position": q.position,
        "is_active": q.is_active,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
    }


def planned_question(q: InterviewQuestion, language: str = "en") -> dict:
    """What the interviewer agent receives - built field by field, not
    filtered, so `evaluation_focus` can never leak into the room by accident."""
    return {
        "id": q.id,
        "position": q.position,
        "category": q.category,
        "question_text": _spoken_text(q, language),
    }


# --- validation --------------------------------------------------------------
def _token(value, allowed: tuple[str, ...], field: str) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token not in allowed:
        raise QuestionBankError("invalid", f"{field} must be one of: {', '.join(allowed)}.")
    return token


def _text(value) -> str:
    text = " ".join(str(value or "").split())
    if not TEXT_MIN <= len(text) <= TEXT_MAX:
        raise QuestionBankError(
            "invalid", f"question_text must be {TEXT_MIN}-{TEXT_MAX} characters."
        )
    return text


def question_language(language: str | None = None) -> str:
    """Resolve a session's language for bank text, including legacy sessions."""
    if language is None:
        from app.ai.interview.config import interview_setting, stt_language

        language = stt_language(interview_setting("SMARTHR_INTERVIEW_LANGUAGE"))
    return "ar" if isinstance(language, str) and language.casefold().startswith("ar") else "en"


def _spoken_text(q: InterviewQuestion, language: str) -> str:
    if language == "en":
        return q.question_text
    if language != "ar":
        raise QuestionBankError("invalid", "Question language must be 'en' or 'ar'.")
    if not q.question_text_ar or not q.question_text_ar.strip():
        raise QuestionBankError(
            "translation_missing",
            f"Question {q.id} has no Arabic text; update the Question Bank before starting an Arabic interview.",
        )
    return q.question_text_ar


def _focus(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if len(text) > FOCUS_MAX:
        raise QuestionBankError("invalid", f"evaluation_focus must be at most {FOCUS_MAX} characters.")
    return text or None


def _position(value) -> int:
    try:
        pos = int(value)
    except (TypeError, ValueError):
        raise QuestionBankError("invalid", "position must be a whole number.") from None
    if not 0 <= pos <= POSITION_MAX:
        raise QuestionBankError("invalid", f"position must be 0-{POSITION_MAX}.")
    return pos


def _check_parent(db: Session, question_type: str, parent_id, own_id: int | None) -> int | None:
    if question_type == "main":
        if parent_id is not None:
            raise QuestionBankError("invalid", "A main question cannot have a parent_question_id.")
        return None
    if parent_id is None:
        raise QuestionBankError("invalid", "A follow_up question needs a parent_question_id.")
    if own_id is not None and int(parent_id) == own_id:
        raise QuestionBankError("invalid", "A question cannot be its own parent.")
    parent = db.get(InterviewQuestion, int(parent_id))
    if parent is None:
        raise QuestionBankError("invalid", "parent_question_id does not exist.")
    if parent.question_type != "main":
        raise QuestionBankError("invalid", "A follow_up's parent must be a main question.")
    return parent.id


# --- CRUD ---------------------------------------------------------------------
def get_question(db: Session, question_id: int) -> InterviewQuestion:
    q = db.get(InterviewQuestion, question_id)
    if q is None:
        raise QuestionBankError("not_found", "Question not found.")
    return q


def list_questions(
    db: Session,
    *,
    active: bool | None = None,
    category: str | None = None,
    question_type: str | None = None,
) -> list[InterviewQuestion]:
    query = db.query(InterviewQuestion)
    if active is not None:
        query = query.filter(InterviewQuestion.is_active.is_(active))
    if category:
        query = query.filter(InterviewQuestion.category == _token(category, CATEGORIES, "category"))
    if question_type:
        query = query.filter(
            InterviewQuestion.question_type == _token(question_type, QUESTION_TYPES, "question_type")
        )
    return query.order_by(InterviewQuestion.position, InterviewQuestion.id).all()


def create_question(db: Session, data: dict) -> InterviewQuestion:
    qtype = _token(data.get("question_type", "main"), QUESTION_TYPES, "question_type")
    now = datetime.utcnow()
    q = InterviewQuestion(
        question_text=_text(data.get("question_text")),
        question_text_ar=_text(data.get("question_text_ar")),
        category=_token(data.get("category", "general"), CATEGORIES, "category"),
        difficulty=_token(data.get("difficulty", "medium"), DIFFICULTIES, "difficulty"),
        question_type=qtype,
        evaluation_focus=_focus(data.get("evaluation_focus")),
        parent_question_id=_check_parent(db, qtype, data.get("parent_question_id"), None),
        position=_position(data.get("position", 0)),
        is_active=bool(data.get("is_active", True)),
        created_at=now,
        updated_at=now,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def update_question(db: Session, question_id: int, data: dict) -> InterviewQuestion:
    """Partial update: only the fields present in `data` change."""
    q = get_question(db, question_id)

    if "question_text" in data and "question_text_ar" not in data:
        raise QuestionBankError(
            "invalid",
            "Updating English question text also requires its Arabic variant.",
        )
    if "question_text" in data:
        q.question_text = _text(data["question_text"])
    if "question_text_ar" in data:
        q.question_text_ar = _text(data["question_text_ar"])
    if "category" in data:
        q.category = _token(data["category"], CATEGORIES, "category")
    if "difficulty" in data:
        q.difficulty = _token(data["difficulty"], DIFFICULTIES, "difficulty")
    if "evaluation_focus" in data:
        q.evaluation_focus = _focus(data["evaluation_focus"])
    if "position" in data:
        q.position = _position(data["position"])

    if "question_type" in data or "parent_question_id" in data:
        qtype = _token(data.get("question_type", q.question_type), QUESTION_TYPES, "question_type")
        parent = data["parent_question_id"] if "parent_question_id" in data else q.parent_question_id
        if qtype == "main" and "parent_question_id" not in data:
            parent = None  # becoming main drops the parent
        if qtype == "follow_up" and q.question_type == "main":
            children = db.query(InterviewQuestion).filter(
                InterviewQuestion.parent_question_id == q.id
            ).count()
            if children:
                raise QuestionBankError(
                    "conflict", f"This main question has {children} follow-up(s); it cannot become a follow-up."
                )
        q.parent_question_id = _check_parent(db, qtype, parent, q.id)
        q.question_type = qtype

    q.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    return q


def set_active(db: Session, question_id: int, active: bool) -> tuple[InterviewQuestion, bool]:
    """Returns (question, changed)."""
    q = get_question(db, question_id)
    if q.is_active == active:
        return q, False
    q.is_active = active
    q.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    return q, True


# --- the interview plan ---------------------------------------------------------
def interview_plan(
    db: Session, limit: int | None = None, *, language: str | None = "en"
) -> list[dict]:
    """The MAIN questions one interview asks, in order. Deterministic.

    Phase 11.1: each carries `follow_up` - its ONE predefined follow-up (the
    first ACTIVE `follow_up` row whose parent is that main question, by
    (position, id)) or None. The main questions and their order are exactly
    what they were: follow-ups are attached, never mixed into the list.
    """
    selected_language = question_language(language)
    limit = limit or question_count()
    rows = (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.question_type == "main")
        .filter(InterviewQuestion.is_active.is_(True))
        .order_by(InterviewQuestion.position, InterviewQuestion.id)
        .limit(limit)
        .all()
    )
    follow_ups: dict[int, InterviewQuestion] = {}
    if rows:
        for f in (db.query(InterviewQuestion)
                  .filter(InterviewQuestion.question_type == "follow_up")
                  .filter(InterviewQuestion.is_active.is_(True))
                  .filter(InterviewQuestion.parent_question_id.in_([q.id for q in rows]))
                  .order_by(InterviewQuestion.position, InterviewQuestion.id)
                  .all()):
            follow_ups.setdefault(f.parent_question_id, f)
    return [
        {
            **planned_question(q, selected_language),
            "follow_up": planned_follow_up(follow_ups.get(q.id), selected_language),
        }
        for q in rows
    ]


def planned_follow_up(q: InterviewQuestion | None, language: str = "en") -> dict | None:
    """A follow-up as the agent receives it - field by field, like
    `planned_question`, plus the parent it must match."""
    if q is None:
        return None
    return {
        "id": q.id,
        "parent_question_id": q.parent_question_id,
        "position": q.position,
        "question_text": _spoken_text(q, language),
    }
