"""The worker's one call to the backend: "what is this room's interview?"

    worker --(agent token, signed with the LiveKit secret)--> POST /ai-interview/agent/plan
           <-- ordered MAIN questions from the Question Bank
                   + the trimmed Job Context (Phase 4) + stored STT language --

The worker names only the room (inside the signed token). WHICH interview and
job that room belongs to is decided by the backend from its own binding - the
worker cannot ask for a different job, and neither can the browser.

The worker does not read the database and does not choose questions. It asks
the backend once per room, at the start, and the controller then walks that
list in order. If the backend cannot be reached, or answers with something
that is not a usable plan, the result is an EMPTY plan - and the controller
ends the session politely rather than letting GPT-4o improvise an interview.

Two more calls follow in the background, with the same token and the same
room binding: the CV Context (Phase 5, `fetch_cv`) and the Matching Context
(Phase 6, `fetch_matching`) - three fields of SmartHR's existing matching
result for the room's candidate and job. Neither is required: without them
the interview goes ahead on the Question Bank and the Job Context.

The response is validated here rather than trusted: ids must be integers,
texts non-empty and within the bank's own length limit, the language must
be `en`, `ar` or absent for legacy fallback, and the job block must parse
(`job_context.parse_job`). No job, no interview.
"""

import logging
from dataclasses import dataclass

import aiohttp

from app.ai.interview.agent_auth import mint_agent_token
from app.ai.interview.config import backend_url, voice_settings
from app.ai.interview.cv_context import CvContext, CvContextInvalid, parse_cv_context
from app.ai.interview.job_context import JobContext, JobContextInvalid, parse_job
from app.ai.interview.matching_context import (
    MatchingContext,
    MatchingContextInvalid,
    parse_matching_context,
)
from app.ai.interview.questions import PlannedQuestion

logger = logging.getLogger("smarthr.interview.plan")

TIMEOUT_S = 10
#: The CV is parsed by a model on the backend; the backend itself waits up to
#: 45 s for that, so the worker allows a little more.
CV_TIMEOUT_S = 60
MAX_TEXT = 500


class PlanUnavailable(Exception):
    pass


@dataclass(frozen=True)
class InterviewPlan:
    questions: list[PlannedQuestion]
    job: JobContext
    language: str | None


def parse_interview(payload: dict, room_name: str) -> InterviewPlan:
    if not isinstance(payload, dict) or payload.get("room_name") != room_name:
        raise PlanUnavailable("plan is for a different room")
    language = payload.get("language")
    if language is not None and (not isinstance(language, str) or language not in {"en", "ar"}):
        raise PlanUnavailable("plan language is invalid")
    questions = parse_plan(payload, room_name)
    try:
        job = parse_job(payload.get("job"))
    except JobContextInvalid as exc:
        raise PlanUnavailable(f"job context unusable: {exc}") from None
    return InterviewPlan(questions, job, language)


def parse_plan(payload: dict, room_name: str) -> list[PlannedQuestion]:
    if not isinstance(payload, dict) or payload.get("room_name") != room_name:
        raise PlanUnavailable("plan is for a different room")
    items = payload.get("questions")
    if not isinstance(items, list):
        raise PlanUnavailable("plan has no question list")
    plan = []
    for item in items:
        try:
            qid = int(item["id"])
            text = " ".join(str(item["question_text"]).split())
            position = int(item.get("position", 0))
            category = str(item.get("category", "general"))
        except (KeyError, TypeError, ValueError):
            raise PlanUnavailable("malformed question in plan") from None
        if not text or len(text) > MAX_TEXT:
            raise PlanUnavailable("question text missing or too long")
        plan.append(PlannedQuestion(qid, position, category, text,
                                    follow_up=parse_follow_up(item.get("follow_up"), qid, room_name)))
    return plan


def parse_follow_up(raw, parent_id: int, room_name: str) -> PlannedQuestion | None:
    """Phase 11.1: a main question's predefined follow-up, or None.

    Accepted only when it is well formed AND names this main question as its
    parent. Anything else is dropped (and logged by id) - the interview then
    simply has no follow-up for that question; it is never a reason to stop.
    """
    if raw is None:
        return None
    try:
        fid = int(raw["id"])
        parent = int(raw["parent_question_id"])
        text = " ".join(str(raw["question_text"]).split())
    except (KeyError, TypeError, ValueError):
        logger.warning("room=%s follow-up for question id=%s dropped: malformed", room_name, parent_id)
        return None
    if parent != parent_id or fid == parent_id:
        logger.warning("room=%s follow-up id=%s dropped: its parent is not question id=%s",
                       room_name, fid, parent_id)
        return None
    if not text or len(text) > MAX_TEXT:
        logger.warning("room=%s follow-up id=%s dropped: text missing or too long", room_name, fid)
        return None
    return PlannedQuestion(fid, int(raw.get("position", 0) or 0), "follow_up", text)


