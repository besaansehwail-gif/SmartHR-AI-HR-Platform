# -*- coding: utf-8 -*-
"""Shared HTTP and account helpers for SmartHR's test scripts.

SmartHR has no test framework and no `httpx` in its venv, so `TestClient` is
unavailable; these drive a **running server** with stdlib `urllib` instead,
which is a truer end-to-end test anyway - every request goes through real JWT
authentication, the real `require_roles` guard re-reading the role from
`users`, and the real database.

These helpers previously lived in `scripts/test_ai_interview_e2e.py` and were
imported from there by the Social Hub suites. They are generic - there is
nothing about any one feature in them - so removing the AI Interview left
them without a home. They were moved here unchanged rather than rewritten.

Test helpers operate only on accounts in the reserved test domain. Configure
the values below in the local environment; replace each placeholder locally
and do not commit credentials or account addresses:

    TEST_ACCOUNT_PASSWORD=<LOCAL_TEST_PASSWORD>
    AI_INTERVIEW_HR_EMAIL=<TEST_ACCOUNT_EMAIL>

`AI_INTERVIEW_HR_EMAIL` is needed only by AI Interview scenarios and must use
the reserved test domain.
"""

import io
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

BASE = "http://127.0.0.1:8000"

def _test_account_password() -> str:
    password = os.environ.get("TEST_ACCOUNT_PASSWORD", "")
    if not password:
        raise RuntimeError(
            "Set TEST_ACCOUNT_PASSWORD in your local environment to run these tests."
        )
    return password


def _require_test_email(email: str) -> str:
    if not email or not email.lower().endswith("@smarthr.test"):
        raise RuntimeError(
            "Test account emails must use the reserved @smarthr.test domain; "
            "set AI_INTERVIEW_HR_EMAIL locally when an HR fixture is required."
        )
    return email


class Response:
    def __init__(self, status: int, body: Any, raw: str):
        self.status = status
        self.body = body
        self.raw = raw

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def __repr__(self) -> str:
        return f"<{self.status} {str(self.body)[:120]}>"

def request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: dict | None = None,
    form: dict | None = None,
    files: dict | None = None,
) -> Response:
    url = f"{BASE}{path}"
    headers: dict[str, str] = {}
    data: bytes | None = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif files is not None:
        data, content_type = _multipart(form or {}, files)
        headers["Content-Type"] = content_type
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except urllib.error.URLError as exc:
        print(f"\nCould not reach {url}: {exc.reason}")
        print("Start the server first:  uvicorn app.main:app --port 8010")
        sys.exit(2)

    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = raw

    return Response(status, body, raw)

def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    buffer = io.BytesIO()

    for key, value in fields.items():
        buffer.write(f"--{boundary}\r\n".encode())
        buffer.write(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        )
        buffer.write(f"{value}\r\n".encode())

    for key, (filename, content) in files.items():
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        buffer.write(f"--{boundary}\r\n".encode())
        buffer.write(
            f'Content-Disposition: form-data; name="{key}"; '
            f'filename="{filename}"\r\n'.encode()
        )
        buffer.write(f"Content-Type: {content_type}\r\n\r\n".encode())
        buffer.write(content)
        buffer.write(b"\r\n")

    buffer.write(f"--{boundary}--\r\n".encode())
    return buffer.getvalue(), f"multipart/form-data; boundary={boundary}"

