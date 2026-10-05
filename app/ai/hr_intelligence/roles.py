"""The four AI roles, their responsibilities and their boundaries (Phase 12).

This is a statement of the architecture, and it is enforced, not decorative:
`scripts/test_ai_interview_multi_agent.py` checks each boundary against the
code (imports, model use, what each role can write, what it outputs).

Model use is separated by purpose - one provider, three uses:

* ``live_conversation``      GPT-4o through LiveKit Inference, in the worker
                             process, during the interview only;
* ``post_interview_analysis`` GPT-4o through `app/ai/provider.py`, one tool
                             call per stored answer, after it is stored;
* ``none``                   deterministic code over stored data - the Report
                             and Recruitment roles make NO model call, which
                             is what makes "never invents evidence" and
                             "never recalculates the match" structural.
"""

from dataclasses import dataclass

LIVE_CONVERSATION = "live_conversation"
POST_INTERVIEW_ANALYSIS = "post_interview_analysis"
NO_MODEL = "none"

PRE_INTERVIEW = "pre_interview"
LIVE = "live"
POST_INTERVIEW = "post_interview"


@dataclass(frozen=True)
class AgentRole:
    name: str
    stage: str
    model_use: str
    modules: tuple[str, ...]          # where the role is implemented
    receives: tuple[str, ...]         # the structured inputs it is given
    produces: tuple[str, ...]
    writes: tuple[str, ...]           # tables it may write - nothing else
    responsibilities: tuple[str, ...]
    never: tuple[str, ...]


INTERVIEWER = AgentRole(
    name="interviewer",
    stage=LIVE,
    model_use=LIVE_CONVERSATION,
    modules=("app.ai.interview.worker", "app.ai.interview.controller", "app.ai.interview.agent"),
    receives=("question_bank_plan", "job_context", "cv_context", "matching_context"),
    produces=("spoken_questions", "final_answers", "progress_reports"),
    # Through the backend's agent endpoints only - the worker has no database.
    writes=("ai_interview_answers", "interviews.status"),
    responsibilities=(
        "owns the live conversation", "asks Question Bank questions verbatim",
        "turn-taking", "predefined follow-ups (yes/no)", "adaptive order (bank ids only)",
        "ends the interview",
    ),
    never=("analyse answers for HR", "build the HR report", "state a score or hiring decision"),
)

ANALYST = AgentRole(
    name="analysis",
    stage=POST_INTERVIEW,
    model_use=POST_INTERVIEW_ANALYSIS,
    modules=("app.ai.interview_analysis", "app.services.interview_analysis_service"),
    receives=("question", "transcript", "earlier_parts", "job_context", "cv_context",
              "matching_skills", "skill_gaps"),
    produces=("addresses_question", "summary", "evidence", "skills_mentioned",
              "job_requirements_referenced", "cv_relation", "specificity", "clarity", "not_covered"),
    writes=("ai_interview_answer_analyses",),
    responsibilities=(
        "analyses stored answers after they are stored", "extracts factual evidence (quoted)",
        "skills the applicant mentioned", "relates answers to job requirements and the CV",
        "identifies uncovered areas",
    ),
    never=("control the live interview", "see the match score", "state a score or hiring decision"),
)

REPORTER = AgentRole(
    name="report",
    stage=POST_INTERVIEW,
    model_use=NO_MODEL,
    modules=("app.ai.hr_intelligence.report_agent", "app.services.interview_report_service"),
    receives=("interview_report",),
    produces=("hr_brief",),
    writes=(),
    responsibilities=(
        "turns the stored report and analyses into an HR-readable brief",
        "every quote and summary copied from stored analysis, with its answer sequence",
    ),
    never=("invent evidence", "call a model", "score, rank or recommend"),
)

RECRUITER = AgentRole(
    name="recruitment",
    stage=POST_INTERVIEW,
    model_use=NO_MODEL,
    modules=("app.ai.hr_intelligence.matching_agent", "app.services.interview_matching_service"),
    receives=("job_title", "requirements", "matching_status", "matching_skills", "skill_gaps"),
    produces=("matching_explanation",),
    writes=(),
    responsibilities=(
        "explains SmartHR's existing matching result: which skills matched, which requirements "
        "were not evidenced",
    ),
    never=("recalculate or override the match", "show the score", "make a hiring decision"),
)

ROLES = (INTERVIEWER, ANALYST, REPORTER, RECRUITER)

#: The post-interview pipeline, in order. The interviewer is not in it: it is
#: never invoked after the interview, and nothing here can reach it.
POST_INTERVIEW_ORDER = (ANALYST.name, REPORTER.name, RECRUITER.name)
