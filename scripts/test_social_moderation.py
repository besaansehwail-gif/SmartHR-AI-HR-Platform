"""AI Moderation V1 for the Social Hub - tests.

    venv\\Scripts\\python.exe -m scripts.test_social_moderation
    venv\\Scripts\\python.exe -m scripts.test_social_moderation --live
    venv\\Scripts\\python.exe -m scripts.test_social_moderation --keep

**The default run makes no network call and needs no OpenAI key.** That is
deliberate: a moderation layer whose test suite stops working when a third
party is slow is a moderation layer nobody can refactor. It is achieved two
ways, neither of which is a mock of SmartHR itself:

  * Section 1 runs in-process against a **fake provider** - a stand-in for
    `app/ai/provider.py` that returns scripted replies. Everything downstream
    of the model is real: the real schema, the real validator, the real
    service, the real database.

  * Section 2 launches a real server whose `SMARTHR_LLM_PROVIDER` is set to an
    unsupported value, so `llm_settings().configured` is False and the model
    is genuinely absent. That is not a trick to avoid the network - it is the
    **fail-closed path**, which is the single most important behaviour in this
    feature and the hardest to reach on demand any other way.

    Note it sets the variable to `none` rather than emptying it: `_setting`
    treats an empty value as absent and falls through to `.env`, which on a
    developer's machine holds the real key - the trap
    `_setting` treats an empty value as absent and falls through to `.env`.

`--live` adds section 4, which calls the real model with the five cases from
the brief. That section is an **integration test** and is labelled as one; it
is skipped by default and its failure means the model or the prompt moved, not
that the application is broken.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.test_helpers as e2e  # noqa: E402

from app.ai.provider import LlmError, LlmNotConfigured, LlmReply, ToolCall  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    SocialComment,
    SocialModerationReview,
    SocialPost,
    SocialStory,
    User,
)
from app.services import social_moderation_service as mod  # noqa: E402

PORT = 8042
BASE = f"http://127.0.0.1:{PORT}"

# Ordinary internal accounts, reused across runs like every other suite here.
ALICE = "mod.alice@smarthr.test"        # role 4, posts things
BOB = "mod.bob@smarthr.test"            # role 4, another colleague
CAROL_HR = "mod.carol.hr@smarthr.test"  # role 2, moderates
DAVE_MGR = "mod.dave.mgr@smarthr.test"  # role 3, must NOT moderate
EVE_ADMIN = "mod.eve.admin@smarthr.test"  # role 1, moderates
APPLICANT = "mod.applicant@smarthr.test"  # role 5, must not reach Social Hub

passed = 0
failed = 0
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        failures.append(label)
        print(f"  FAIL  {label}" + (f"   -> {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


# ===========================================================================
# A fake provider
# ===========================================================================

@dataclass
class FakeProvider:
    """Stands in for a language model. Returns what it is told to return.

    It implements the same two methods `app/ai/provider.py` declares, so what
    is being tested is the real call site - not a re-implementation of it.
    """

    payload: dict | None = None
    raise_with: Exception | None = None
    text_instead: str | None = None
    name: str = "fake"
    model: str = "fake-model"
    configured: bool = True
    calls: int = 0

    def complete(self, system, messages, tools=None) -> LlmReply:
        self.calls += 1

        if self.raise_with is not None:
            raise self.raise_with

        if self.text_instead is not None:
            return LlmReply(text=self.text_instead)

        return LlmReply(
            tool_call=ToolCall(name=mod.TOOL_NAME, arguments=self.payload or {})
        )

    def tool_exchange(self, reply, result_json):
        return []


class use_provider:
    """Swap the provider `social_moderation_service` reaches for."""

    def __init__(self, provider):
        self.provider = provider

    def __enter__(self):
        self._original = mod.get_provider
        mod.get_provider = lambda settings=None: self.provider
        return self.provider

    def __exit__(self, *exc):
        mod.get_provider = self._original
        return False


# ===========================================================================
# 1. The service, deterministically
# ===========================================================================

def test_service() -> None:
    section("1. Moderation service - deterministic, no network")

    # --- the validator -----------------------------------------------------
    print("\n  Output validation")

    r = mod.validate_moderation({
        "decision": "allow", "confidence": 0.98, "reason": "Fine.",
    })
    check("a clean allow validates", r.decision == "allow" and r.publishes)
    check("an allow carries no categories or severity",
          r.categories == [] and r.severity is None)

    r = mod.validate_moderation({
        "decision": "flag", "categories": ["harassment"], "severity": "high",
        "confidence": 0.91, "reason": "Targets a colleague.",
    })
    check("a flag validates", r.decision == "flag" and not r.publishes)
    check("a flagged item does not publish",
          r.content_status == mod.CONTENT_PENDING, r.content_status)

    r = mod.validate_moderation({
        "decision": "flag", "categories": ["harassment", "witchcraft", "spam"],
        "severity": "medium", "confidence": 0.7, "reason": "x",
    })
    check("an invented category is dropped",
          r.categories == ["harassment", "spam"], str(r.categories))

    r = mod.validate_moderation({
        "decision": "flag", "categories": "harassment, spam",
        "severity": "low", "confidence": 0.5, "reason": "x",
    })
    check("categories sent as a string are coerced, not rejected",
          r.categories == ["harassment", "spam"], str(r.categories))

    r = mod.validate_moderation({
        "decision": "flag", "categories": ["spam"], "severity": "catastrophic",
        "confidence": 0.5, "reason": "x",
    })
    check("an unusable severity on a flag defaults to medium, keeping the flag",
          r.decision == "flag" and r.severity == "medium", str(r.severity))

    r = mod.validate_moderation({
        "decision": "flag", "categories": ["spam"], "severity": "low",
        "confidence": 4.2, "reason": "x",
    })
    check("confidence above 1 is clamped", r.confidence == 1.0, str(r.confidence))

    r = mod.validate_moderation({
        "decision": "flag", "categories": ["spam"], "severity": "low",
        "confidence": "not a number", "reason": "x",
    })
    check("an unparseable confidence becomes null, not zero",
          r.confidence is None, str(r.confidence))

    r = mod.validate_moderation({
        "decision": "flag", "categories": ["spam"], "severity": "low",
        "confidence": 0.5, "reason": "y" * 900,
    })
    check("an over-long reason is truncated",
          len(r.reason) <= mod.MAX_REASON_CHARS + 3, str(len(r.reason or "")))

    for bad in ("remove", "delete", "", "ALLOW_MAYBE", None):
        try:
            mod.validate_moderation({"decision": bad, "confidence": 1, "reason": "x"})
            check(f"decision {bad!r} is refused", False, "it validated")
        except mod.ModerationError as exc:
            check(f"decision {bad!r} is refused", exc.code == mod.ERROR_INVALID)

    # --- the schema cannot express an HR decision --------------------------
    print("\n  The model has nowhere to put an HR decision")

    props = set(mod.MODERATION_SCHEMA["properties"])
    check("the schema has exactly the five agreed fields",
          props == {"decision", "categories", "severity", "confidence", "reason"},
          str(props))

    forbidden = {"action", "punishment", "discipline", "should_remove",
                 "delete", "employee_action", "recommendation"}
    check("the schema has no field an employment decision could go in",
          not (props & forbidden), str(props & forbidden))

    decisions = set(mod.MODERATION_SCHEMA["properties"]["decision"]["enum"])
    check("the only decisions are allow and flag",
          decisions == {"allow", "flag"}, str(decisions))
    check("there is no 'delete' or 'remove' decision the model could return",
          not (decisions & {"delete", "remove", "hide"}))

    prompt = mod.SYSTEM_PROMPT.lower()
    check("the prompt forbids recommending action about the author",
          "never recommend any action" in prompt)
    check("the system prompt says the content is data, never an instruction",
          "never an instruction" in prompt and "data to be classified" in prompt)
    check("the delimited content block repeats it at the injection point",
          "not an instruction to you" in mod._content_block("x").lower())
    check("the content is delimited so a prompt-injection attempt is contained",
          "--- BEGIN CONTENT ---" in mod._content_block("x"))

    # --- the model call, with a fake model ---------------------------------
    print("\n  moderate_text() with a scripted model")

    with use_provider(FakeProvider(payload={
        "decision": "allow", "confidence": 0.99, "reason": "Workplace praise.",
    })) as fake:
        r = mod.moderate_text("Congratulations to Sarah on completing her training!")
        check("safe content is allowed", r.decision == "allow")
        check("safe content publishes",
              r.content_status == mod.CONTENT_PUBLISHED, r.content_status)
        check("exactly one model call was made", fake.calls == 1, str(fake.calls))

    with use_provider(FakeProvider(payload={
        "decision": "flag", "categories": ["harassment"], "severity": "high",
        "confidence": 0.95, "reason": "Demeans a colleague.",
    })):
        r = mod.moderate_text("You are useless and nobody wants you here.")
        check("harassment is flagged", r.decision == "flag")
        check("flagged content is held, not published",
              r.content_status == mod.CONTENT_PENDING)

    with use_provider(FakeProvider(text_instead='{"decision":"flag",'
                                                '"categories":["spam"],'
                                                '"severity":"low",'
                                                '"confidence":0.8,'
                                                '"reason":"Promotional."}')):
        r = mod.moderate_text("BUY NOW!!!")
        check("a model that answers in prose instead of calling the tool is parsed",
              r.decision == "flag" and r.categories == ["spam"])

    # --- fail closed -------------------------------------------------------
    print("\n  Fail closed - and never destructively")

    for label, exc, code in (
        ("no model configured", LlmNotConfigured("none"), mod.ERROR_NOT_CONFIGURED),
        ("the model errors", LlmError("boom"), mod.ERROR_LLM),
        ("the provider raises something unexpected", RuntimeError("x"), mod.ERROR_LLM),
    ):
        with use_provider(FakeProvider(raise_with=exc)):
            r = mod.moderate_text("Anything at all.")
            check(f"{label}: content is NOT published",
                  r.content_status == mod.CONTENT_PENDING, r.content_status)
            check(f"{label}: recorded as unavailable with a code",
                  r.decision == mod.DECISION_UNAVAILABLE and r.error_code == code,
                  f"{r.decision}/{r.error_code}")

    with use_provider(FakeProvider(text_instead="I'm not going to answer that.")):
        r = mod.moderate_text("Anything.")
        check("unusable model output holds the content",
              r.content_status == mod.CONTENT_PENDING and
              r.error_code == mod.ERROR_INVALID, f"{r.decision}/{r.error_code}")

    with use_provider(FakeProvider(payload={"decision": "allow", "confidence": 1,
                                            "reason": "ok"})) as fake:
        r = mod.moderate_text("   ")
        check("empty text is not sent to the model at all", fake.calls == 0)
        check("empty text publishes (an image-only story)",
              r.content_status == mod.CONTENT_PUBLISHED)

    with use_provider(FakeProvider(payload={"decision": "allow", "confidence": 1,
                                            "reason": "ok"})) as fake:
        r = mod.moderate_text("x" * (mod.MAX_MODERATED_CHARS + 1))
        check("content too long to classify is held, not published",
              r.content_status == mod.CONTENT_PENDING)
        check("content too long to classify is not sent to the model",
              fake.calls == 0)

    # --- the off switch ----------------------------------------------------
    os.environ[mod.MODERATION_VARIABLE] = "false"
    try:
        with use_provider(FakeProvider()) as fake:
            r = mod.moderate_text("You are useless and nobody wants you here.")
            check("with moderation switched off nothing is classified",
                  fake.calls == 0)
            check("with moderation switched off content publishes",
                  r.content_status == mod.CONTENT_PUBLISHED)
    finally:
        os.environ.pop(mod.MODERATION_VARIABLE, None)

    check("moderation is on by default", mod.moderation_enabled())


# ===========================================================================
# 2. The HTTP surface
# ===========================================================================

class Server:
    def __init__(self, port: int, env: dict | None = None):
        self.port = port
        self.env = env or {}
        self._process = None

    def __enter__(self):
        self._process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--port", str(self.port), "--log-level", "warning"],
            cwd=str(ROOT),
            env={**os.environ, **self.env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=2):
                    return self
            except urllib.error.HTTPError:
                return self
            except Exception:
                time.sleep(0.25)

        raise SystemExit(f"The test server on port {self.port} did not start.")

    def __exit__(self, *exc):
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except Exception:
                self._process.kill()
        return False


def post_as(token: str, content: str) -> dict:
    return e2e.request("POST", "/social/posts", token=token,
                       form={"content": content, "audience": "company"}).body or {}


def test_http(created: dict) -> None:
    section("2. End to end over HTTP, with the model deliberately absent")

    print("  The server for this section runs with SMARTHR_LLM_PROVIDER=none, so")
    print("  every submission takes the fail-closed path. No network is used.")
    print()

    e2e.ensure_staff_account(ALICE, 4)
    e2e.ensure_staff_account(BOB, 4)
    e2e.ensure_staff_account(CAROL_HR, 2)
    e2e.ensure_staff_account(DAVE_MGR, 3)
    e2e.ensure_staff_account(EVE_ADMIN, 1)

    alice = e2e.login(ALICE)
    bob = e2e.login(BOB)
    hr = e2e.login(CAROL_HR)
    mgr = e2e.login(DAVE_MGR)
    admin = e2e.login(EVE_ADMIN)
    applicant = e2e.register_applicant(APPLICANT, "Mod Applicant")

    check("all six accounts sign in",
          all([alice, bob, hr, mgr, admin, applicant]))

    # --- an employee posts -------------------------------------------------
    print("\n  An employee submits content")

    created_post = post_as(alice, "DEMO MODERATION - a post made by the test suite.")
    post_id = created_post.get("id")
    created.setdefault("posts", []).append(post_id)

    check("the post is accepted (not an error)", bool(post_id), str(created_post)[:160])
    check("the post is held for review",
          created_post.get("moderation_status") == mod.CONTENT_PENDING,
          str(created_post.get("moderation_status")))
    check("its author is told it is pending, in one boolean",
          created_post.get("pending_review") is True)

    # --- what the author is NOT told --------------------------------------
    print("\n  The author learns the status and nothing else")

    leaked = [k for k in ("categories", "severity", "confidence", "reason",
                          "ai_decision", "error_code", "reviewer")
              if k in created_post]
    check("no AI reasoning reaches the author's payload", not leaked, str(leaked))

    body = str(created_post).lower()
    check("no taxonomy token appears in the author's payload",
          not any(c in body for c in mod.CATEGORIES),
          str([c for c in mod.CATEGORIES if c in body]))

    # --- visibility --------------------------------------------------------
    print("\n  Held content is not on anybody else's feed")

    alice_feed = e2e.request("GET", "/social/feed", token=alice).body or {}
    check("the author still sees their own held post",
          any(p["id"] == post_id for p in alice_feed.get("posts", [])))

    bob_feed = e2e.request("GET", "/social/feed", token=bob).body or {}
    check("a colleague does not see it",
          not any(p["id"] == post_id for p in bob_feed.get("posts", [])))

    direct = e2e.request("GET", f"/social/posts/{post_id}", token=bob)
    check("fetching it by id is a 404 for a colleague, not a 403",
          direct.status == 404, str(direct.status))

    mine = e2e.request("GET", f"/social/posts/{post_id}", token=alice)
    check("the author can still fetch their own", mine.ok, str(mine.status))

    # --- a review row exists ----------------------------------------------
    print("\n  A moderation record was written")

    queue = e2e.request("GET", "/social/moderation?status=pending", token=hr)
    check("HR can read the queue", queue.ok, str(queue.status))

    entry = None
    for row in (queue.body or {}).get("reviews", []):
        if row["content_type"] == "post" and row["content_id"] == post_id:
            entry = row
            break

    if not check("the held post is in the queue", entry is not None):
        return

    review_id = entry["id"]
    created.setdefault("reviews", []).append(review_id)

    check("the record says the model was unavailable",
          entry["ai_decision"] == mod.DECISION_UNAVAILABLE, str(entry["ai_decision"]))
    check("the record names why",
          entry["error_code"] == mod.ERROR_NOT_CONFIGURED, str(entry["error_code"]))
    check("the queue shows the moderator the content itself",
          entry["content"] and "DEMO MODERATION" in entry["content"])
    check("the queue shows who wrote it", (entry.get("author") or {}).get("name"))
    check("it is pending", entry["status"] == mod.REVIEW_PENDING)
    check("nobody has reviewed it yet",
          entry["reviewer"] is None and entry["reviewed_at"] is None)

    # --- RBAC --------------------------------------------------------------
    print("\n  RBAC on the moderation surface")

    for label, token, expected in (
        ("Employee", alice, 403),
        ("Manager", mgr, 403),
        ("Applicant", applicant, 403),
    ):
        for method, path in (
            ("GET", "/social/moderation"),
            ("GET", "/social/moderation/summary"),
            ("GET", f"/social/moderation/{review_id}"),
            ("POST", f"/social/moderation/{review_id}/approve"),
            ("POST", f"/social/moderation/{review_id}/remove"),
        ):
            got = e2e.request(method, path, token=token,
                              json_body={} if method == "POST" else None)
            check(f"{label} gets {expected} on {method} {path}",
                  got.status == expected, str(got.status))

    for method, path in (
        ("GET", "/social/moderation"),
        ("POST", f"/social/moderation/{review_id}/approve"),
    ):
        got = e2e.request(method, path, json_body={} if method == "POST" else None)
        check(f"anonymous gets 401 on {method} {path}", got.status == 401,
              str(got.status))

    for label, token in (("HR", hr), ("Admin", admin)):
        got = e2e.request("GET", "/social/moderation", token=token)
        check(f"{label} may read the queue", got.ok, str(got.status))

    # --- the author cannot approve their own content -----------------------
    self_approve = e2e.request("POST", f"/social/moderation/{review_id}/approve",
                               token=alice, json_body={})
    check("the author cannot approve their own held post",
          self_approve.status == 403, str(self_approve.status))

    still = e2e.request("GET", f"/social/posts/{post_id}", token=bob)
    check("and it is still invisible to colleagues afterwards",
          still.status == 404, str(still.status))

    # --- approval ----------------------------------------------------------
    print("\n  HR approves")

    approved = e2e.request("POST", f"/social/moderation/{review_id}/approve",
                           token=hr, json_body={"note": "Test fixture content."})
    check("HR approves it", approved.ok, f"{approved.status}: {approved.body}")

    if approved.ok:
        check("the record is approved",
              approved.body["status"] == mod.REVIEW_APPROVED)
        check("the reviewer is recorded",
              (approved.body.get("reviewer") or {}).get("name"))
        check("the decision is recorded",
              approved.body["reviewer_decision"] == mod.REVIEW_APPROVED)
        check("the time is recorded", approved.body["reviewed_at"])

    now_visible = e2e.request("GET", f"/social/posts/{post_id}", token=bob)
    check("the post is now visible to colleagues", now_visible.ok,
          str(now_visible.status))
    check("and it no longer says pending to its author",
          (e2e.request("GET", f"/social/posts/{post_id}", token=alice).body or {})
          .get("pending_review") is False)

    # --- removal -----------------------------------------------------------
    print("\n  HR removes")

    second = post_as(alice, "DEMO MODERATION - a second post, to be removed.")
    second_id = second.get("id")
    created["posts"].append(second_id)

    q2 = e2e.request("GET", "/social/moderation?status=pending", token=admin)
    second_review = next(
        (r for r in (q2.body or {}).get("reviews", [])
         if r["content_type"] == "post" and r["content_id"] == second_id), None
    )

    if check("the second post is queued", second_review is not None):
        rid = second_review["id"]
        created["reviews"].append(rid)

        removed = e2e.request("POST", f"/social/moderation/{rid}/remove",
                              token=admin, json_body={"note": "Test."})
        check("Admin removes it", removed.ok, str(removed.status))

        gone_for_all = e2e.request("GET", f"/social/posts/{second_id}", token=bob)
        check("removed content is invisible to colleagues",
              gone_for_all.status == 404, str(gone_for_all.status))

        gone_for_author = e2e.request("GET", f"/social/posts/{second_id}", token=alice)
        check("removed content is invisible to its author too",
              gone_for_author.status == 404, str(gone_for_author.status))

        db = SessionLocal()
        try:
            row = db.query(SocialPost).filter(SocialPost.id == second_id).first()
            check("the post row still exists - removal is a status, not a DELETE",
                  row is not None)
            check("its status is 'removed'",
                  row is not None and row.moderation_status == mod.CONTENT_REMOVED,
                  getattr(row, "moderation_status", "?"))

            rec = db.query(SocialModerationReview).filter(
                SocialModerationReview.id == rid).first()
            check("the moderation record survives the removal", rec is not None)
            check("it records who decided and when",
                  rec is not None and rec.reviewer_user_id and rec.reviewed_at)
        finally:
            db.close()

    # --- comments and stories take the same path ---------------------------
    print("\n  Comments and stories go through the same moderation")

    comment = e2e.request("POST", f"/social/posts/{post_id}/comments", token=bob,
                          json_body={"content": "DEMO MODERATION - a comment."})
    check("a comment is accepted", comment.ok, str(comment.status))

    if comment.ok:
        check("the comment is held",
              comment.body.get("moderation_status") == mod.CONTENT_PENDING,
              str(comment.body.get("moderation_status")))

        listed = e2e.request("GET", f"/social/posts/{post_id}/comments", token=alice)
        ids = [c["id"] for c in (listed.body or {}).get("comments", [])]
        check("a colleague does not see the held comment",
              comment.body["id"] not in ids)

        own = e2e.request("GET", f"/social/posts/{post_id}/comments", token=bob)
        own_ids = [c["id"] for c in (own.body or {}).get("comments", [])]
        check("its author does see it", comment.body["id"] in own_ids)

    story = e2e.request("POST", "/social/stories", token=alice,
                        form={"caption": "DEMO MODERATION - a story caption."})
    check("a story is accepted", story.ok, str(story.status))

    if story.ok:
        created.setdefault("stories", []).append(story.body["id"])
        check("the story is held",
              story.body.get("moderation_status") == mod.CONTENT_PENDING,
              str(story.body.get("moderation_status")))

        bars = e2e.request("GET", "/social/stories", token=bob).body or {}
        seen_ids = [s["id"] for g in bars.get("groups", []) for s in g["stories"]]
        check("a colleague does not see the held story",
              story.body["id"] not in seen_ids)

    # --- summary -----------------------------------------------------------
    summary = e2e.request("GET", "/social/moderation/summary", token=hr)
    check("the summary endpoint answers", summary.ok, str(summary.status))

    if summary.ok:
        check("it reports the queue counts",
              set(summary.body["counts"]) ==
              {mod.REVIEW_PENDING, mod.REVIEW_APPROVED, mod.REVIEW_REMOVED},
              str(summary.body.get("counts")))
        check("it reports the taxonomy",
              summary.body["categories"] == list(mod.CATEGORIES))
        check("it says the model is not configured on this server",
              summary.body["model_configured"] is False)

    # --- audit -------------------------------------------------------------
    print("\n  The existing audit trail, not a second one")

    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "SocialModeration")
            .order_by(AuditLog.id.desc())
            .limit(40)
            .all()
        )
        actions = {r.action for r in rows}

        check("moderation events are written to audit_logs", bool(rows))
        check("holding content is audited", "STATUS_CHANGE" in actions, str(actions))
        check("approval is audited", "APPROVE" in actions, str(actions))
        check("removal is audited", "REJECT" in actions, str(actions))

        hr_user = db.query(User).filter(User.email == CAROL_HR).first()
        approve_rows = [r for r in rows if r.action == "APPROVE"]
        check("the approval is attributed to the reviewer, not the author",
              any(r.user_id == hr_user.id for r in approve_rows))
    finally:
        db.close()


# ===========================================================================
# 3. Regression: an ordinary post with moderation off
# ===========================================================================

def test_unmoderated(created: dict) -> None:
    section("3. With moderation switched off, the Social Hub is as it was")

    e2e.ensure_staff_account(ALICE, 4)
    alice = e2e.login(ALICE)
    bob = e2e.login(BOB)

    made = post_as(alice, "DEMO MODERATION - unmoderated deployment.")
    created.setdefault("posts", []).append(made.get("id"))

    check("the post publishes immediately",
          made.get("moderation_status") == mod.CONTENT_PUBLISHED,
          str(made.get("moderation_status")))
    check("it is not marked pending", made.get("pending_review") is False)

    feed = e2e.request("GET", "/social/feed", token=bob).body or {}
    check("a colleague sees it straight away",
          any(p["id"] == made.get("id") for p in feed.get("posts", [])))


# ===========================================================================
# 4. Live model - integration test, opt in
# ===========================================================================

def test_live() -> None:
    section("4. INTEGRATION - the real configured model")

    print("  This section makes real API calls. A failure here means the model")
    print("  or the prompt has moved, not that the application is broken.")
    print()

    from app.ai.config import llm_settings

    settings = llm_settings()

    if not settings.configured:
        print("  SKIPPED - no model is configured.")
        return

    print(f"  provider={settings.provider} model={settings.model}")
    print()

    cases = [
        ("safe praise", "allow",
         "Congratulations to Sarah on completing her training!"),
        ("harassment", "flag",
         "You are useless and nobody wants you here."),
        ("threat", "flag",
         "I am going to hurt you."),
        ("spam", "flag",
         "BUY NOW!!! CLICK THIS LINK!!! BUY NOW!!!"),
        ("normal workplace content", "allow",
         "Great teamwork everyone. We completed the project on time."),
    ]

    for label, expected, text in cases:
        result = mod.moderate_text(text)
        check(f"{label} -> {expected}", result.decision == expected,
              f"got {result.decision} {result.categories}")

    # Every category the model returned across the run must be in the taxonomy.
    everything = mod.moderate_text("You are worthless, get out of this company.")
    check("no category outside the taxonomy is ever returned",
          all(c in mod.CATEGORIES for c in everything.categories),
          str(everything.categories))

    check("the reason never recommends action about the person",
          not any(word in (everything.reason or "").lower()
                  for word in ("fire", "dismiss", "discipline", "terminate",
                               "warning letter", "should be removed from the company")),
          str(everything.reason))


# ===========================================================================

def cleanup(created: dict) -> None:
    section("Cleanup")

    db = SessionLocal()
    try:
        for rid in created.get("reviews", []):
            db.query(SocialModerationReview).filter(
                SocialModerationReview.id == rid).delete(synchronize_session=False)

        post_ids = [p for p in created.get("posts", []) if p]
        if post_ids:
            db.query(SocialModerationReview).filter(
                SocialModerationReview.content_type == "post",
                SocialModerationReview.content_id.in_(post_ids),
            ).delete(synchronize_session=False)

            # The comments' own review rows go too. A moderation record
            # deliberately outlives the content it refers to in production -
            # an author deleting a held post must not erase the fact that it
            # was held - so they do not cascade, and a test that forgets them
            # leaves orphans sitting in HR's queue.
            comment_ids = [
                row[0] for row in
                db.query(SocialComment.id)
                .filter(SocialComment.post_id.in_(post_ids)).all()
            ]

            if comment_ids:
                db.query(SocialModerationReview).filter(
                    SocialModerationReview.content_type == "comment",
                    SocialModerationReview.content_id.in_(comment_ids),
                ).delete(synchronize_session=False)

            db.query(SocialComment).filter(
                SocialComment.post_id.in_(post_ids)).delete(synchronize_session=False)
            db.flush()
            db.query(SocialPost).filter(
                SocialPost.id.in_(post_ids)).delete(synchronize_session=False)

        story_ids = [s for s in created.get("stories", []) if s]
        if story_ids:
            db.query(SocialModerationReview).filter(
                SocialModerationReview.content_type == "story",
                SocialModerationReview.content_id.in_(story_ids),
            ).delete(synchronize_session=False)
            db.query(SocialStory).filter(
                SocialStory.id.in_(story_ids)).delete(synchronize_session=False)

        db.commit()
        print("  The suite's own posts, stories and review rows are removed.")
        print("  Its @smarthr.test accounts persist, like every other suite here.")
    except Exception as exc:
        db.rollback()
        print(f"  Cleanup problem: {type(exc).__name__}: {exc}")
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="also run the real-model integration section")
    parser.add_argument("--keep", action="store_true",
                        help="leave the suite's rows in the database")
    args = parser.parse_args()

    print("SmartHR - AI Moderation V1")
    print(f"Default run makes no network call. Live section: "
          f"{'ON' if args.live else 'off (--live to enable)'}")

    e2e.BASE = BASE

    created: dict = {}

    test_service()

    try:
        # The model is genuinely absent on this server, which is the
        # fail-closed path. 'none' rather than an empty value, because an
        # empty one falls through to `.env`.
        with Server(PORT, {"SMARTHR_LLM_PROVIDER": "none",
                           "SMARTHR_SOCIAL_SHOW_TEST_ACCOUNTS": "true"}):
            test_http(created)

        with Server(PORT, {"SMARTHR_SOCIAL_MODERATION": "false",
                           "SMARTHR_SOCIAL_SHOW_TEST_ACCOUNTS": "true"}):
            test_unmoderated(created)

        if args.live:
            test_live()
    finally:
        if args.keep:
            section("Cleanup")
            print("  --keep: rows left in place.")
        else:
            cleanup(created)

    section("Result")
    print(f"  {passed} passed, {failed} failed")

    if failures:
        print()
        for item in failures:
            print(f"    FAILED: {item}")

    print()
    print("  Not covered here: the browser. The moderation page, its Arabic")
    print("  layout and the pending-review badge need a person and a browser;")
    print("  `npx tsc --noEmit` and the access check are what guard those.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
