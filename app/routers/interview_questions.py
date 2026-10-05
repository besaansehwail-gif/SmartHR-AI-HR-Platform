"""AI Interview Question Bank - HR management API.

    GET   /ai-interview/questions                 list (filters: active, category, question_type)
    POST  /ai-interview/questions                 create
    GET   /ai-interview/questions/{id}            one question
    PUT   /ai-interview/questions/{id}            partial update (only the fields sent)
    PATCH /ai-interview/questions/{id}/status     activate / deactivate

**Admin and HR only - on every route, reads included.** The bank is what
applicants will be asked; letting an applicant (or a Manager/Employee) read it
would hand out the questions before the interview. Applicants reach the
questions only by being asked them, one at a time, by the interviewer.

There is **no DELETE**: a question is deactivated. Later phases store answers
against questions, and a deleted row would orphan them.

Every write is audited under `ENTITY_INTERVIEW_QUESTION`, after the commit.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.audit import (
    ACTION_ACTIVATE,
    ACTION_CREATE,
    ACTION_DEACTIVATE,
    ACTION_UPDATE,
    ENTITY_INTERVIEW_QUESTION,
    record_audit,
)
from app.dependencies import get_db, require_roles
from app.models import User
from app.services import question_bank_service as bank
from app.services.question_bank_service import QuestionBankError

router = APIRouter(prefix="/ai-interview/questions", tags=["AI Interview Question Bank"])

#: Admin and HR. Named once so the guard and the docstring cannot drift.
BANK_ROLES = (1, 2)

ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "conflict": status.HTTP_409_CONFLICT,
}


def _fail(error: QuestionBankError):
    raise HTTPException(
        status_code=ERROR_STATUS.get(error.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        detail=str(error),
    )


class QuestionCreate(BaseModel):
    # Unknown fields are refused rather than ignored - a typo like
    # "catgory" must not silently fall back to the default.
    model_config = ConfigDict(extra="forbid")

    question_text: str = Field(max_length=2000)
    question_text_ar: str = Field(min_length=5, max_length=2000)
    category: str = "general"
    difficulty: str = "medium"
    question_type: str = "main"
    evaluation_focus: str | None = Field(default=None, max_length=4000)
    parent_question_id: int | None = None
    position: int = 0
    is_active: bool = True


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_text: str | None = Field(default=None, max_length=2000)
    question_text_ar: str | None = Field(default=None, min_length=5, max_length=2000)
    category: str | None = None
    difficulty: str | None = None
    question_type: str | None = None
    evaluation_focus: str | None = Field(default=None, max_length=4000)
    parent_question_id: int | None = None
    position: int | None = None


class QuestionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


@router.get("", dependencies=[Depends(require_roles(*BANK_ROLES))])
def list_questions(
    active: bool | None = Query(default=None),
    category: str | None = Query(default=None),
    question_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        rows = bank.list_questions(db, active=active, category=category, question_type=question_type)
    except QuestionBankError as error:
        _fail(error)
    return {
        "questions": [bank.question_to_dict(q) for q in rows],
        "vocabulary": {
            "category": list(bank.CATEGORIES),
            "difficulty": list(bank.DIFFICULTIES),
            "question_type": list(bank.QUESTION_TYPES),
        },
        "questions_per_interview": bank.question_count(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreate,
    current_user: User = Depends(require_roles(*BANK_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        q = bank.create_question(db, payload.model_dump())
    except QuestionBankError as error:
        _fail(error)
    question_id = q.id
    result = bank.question_to_dict(q)
    record_audit(db, current_user, ACTION_CREATE, ENTITY_INTERVIEW_QUESTION, question_id)
    return result


@router.get("/{question_id}", dependencies=[Depends(require_roles(*BANK_ROLES))])
def get_question(question_id: int, db: Session = Depends(get_db)):
    try:
        return bank.question_to_dict(bank.get_question(db, question_id))
    except QuestionBankError as error:
        _fail(error)


@router.put("/{question_id}")
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    current_user: User = Depends(require_roles(*BANK_ROLES)),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    try:
        q = bank.update_question(db, question_id, data)
    except QuestionBankError as error:
        _fail(error)
    result = bank.question_to_dict(q)
    record_audit(db, current_user, ACTION_UPDATE, ENTITY_INTERVIEW_QUESTION, question_id)
    return result


@router.patch("/{question_id}/status")
def set_question_status(
    question_id: int,
    payload: QuestionStatus,
    current_user: User = Depends(require_roles(*BANK_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        q, changed = bank.set_active(db, question_id, payload.is_active)
    except QuestionBankError as error:
        _fail(error)
    result = bank.question_to_dict(q)
    if changed:
        action = ACTION_ACTIVATE if payload.is_active else ACTION_DEACTIVATE
        record_audit(db, current_user, action, ENTITY_INTERVIEW_QUESTION, question_id)
    return result
