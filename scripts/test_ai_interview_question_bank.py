"""AI Interview - Question Bank API tests (CRUD, validation, RBAC, agent plan).

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_question_bank

Launches its own backend on port 8045 with THROWAWAY LiveKit credentials in
its environment (which outranks `.env.local`), so agent tokens can be minted
here and verified there without touching the real project's secret.

Its questions are prefixed `TEST-QB ` and placed at positions >= 90000, so
they never enter the real first-five interview plan while the suite runs, and
they are deleted at the end (follow-ups first).
"""

import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_helpers as e2e  # noqa: E402

PORT = 8045
BASE = f"http://127.0.0.1:{PORT}"
PREFIX = "TEST-QB "
FAKE_URL = "wss://smarthr-test.invalid"
FAKE_KEY = "APItest" + secrets.token_hex(4)
FAKE_SECRET = secrets.token_urlsafe(32)

ACCOUNTS = {1: "qb.admin@smarthr.test", 2: "qb.hr@smarthr.test",
            3: "qb.manager@smarthr.test", 4: "qb.employee@smarthr.test"}
APPLICANT = "qb.applicant@smarthr.test"

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name}{f' - {detail}' if detail else ''}")
        print(f"  FAIL  {name}{f' - {detail}' if detail else ''}")
    return bool(ok)


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


class Server:
    def __init__(self, port: int):
        self.port, self._p = port, None

    def __enter__(self):
        self._p = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port), "--log-level", "warning"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "LIVEKIT_URL": FAKE_URL, "LIVEKIT_API_KEY": FAKE_KEY,
                 "LIVEKIT_API_SECRET": FAKE_SECRET,
                 # Phase 5 warms a CV parse on every session; this suite does
                 # not test CVs, so the model is genuinely absent (not empty -
                 # an empty value falls through to .env and the real key).
                 "SMARTHR_LLM_PROVIDER": "none"})
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=2):
                    return self
            except urllib.error.HTTPError:
                return self
            except Exception:
                time.sleep(0.25)
        raise SystemExit("test server did not start")

    def __exit__(self, *_):
        self._p.terminate()
        try:
            self._p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._p.kill()


def audit_count() -> int:
    from sqlalchemy import text

    from app.database import engine
    with engine.connect() as c:
        return c.execute(text("select count(*) from audit_logs where entity_type = 'InterviewQuestion'")).scalar()


def cleanup() -> int:
    from app.database import SessionLocal
    from app.models import InterviewQuestion
    db = SessionLocal()
    try:
        rows = db.query(InterviewQuestion).filter(InterviewQuestion.question_text.like(PREFIX + "%")).all()
        for q in sorted(rows, key=lambda r: r.question_type != "follow_up"):
            db.delete(q)
            db.commit()
        return len(rows)
    finally:
        db.close()