def login(email: str, password: str | None = None) -> str | None:
    _require_test_email(email)
    if password is None:
        password = _test_account_password()
    response = request(
        "POST", "/auth/login", form={"username": email, "password": password}
    )
    if not response.ok:
        return None
    return response.body.get("access_token")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def ensure_staff_account(email: str, role_id: int) -> int:
    """Create (or reactivate) a staff test account directly in the database.

    SmartHR has no public staff registration - `POST /applicant/register` only
    creates role 5 - so a test that needs to sign in as HR has to make the row
    itself. It uses the same `pwdlib` hash the login endpoint verifies with,
    so nothing here weakens authentication: the account is an ordinary user
    with an ordinary Argon2 hash.
    """
    _require_test_email(email)
    _test_account_password()
    from app.database import SessionLocal
    from app.models import User
    from app.routers.auth import password_hash

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()

        if user is None:
            user = User(
                email=email,
                password_hash=password_hash.hash(_test_account_password()),
                role_id=role_id,
                is_active=True,
            )
            db.add(user)
        else:
            user.password_hash = password_hash.hash(_test_account_password())
            user.role_id = role_id
            user.is_active = True

        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()

def register_applicant(email: str, full_name: str) -> str:
    """Register, or sign in if a previous run already created the account."""
    _require_test_email(email)
    password = _test_account_password()
    response = request(
        "POST",
        "/applicant/register",
        json_body={"full_name": full_name, "email": email, "password": password},
    )

    if response.status == 409:
        token = login(email)
        if token:
            return token
        # A previous run made it with a different password; reset it.
        from app.database import SessionLocal
        from app.models import User
        from app.routers.auth import password_hash

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            user.password_hash = password_hash.hash(_test_account_password())
            db.commit()
        finally:
            db.close()
        return login(email)

    if not response.ok:
        print(f"Registration failed for {email}: {response}")
        sys.exit(2)

    return login(email)


# ---------------------------------------------------------------------------
# The scenario
# ---------------------------------------------------------------------------


#: The job AI Interview tests hold their interview for: an EXISTING row
#: (`scripts/seed_demo_opportunities.py`), never one a test creates.
AI_INTERVIEW_JOB = "DEMO - AI Engineering Intern"
AI_INTERVIEW_HR = os.environ.get("AI_INTERVIEW_HR_EMAIL", "")


def ensure_ai_interview(applicant_token: str, job_title: str = AI_INTERVIEW_JOB) -> dict:
    """A scheduled interview for this applicant, for an existing job.

    Built through SmartHR's own endpoints - the applicant applies
    (`POST /applicant/applications`), HR approves and schedules
    (`ready_ai_interview`) - so the rows are exactly what the real recruitment
    flow produces. Idempotent: an existing application and the fixture
    interview are reused (rescheduled to now when needed), so re-running a
    suite does not pile up rows. Returns
    {interview_id, application_id, job_id, job_title}.
    """
    hr_email = _require_test_email(AI_INTERVIEW_HR)
    ensure_staff_account(hr_email, 2)
    hr = login(hr_email)

    jobs = request("GET", "/jobs/", token=hr).body
    job = next((j for j in jobs if j.get("title") == job_title), None)
    if job is None:
        print(f"Job {job_title!r} not found - run scripts.seed_demo_opportunities first.")
        sys.exit(2)

    apps = request("GET", "/applicant/applications", token=applicant_token).body["applications"]
    application = next((a for a in apps if a.get("job_id") == job["id"]), None)
    if application is None:
        _ensure_fixture_cv(applicant_token)
        r = request("POST", "/applicant/applications", token=applicant_token,
                    json_body={"job_id": job["id"], "confirm": True})
        if not r.ok:
            print(f"Could not apply for the test job: {r}")
            sys.exit(2)
        application = r.body["application"]

    interview_id = ready_ai_interview(hr, application["id"])

    return {"interview_id": interview_id, "application_id": application["id"],
            "job_id": job["id"], "job_title": job["title"]}


AI_INTERVIEW_LOCATION = "AI Interview (online)"