async def fetch_plan(room_name: str) -> InterviewPlan:
    settings = voice_settings()
    if not settings.configured:
        raise PlanUnavailable("LiveKit credentials not configured")
    token = mint_agent_token(settings.api_key, settings.api_secret, room_name)
    url = f"{backend_url()}/ai-interview/agent/plan"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)) as http:
            async with http.post(url, headers={"Authorization": f"Bearer {token}"}) as resp:
                if resp.status != 200:
                    raise PlanUnavailable(f"backend answered HTTP {resp.status}")
                payload = await resp.json()
    except PlanUnavailable:
        raise
    except Exception as exc:
        raise PlanUnavailable(f"backend unreachable ({type(exc).__name__})") from None
    plan = parse_interview(payload, room_name)
    # Ids and counts only - the job title is not personal, but the log keeps
    # to one rule everywhere rather than deciding field by field.
    logger.info("room=%s plan received: %d questions (ids %s, follow-ups %s), job context job_id=%s "
                "(%d requirements)", room_name, len(plan.questions),
                [q.id for q in plan.questions],
                {q.id: q.follow_up.id for q in plan.questions if q.follow_up},
                plan.job.job_id, len(plan.job.requirements))
    return plan


def parse_cv_response(payload: dict, room_name: str) -> CvContext | None:
    if not isinstance(payload, dict) or payload.get("room_name") != room_name:
        raise PlanUnavailable("CV context is for a different room")
    try:
        return parse_cv_context(payload.get("cv"))
    except CvContextInvalid as exc:
        raise PlanUnavailable(f"CV context unusable: {exc}") from None


async def fetch_cv(room_name: str) -> CvContext | None:
    """The room candidate's CV Context (Phase 5), or None if they have no
    usable CV. Same agent token, same backend, same room binding as the plan.
    Raises PlanUnavailable when it cannot be fetched; the interview then
    simply continues without CV facts."""
    settings = voice_settings()
    if not settings.configured:
        raise PlanUnavailable("LiveKit credentials not configured")
    token = mint_agent_token(settings.api_key, settings.api_secret, room_name)
    url = f"{backend_url()}/ai-interview/agent/cv"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=CV_TIMEOUT_S)) as http:
            async with http.post(url, headers={"Authorization": f"Bearer {token}"}) as resp:
                if resp.status != 200:
                    raise PlanUnavailable(f"backend answered HTTP {resp.status}")
                payload = await resp.json()
    except PlanUnavailable:
        raise
    except Exception as exc:
        raise PlanUnavailable(f"backend unreachable ({type(exc).__name__})") from None
    cv = parse_cv_response(payload, room_name)
    # Counts only - never a CV value.
    logger.info("room=%s CV context received: %s", room_name,
                f"no CV context (backend status: {payload['cv'].get('status')})" if cv is None else
                f"{len(cv.skills)} skills, {len(cv.experience)} roles, {len(cv.education)} education, "
                f"{len(cv.certifications)} certifications")
    return cv


def parse_matching_response(payload: dict, room_name: str) -> MatchingContext | None:
    if not isinstance(payload, dict) or payload.get("room_name") != room_name:
        raise PlanUnavailable("matching context is for a different room")
    try:
        return parse_matching_context(payload.get("matching"))
    except MatchingContextInvalid as exc:
        raise PlanUnavailable(f"matching context unusable: {exc}") from None


async def fetch_matching(room_name: str) -> MatchingContext | None:
    """SmartHR's existing matching result for the room's candidate and job
    (Phase 6), or None when there is none. The backend waits for the same CV
    parse the CV Context used, so this shares the CV's timeout. Raises
    PlanUnavailable when it cannot be fetched; the interview then continues
    without matching."""
    settings = voice_settings()
    if not settings.configured:
        raise PlanUnavailable("LiveKit credentials not configured")
    token = mint_agent_token(settings.api_key, settings.api_secret, room_name)
    url = f"{backend_url()}/ai-interview/agent/matching"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=CV_TIMEOUT_S)) as http:
            async with http.post(url, headers={"Authorization": f"Bearer {token}"}) as resp:
                if resp.status != 200:
                    raise PlanUnavailable(f"backend answered HTTP {resp.status}")
                payload = await resp.json()
    except PlanUnavailable:
        raise
    except Exception as exc:
        raise PlanUnavailable(f"backend unreachable ({type(exc).__name__})") from None
    matching = parse_matching_response(payload, room_name)
    # Counts only - never a skill, never the score.
    logger.info("room=%s matching context received: %s", room_name,
                f"none (backend status: {payload['matching'].get('status')})" if matching is None else
                f"{len(matching.matching_skills)} matching skills, {len(matching.skill_gaps)} gaps")
    return matching