def run() -> None:
    e2e.BASE = BASE
    tok = {}
    for role, email in ACCOUNTS.items():
        e2e.ensure_staff_account(email, role)
        tok[role] = e2e.login(email)
    tok[5] = e2e.register_applicant(APPLICANT, "Question Bank Tester")
    R = e2e.request

    section("1. RBAC - Admin + HR only, every route")
    routes = [("GET", "/ai-interview/questions", None),
              ("POST", "/ai-interview/questions", {"question_text": PREFIX + "RBAC probe question"}),
              ("GET", "/ai-interview/questions/1", None),
              ("PUT", "/ai-interview/questions/1", {"position": 1}),
              ("PATCH", "/ai-interview/questions/1/status", {"is_active": False})]
    for method, path, body in routes:
        check(f"anonymous {method} {path} -> 401", R(method, path, json_body=body).status == 401)
        for role in (3, 4, 5):
            r = R(method, path, token=tok[role], json_body=body)
            check(f"role {role} {method} {path} -> 403", r.status == 403, repr(r))
    for role in (1, 2):
        r = R("GET", "/ai-interview/questions", token=tok[role])
        check(f"role {role} can list", r.status == 200 and "questions" in r.body, repr(r))

    section("2. Create + validation")
    before = audit_count()
    r = R("POST", "/ai-interview/questions", token=tok[2], json_body={
        "question_text": PREFIX + "  Describe   a project you are proud of. ",
        "question_text_ar": PREFIX + "صف مشروعًا تشعر بالفخر لإنجازه.",
        "category": "Behavioral", "difficulty": "hard", "position": 90010,
        "evaluation_focus": "Ownership and impact."})
    main = r.body if r.status == 201 else {}
    check("HR creates a main question -> 201", r.status == 201, repr(r))
    check("text whitespace normalised", main.get("question_text") == PREFIX + "Describe a project you are proud of.")
    check("Arabic variant is stored on the same logical question",
          main.get("question_text_ar") == PREFIX + "صف مشروعًا تشعر بالفخر لإنجازه.")
    check("category token normalised to lowercase", main.get("category") == "behavioral")
    check("defaults: type main, active, no parent",
          main.get("question_type") == "main" and main.get("is_active") is True and main.get("parent_question_id") is None)
    check("created_at / updated_at present", bool(main.get("created_at")) and bool(main.get("updated_at")))
    check("create is audited", audit_count() == before + 1)

    bad = {
        "unknown category": {"question_text": PREFIX + "valid text here", "category": "astrology"},
        "unknown difficulty": {"question_text": PREFIX + "valid text here", "difficulty": "extreme"},
        "unknown type": {"question_text": PREFIX + "valid text here", "question_type": "trick"},
        "text too short": {"question_text": "Hi"},
        "text too long": {"question_text": PREFIX + "x" * 600},
        "negative position": {"question_text": PREFIX + "valid text here", "position": -1},
        "main with a parent": {"question_text": PREFIX + "valid text here", "parent_question_id": main.get("id")},
        "follow_up without parent": {"question_text": PREFIX + "valid text here", "question_type": "follow_up"},
        "follow_up with missing parent": {"question_text": PREFIX + "valid text here",
                                          "question_type": "follow_up", "parent_question_id": 99999999},
        "unknown field (typo)": {"question_text": PREFIX + "valid text here", "catgory": "general"},
        "missing text": {"category": "general"},
        "missing Arabic variant": {"question_text": PREFIX + "No Arabic variant here."},
    }
    for label, body in bad.items():
        r = R("POST", "/ai-interview/questions", token=tok[1], json_body=body)
        check(f"refused 422: {label}", r.status == 422, repr(r))

    r = R("POST", "/ai-interview/questions", token=tok[1], json_body={
        "question_text": PREFIX + "What would you change about it now?",
        "question_text_ar": PREFIX + "ما الذي ستغيره إذا تكرر الأمر؟",
        "question_type": "follow_up",
        "parent_question_id": main.get("id"), "position": 1})
    follow = r.body if r.status == 201 else {}
    check("follow_up under a main question -> 201", r.status == 201 and follow.get("parent_question_id") == main.get("id"), repr(r))
    r = R("POST", "/ai-interview/questions", token=tok[1], json_body={
        "question_text": PREFIX + "A follow-up of a follow-up",
        "question_text_ar": PREFIX + "متابعة لسؤال متابعة.",
        "question_type": "follow_up",
        "parent_question_id": follow.get("id")})
    check("follow_up whose parent is a follow_up -> 422", r.status == 422, repr(r))

    section("3. Read + update")
    r = R("GET", f"/ai-interview/questions/{main['id']}", token=tok[1])
    check("get one -> 200", r.status == 200 and r.body.get("id") == main["id"])
    check("get missing -> 404", R("GET", "/ai-interview/questions/99999999", token=tok[1]).status == 404)
    before = audit_count()
    time.sleep(1.1)
    check("English-only question text update is refused to prevent stale Arabic",
          R("PUT", f"/ai-interview/questions/{main['id']}", token=tok[2],
            json_body={"question_text": PREFIX + "Describe a project you are most proud of."}).status == 422)
    r = R("PUT", f"/ai-interview/questions/{main['id']}", token=tok[2],
          json_body={
              "question_text": PREFIX + "Describe a project you are most proud of.",
              "question_text_ar": PREFIX + "صف مشروعًا تشعر بالفخر لإنجازه.",
          })
    check("partial update of text -> 200", r.status == 200 and r.body.get("question_text", "").endswith("most proud of."))
    check("untouched fields unchanged", r.body.get("category") == "behavioral" and r.body.get("difficulty") == "hard")
    check("partial English update preserves the Arabic variant",
          r.body.get("question_text_ar") == PREFIX + "صف مشروعًا تشعر بالفخر لإنجازه.")
    check("updated_at moved", r.body.get("updated_at") != main.get("updated_at"))
    check("update is audited", audit_count() == before + 1)
    check("empty update -> 422", R("PUT", f"/ai-interview/questions/{main['id']}", token=tok[2], json_body={}).status == 422)
    check("invalid update -> 422",
          R("PUT", f"/ai-interview/questions/{main['id']}", token=tok[2], json_body={"difficulty": "impossible"}).status == 422)
    r = R("PUT", f"/ai-interview/questions/{main['id']}", token=tok[2], json_body={"question_type": "follow_up",
                                                                                   "parent_question_id": main["id"]})
    check("a main with follow-ups cannot become a follow-up -> 409 (or self-parent 422)",
          r.status in (409, 422), repr(r))
    check("update missing -> 404",
          R("PUT", "/ai-interview/questions/99999999", token=tok[2], json_body={"position": 3}).status == 404)

    section("4. Activate / deactivate")
    before = audit_count()
    r = R("PATCH", f"/ai-interview/questions/{main['id']}/status", token=tok[1], json_body={"is_active": False})
    check("deactivate -> 200, inactive", r.status == 200 and r.body.get("is_active") is False)
    check("deactivation audited", audit_count() == before + 1)
    r = R("PATCH", f"/ai-interview/questions/{main['id']}/status", token=tok[1], json_body={"is_active": False})
    check("deactivating again is a no-op (no second audit row)", r.status == 200 and audit_count() == before + 1)
    r = R("GET", "/ai-interview/questions?active=false", token=tok[1])
    check("list active=false includes it", main["id"] in [q["id"] for q in r.body.get("questions", [])])
    r = R("GET", "/ai-interview/questions?active=true", token=tok[1])
    check("list active=true excludes it", main["id"] not in [q["id"] for q in r.body.get("questions", [])])
    check("list with an invalid category filter -> 422",
          R("GET", "/ai-interview/questions?category=astrology", token=tok[1]).status == 422)
    r = R("PATCH", f"/ai-interview/questions/{main['id']}/status", token=tok[1], json_body={"is_active": True})
    check("reactivate -> 200, active", r.status == 200 and r.body.get("is_active") is True)
    check("no DELETE route (deactivate instead)",
          R("DELETE", f"/ai-interview/questions/{main['id']}", token=tok[1]).status == 405)

    section("5. Deterministic interview plan (service)")
    from app.database import SessionLocal
    from app.services import question_bank_service as bank
    db = SessionLocal()
    try:
        full = bank.interview_plan(db, limit=100)
        keys = [(q["position"], q["id"]) for q in full]
        check("plan ordered by (position, id)", keys == sorted(keys))
        check("plan holds only main questions", main["id"] in [q["id"] for q in full]
              and follow.get("id") not in [q["id"] for q in full])
        R("PATCH", f"/ai-interview/questions/{main['id']}/status", token=tok[1], json_body={"is_active": False})
        db.expire_all()
        check("an inactive question leaves the plan",
              main["id"] not in [q["id"] for q in bank.interview_plan(db, limit=100)])
        check("same bank -> same plan (repeatable)",
              bank.interview_plan(db, limit=100) == bank.interview_plan(db, limit=100))
        first = bank.interview_plan(db)
        check("default plan length is questions_per_interview", len(first) <= bank.question_count())
        # Phase 11.1 adds `follow_up` (None or one predefined follow-up); it is
        # held to the same rule - no evaluation_focus, no is_active.
        check("plan items expose no evaluation_focus / is_active",
              all(set(q) == {"id", "position", "category", "question_text", "follow_up"} for q in first)
              and all(q["follow_up"] is None
                      or set(q["follow_up"]) == {"id", "parent_question_id", "position", "question_text"}
                      for q in first))
        english = bank.interview_plan(db, language="en", limit=100)
        arabic = bank.interview_plan(db, language="ar", limit=100)
        check("English and Arabic plans preserve identical logical ids and ordering",
                      [(q["id"], q["position"]) for q in english]
                      == [(q["id"], q["position"]) for q in arabic])
        check("Arabic variants stay on the same main and follow-up ids",
                      all(q["question_text"] == bank.get_question(db, q["id"]).question_text_ar
                          and (q["follow_up"] is None or q["follow_up"]["question_text"]
                               == bank.get_question(db, q["follow_up"]["id"]).question_text_ar)
                          for q in arabic))
    finally:
        db.close()

    section("6. Agent plan endpoint - agent only")
    from livekit import api

    from app.ai.interview.agent_auth import mint_agent_token
    room = "smarthr-ai-interview-" + secrets.token_hex(8)
    P = "/ai-interview/agent/plan"

    def plan_call(bearer):
        req = urllib.request.Request(BASE + P, method="POST", data=b"",
                                     headers={"Authorization": bearer} if bearer else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                import json
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, None

    check("no token -> 401", plan_call(None)[0] == 401)
    check("garbage bearer -> 403", plan_call("Bearer not-a-token")[0] == 403)
    check("an applicant's SmartHR login JWT -> 403", plan_call(f"Bearer {tok[5]}")[0] == 403)
    check("an HR SmartHR login JWT -> 403", plan_call(f"Bearer {tok[2]}")[0] == 403)
    # Phase 4: a session is for one of the applicant's interviews, and the
    # plan is served only for a room the backend bound to one.
    interview = e2e.ensure_ai_interview(tok[5])
    sess = R("POST", "/ai-interview/session", token=tok[5],
             json_body={"interview_id": interview["interview_id"]})
    check("an applicant's LiveKit room token -> 403",
          sess.ok and plan_call(f"Bearer {sess.body['participant_token']}")[0] == 403)
    check("a valid agent token for an UNBOUND room -> 404",
          plan_call(f"Bearer {mint_agent_token(FAKE_KEY, FAKE_SECRET, room)}")[0] == 404)
    room = sess.body["room_name"]
    check("agent token signed with the WRONG secret -> 403",
          plan_call(f"Bearer {mint_agent_token(FAKE_KEY, 'wrong' + FAKE_SECRET, room)}")[0] == 403)
    status_, body = plan_call(f"Bearer {mint_agent_token(FAKE_KEY, FAKE_SECRET, room)}")
    check("valid agent token -> 200", status_ == 200)
    body = body or {}
    check("the plan echoes the room it is for", body.get("room_name") == room)
    db = SessionLocal()
    try:
        expected = bank.interview_plan(db)
    finally:
        db.close()
    check("the endpoint returns exactly the deterministic plan", body.get("questions") == expected)
    check("no evaluation_focus / TEST-QB internals leaked",
          "evaluation_focus" not in repr(body) and all(q["id"] != main["id"] for q in body.get("questions", [])))
    again = plan_call(f"Bearer {mint_agent_token(FAKE_KEY, FAKE_SECRET, room)}")[1] or {}
    check("asking twice gives the same plan", again.get("questions") == body.get("questions"))


def main() -> int:
    print("SmartHR - AI Interview Question Bank API tests")
    try:
        with Server(PORT):
            run()
    finally:
        removed = cleanup()
        print(f"\n  cleanup: removed {removed} TEST-QB question(s)")
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