def mark_session_started(room_name: str) -> None:
    """Record that a fixture session's agent STARTED - exactly the record the
    backend writes when a real agent reports "started" (Phase 10: one
    STATUS_CHANGE / AiInterviewSession audit row) - WITHOUT moving the
    interview to in_progress, so a suite that only needs to store answers keeps
    its flow. Since Phase 11.6.4 answers are accepted only for a started
    session. Test fixtures only; idempotent."""
    from sqlalchemy import text

    from app.database import engine
    with engine.begin() as conn:
        conn.execute(text("""
            insert into audit_logs (user_id, action, entity_type, entity_id)
            select null, 'STATUS_CHANGE', 'AiInterviewSession', s.id
            from ai_interview_sessions s
            where s.room_name = :r and not exists (
                select 1 from audit_logs l where l.action = 'STATUS_CHANGE'
                and l.entity_type = 'AiInterviewSession' and l.entity_id = s.id)"""), {"r": room_name})


def ready_ai_interview(hr_token: str, application_id: int) -> int:
    """Make this application's fixture interview startable NOW (Phase 9).

    HR approves the application (stage `interview`, `PATCH
    /applications/{id}/status`) and the fixture interview - the one at
    `AI_INTERVIEW_LOCATION`, reused - is scheduled for now and `scheduled`
    (`PUT /interviews/{id}`), so it is inside the start window. Only what is
    not already so is written. Returns the interview id.
    """
    from datetime import datetime

    from app.database import SessionLocal
    from app.models import Application, Interview
    from app.routers.applications import read_stage

    db = SessionLocal()
    try:
        stage = read_stage(db.get(Application, application_id).status)
        row = (db.query(Interview)
               .filter(Interview.application_id == application_id,
                       Interview.location == AI_INTERVIEW_LOCATION)
               .order_by(Interview.id.desc()).first())
        existing = (row.id, row.status, row.scheduled_at, row.interviewer_id) if row else None
    finally:
        db.close()

    if stage != "interview":
        r = request("PATCH", f"/applications/{application_id}/status", token=hr_token,
                    json_body={"status": "interview"})
        if not r.ok:
            print(f"Could not move the test application to the interview stage: {r}")
            sys.exit(2)

    now = datetime.now().replace(microsecond=0)
    body = {"application_id": application_id, "scheduled_at": now.isoformat(),
            "location": AI_INTERVIEW_LOCATION, "status": "scheduled"}
    if existing is None:
        r = request("POST", "/interviews/", token=hr_token, json_body=body)
        if not r.ok:
            print(f"Could not schedule the test interview: {r}")
            sys.exit(2)
        return r.body["id"]

    interview_id, status, scheduled_at, interviewer_id = existing
    if status == "scheduled" and abs((scheduled_at - now).total_seconds()) < 10 * 60:
        return interview_id
    r = request("PUT", f"/interviews/{interview_id}", token=hr_token,
                json_body={**body, "interviewer_id": interviewer_id})
    if not r.ok:
        print(f"Could not reschedule the test interview: {r}")
        sys.exit(2)
    return interview_id


def _ensure_fixture_cv(applicant_token: str) -> None:
    """Applying requires a CV on file. Store a minimal one the way
    `create_applicant_test_accounts.py` does - through
    `cv_storage.store_cv_file()` - so no model is called to parse it."""
    import io

    from docx import Document

    from app.cv_storage import PROJECT_ROOT, store_cv_file
    from app.database import SessionLocal
    from app.models import CV, Candidate

    me = request("GET", "/auth/me", token=applicant_token).body
    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.user_id == me["id"]).one()
        rows = db.query(CV).filter(CV.candidate_id == candidate.id).all()
        if any((PROJECT_ROOT / row.file_path).is_file() for row in rows):
            return
        doc = Document()
        doc.add_heading(f"{candidate.first_name} {candidate.last_name}", 0)
        doc.add_paragraph("Test fixture CV for AI Interview suites. Python, SQL, Git.")
        buffer = io.BytesIO()
        doc.save(buffer)
        db.add(CV(candidate_id=candidate.id, file_name="fixture-cv.docx",
                  file_path=store_cv_file(buffer.getvalue(), "docx")))
        db.commit()
    finally:
        db.close()
