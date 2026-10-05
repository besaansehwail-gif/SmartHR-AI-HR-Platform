"""Clearly-labelled DEMO opportunities, so the Applicant experience has
something to show.

    venv\\Scripts\\python.exe -m scripts.seed_demo_opportunities          add
    venv\\Scripts\\python.exe -m scripts.seed_demo_opportunities --remove  undo

Why this exists: SmartHR's real data has four full-time jobs and **zero**
trainings, so Internships, Training Opportunities and Free Courses would each
render an empty page. These rows exist to demonstrate those sections.

Three rules they follow:

* **Every title starts with "DEMO - "**, so nobody can mistake one for a real
  opening while browsing, and `--remove` can find them again without keeping a
  manifest.
* **Nothing existing is touched.** The four real jobs keep their titles,
  requirements and (absent) locations and deadlines. This script only inserts.
* **Re-running does not duplicate.** Each row is matched by title first.

The applicant-facing code has no seeded, sample or placeholder data anywhere
in it: delete these rows and the pages correctly show that SmartHR has nothing
on offer.
"""

import sys
from datetime import date, timedelta

from app.database import SessionLocal
from app.models import Application, Department, Job, Training

DEMO_PREFIX = "DEMO - "


def _department_id(db, name: str) -> int:
    department = db.query(Department).filter(Department.name == name).first()

    if department is None:
        department = db.query(Department).order_by(Department.id).first()

    return department.id


def demo_jobs(db) -> list[dict]:
    it = _department_id(db, "IT")
    hr = _department_id(db, "HR")
    soon = date.today() + timedelta(days=45)

    return [
        {
            "title": f"{DEMO_PREFIX}AI Engineering Intern",
            "department_id": it,
            "description": (
                "Six-month internship working alongside the AI team on model "
                "integration, evaluation and data pipelines."
            ),
            "requirements": "Python, Machine Learning, SQL, Git",
            "employment_type": "internship",
            "location": "Amman",
            "deadline": soon,
        },
        {
            "title": f"{DEMO_PREFIX}Data Analytics Intern",
            "department_id": it,
            "description": (
                "Internship supporting the analytics team with reporting, "
                "dashboards and data quality checks."
            ),
            "requirements": "Excel, SQL, Power BI",
            "employment_type": "internship",
            "location": "Remote",
            "deadline": soon,
        },
        {
            "title": f"{DEMO_PREFIX}People Operations Assistant",
            "department_id": hr,
            "description": "Part-time support for the HR operations team.",
            "requirements": "Communication, HR Systems, Excel",
            "employment_type": "part_time",
            "location": "Amman",
            "deadline": None,
        },
    ]


DEMO_TRAININGS = [
    {
        "title": f"{DEMO_PREFIX}Advanced SQL for Analysts",
        "description": "Window functions, query tuning and analytical patterns.",
        "provider": "SmartHR Academy",
        "duration_hours": 16,
        "category": "training",
        "url": None,
    },
    {
        "title": f"{DEMO_PREFIX}Interview Skills Workshop",
        "description": "Preparing for technical and behavioural interviews.",
        "provider": "SmartHR Academy",
        "duration_hours": 6,
        "category": "training",
        "url": None,
    },
    {
        "title": f"{DEMO_PREFIX}Python Fundamentals (Free)",
        "description": "Free introductory Python course. No prior experience needed.",
        "provider": "SmartHR Open Learning",
        "duration_hours": 20,
        "category": "free_course",
        "url": "https://example.invalid/demo/python-fundamentals",
    },
    {
        "title": f"{DEMO_PREFIX}Data Literacy Essentials (Free)",
        "description": "Free short course on reading, questioning and presenting data.",
        "provider": "SmartHR Open Learning",
        "duration_hours": 8,
        "category": "free_course",
        "url": "https://example.invalid/demo/data-literacy",
    },
]


def add() -> None:
    db = SessionLocal()
    try:
        created = 0

        for spec in demo_jobs(db):
            if db.query(Job).filter(Job.title == spec["title"]).first():
                continue

            db.add(Job(status="open", **spec))
            created += 1

        for spec in DEMO_TRAININGS:
            if db.query(Training).filter(Training.title == spec["title"]).first():
                continue

            db.add(Training(**spec))
            created += 1

        db.commit()

        print(f"DEMO opportunities added: {created}")
        print(f"  jobs      : {db.query(Job).count()}")
        print(f"  trainings : {db.query(Training).count()}")
    finally:
        db.close()


def remove() -> None:
    """Delete the DEMO rows, refusing any that somebody has applied to.

    A demo job with a real application against it is no longer only demo data -
    deleting it would break the applications row pointing at it.
    """
    db = SessionLocal()
    try:
        removed = kept = 0

        for job in db.query(Job).filter(Job.title.like(f"{DEMO_PREFIX}%")).all():
            if db.query(Application).filter(Application.job_id == job.id).count():
                print(f"  kept (has applications): {job.title}")
                kept += 1
                continue

            db.delete(job)
            removed += 1

        for training in db.query(Training).filter(
            Training.title.like(f"{DEMO_PREFIX}%")
        ).all():
            db.delete(training)
            removed += 1

        db.commit()
        print(f"DEMO opportunities removed: {removed} (kept {kept})")
    finally:
        db.close()


if __name__ == "__main__":
    remove() if "--remove" in sys.argv else add()
