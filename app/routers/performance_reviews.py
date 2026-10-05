from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models import (
    PerformanceReview,
    Employee,
    Department,
    Position,
    User,
)
from app.dependencies import require_roles
from app.dependencies import get_current_employee
from app.audit import (
    record_audit,
    ACTION_CREATE,
    ACTION_UPDATE,
    ENTITY_PERFORMANCE_REVIEW,
)
from app.routers.interviews import describe_user


router = APIRouter(
    prefix="/performance-reviews",
    tags=["Performance Reviews"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Rating
#
# PostgreSQL enforces CHECK (rating >= 1 AND rating <= 5) on an INTEGER
# column. Validate here too so the API returns a clean 422 instead of
# letting the insert fail with an IntegrityError.
# =========================

RATING_MIN = 1
RATING_MAX = 5

RATING_LABELS = {
    5: "Exceptional",
    4: "Exceeds Expectations",
    3: "Meets Expectations",
    2: "Needs Improvement",
    1: "Unsatisfactory",
}


def validate_rating(rating: int) -> int:
    if rating is None or rating < RATING_MIN or rating > RATING_MAX:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Rating must be a whole number between {RATING_MIN} and "
                f"{RATING_MAX} (database constraint "
                f"performance_reviews_rating_check)"
            )
        )

    return rating


def rating_label(rating: int | None) -> str | None:
    if rating is None:
        return None

    return RATING_LABELS.get(rating, "Unrated")


class PerformanceReviewCreate(BaseModel):
    employee_id: int
    rating: int
    reviewer_id: int | None = None
    feedback: str | None = None
    review_date: date | None = None


class PerformanceReviewUpdate(BaseModel):
    employee_id: int
    rating: int
    reviewer_id: int | None = None
    feedback: str | None = None
    review_date: date | None = None


def review_to_dict(review, db):
    employee = (
        db.query(Employee)
        .filter(Employee.id == review.employee_id)
        .first()
    )

    department = None
    position = None

    if employee is not None:
        if employee.department_id:
            department = (
                db.query(Department)
                .filter(Department.id == employee.department_id)
                .first()
            )

        if employee.position_id:
            position = (
                db.query(Position)
                .filter(Position.id == employee.position_id)
                .first()
            )

    reviewer = (
        db.query(User)
        .filter(User.id == review.reviewer_id)
        .first()
    )

    reviewer_name, reviewer_role = describe_user(reviewer, db)

    return {
        "id": review.id,

        "employee_id": review.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee else None
        ),
        "department_name": department.name if department else None,
        "position_title": position.title if position else None,

        "reviewer_id": review.reviewer_id,
        "reviewer_name": reviewer_name,
        "reviewer_email": reviewer.email if reviewer else None,
        "reviewer_role": reviewer_role,

        "rating": review.rating,
        "rating_label": rating_label(review.rating),
        "feedback": review.feedback,
        "review_date": review.review_date,
        "created_at": review.created_at,
    }


def get_review_or_404(review_id: int, db: Session) -> PerformanceReview:
    review = (
        db.query(PerformanceReview)
        .filter(PerformanceReview.id == review_id)
        .first()
    )

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="Performance review not found"
        )

    return review


def validate_relations(employee_id: int, reviewer_id: int, db: Session):
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=400,
            detail=f"Employee {employee_id} does not exist"
        )

    # reviewer_id is a FK to users, not employees.
    reviewer = (
        db.query(User)
        .filter(User.id == reviewer_id)
        .first()
    )

    if reviewer is None:
        raise HTTPException(
            status_code=400,
            detail=f"Reviewer (user) {reviewer_id} does not exist"
        )


# =========================
# Reviewer picker
#
# Declared before /{review_id} so the literal path wins the route match.
# reviewer_id references users, and /users/ is Admin-only, so managers get
# this narrow view instead.
# =========================

@router.get("/reviewers")
def get_reviewers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )

    result = []

    for user in users:
        name, role = describe_user(user, db)

        result.append({
            "id": user.id,
            "email": user.email,
            "name": name,
            "role": role,
        })

    return result


# =========================
# Get Performance Reviews
# =========================

# =========================
# My Reviews
#
# Scoped to the caller and declared before /{review_id}.
# =========================

@router.get("/me")
def get_my_reviews(
    db: Session = Depends(get_db),
    employee=Depends(get_current_employee)
):
    reviews = (
        db.query(PerformanceReview)
        .filter(PerformanceReview.employee_id == employee.id)
        .order_by(PerformanceReview.review_date.desc(), PerformanceReview.id.desc())
        .all()
    )

    return [review_to_dict(review, db) for review in reviews]


# =========================
# Get Reviews (whole organisation)
#
# Admin, HR and Managers only. Employees read /performance-reviews/me.
# =========================

@router.get("/")
def get_reviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    reviews = (
        db.query(PerformanceReview)
        .order_by(
            PerformanceReview.review_date.desc(),
            PerformanceReview.id.desc()
        )
        .all()
    )

    return [
        review_to_dict(review, db)
        for review in reviews
    ]


# =========================
# Get One Review
# =========================

@router.get("/{review_id}")
def get_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    return review_to_dict(get_review_or_404(review_id, db), db)


# =========================
# Create Review
# =========================

@router.post("/")
def create_review(
    data: PerformanceReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    reviewer_id = data.reviewer_id or current_user.id

    validate_relations(data.employee_id, reviewer_id, db)
    validate_rating(data.rating)

    review = PerformanceReview(
        employee_id=data.employee_id,
        reviewer_id=reviewer_id,
        rating=data.rating,
        feedback=data.feedback,
        review_date=data.review_date or date.today()
    )

    db.add(review)
    db.commit()
    db.refresh(review)

    record_audit(db, current_user, ACTION_CREATE, ENTITY_PERFORMANCE_REVIEW, review.id)

    return review_to_dict(review, db)


# =========================
# Update Review
# =========================

@router.put("/{review_id}")
def update_review(
    review_id: int,
    data: PerformanceReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(1, 2, 3))
):
    review = get_review_or_404(review_id, db)

    reviewer_id = data.reviewer_id or review.reviewer_id or current_user.id

    validate_relations(data.employee_id, reviewer_id, db)
    validate_rating(data.rating)

    review.employee_id = data.employee_id
    review.reviewer_id = reviewer_id
    review.rating = data.rating
    review.feedback = data.feedback
    review.review_date = data.review_date or review.review_date

    db.commit()
    db.refresh(review)

    record_audit(db, current_user, ACTION_UPDATE, ENTITY_PERFORMANCE_REVIEW, review.id)

    return review_to_dict(review, db)
