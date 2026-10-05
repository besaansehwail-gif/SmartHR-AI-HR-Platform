"""Which roles may run which MCP tool.

This is the whole authorisation model for the MCP layer, and it is enforced in
`authorise()` - which re-reads `users.role_id` **from the database** rather
than trusting the role carried on the principal, the JWT claim, or anything the
frontend sent. That is the same rule `app/dependencies.require_roles` applies
to the REST API, for the same reason: a token can be stale or forged, a row
cannot.

`scope` records what a tool's handler is obliged to filter on, so the intent is
written down next to the permission rather than living only in the query:

    self          the caller's own employees row, resolved from the principal
    team          employees whose manager_id is the caller's employees row
    organisation  every row; HR and Admin tools only

Adding a tool means adding a `ToolPolicy` here and a `@smarthr_mcp.tool()` in
`app/mcp/tools/`. Nothing else in the stack needs to change.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import User

SCOPE_SELF = "self"
SCOPE_TEAM = "team"
SCOPE_ORG = "organisation"
#: Published internal documents rather than anybody's records. Every signed-in
#: role may read them; there is no per-person filtering to do, which is exactly
#: why it is its own scope rather than being lumped in with `organisation`.
SCOPE_KNOWLEDGE = "knowledge"
#: Published openings - jobs, internships, trainings and courses that are on
#: offer. Like `knowledge` there is no per-person filtering to do, but it is
#: its own scope because the filtering obligation is different: a handler must
#: return the *public projection* of a job, never the recruitment view of it.
SCOPE_OPPORTUNITIES = "opportunities"
#: Recruitment records - requisitions, candidates, applications and CVs -
#: read across the whole organisation. It is `organisation` scope with a name
#: that says which records, because the filtering obligation is specific: a
#: handler must return the *recruiter's* projection (no interview notes, no
#: interviewer identity) and must never expose an employee's own HR data
#: through a recruitment tool.
SCOPE_RECRUITMENT = "recruitment"

# Role ids as seeded in the database:
#   1 Admin, 2 HR, 3 Manager, 4 Employee   - internal staff
#   5 Applicant                            - an external job seeker
ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_EMPLOYEE = 1, 2, 3, 4
ROLE_APPLICANT = 5


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    allowed_roles: tuple[int, ...]
    scope: str


#: Every MCP tool SmartHR exposes must appear here. A tool with no policy is
#: refused by `authorise()` rather than defaulting to allowed.
TOOL_POLICIES: dict[str, ToolPolicy] = {
    # Self-service: everyone has their own leave, including an Admin - being
    # an administrator does not stop you being a person who takes holiday.
    "get_my_leave": ToolPolicy(
        name="get_my_leave",
        allowed_roles=(ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_EMPLOYEE),
        scope=SCOPE_SELF,
    ),
    # Recruitment: a CV is organisation-scoped HR data, readable by the same
    # roles that may already call GET /cvs/. The tool takes a cv_id or
    # candidate_id to choose a *subject*; that is not an identity claim, and
    # the caller is still the principal. Manager and Employee are refused.
    "parse_cv": ToolPolicy(
        name="parse_cv",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_ORG,
    ),
    # HR policy documents. Everyone may read published policy - an employee
    # needs to know the leave rules as much as HR does. The tool returns
    # document passages, never anybody's records, so there is no personal data
    # to scope.
    "search_hr_policies": ToolPolicy(
        name="search_hr_policies",
        allowed_roles=(ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_EMPLOYEE),
        scope=SCOPE_KNOWLEDGE,
    ),
    # --- Career Agent: the Applicant's tools --------------------------------
    #
    # Every one of these is role 5 and role 5 only. That is not an oversight
    # about Admin: these tools answer "my profile", "my CV", "my applications"
    # for an *external job seeker*, and an Admin calling them would resolve to
    # a candidates row that does not exist. HR reads applicant data through the
    # recruitment endpoints they already have, which are richer and audited.
    #
    # Note what none of them declare: a candidate_id, a user_id or an email.
    # The subject is always the bound principal, so the Career Agent's model
    # has no argument through which it could ask about a different person -
    # the same design as `get_my_leave`.
    "get_my_profile": ToolPolicy(
        name="get_my_profile",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_SELF,
    ),
    "get_my_cv": ToolPolicy(
        name="get_my_cv",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_SELF,
    ),
    "get_my_applications": ToolPolicy(
        name="get_my_applications",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_SELF,
    ),
    "get_my_application_status": ToolPolicy(
        name="get_my_application_status",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_SELF,
    ),
    "match_my_profile_to_opportunity": ToolPolicy(
        name="match_my_profile_to_opportunity",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_SELF,
    ),
    # The catalogue. Public information about what is on offer, so there is no
    # personal data to scope - but the handler is still obliged to return the
    # applicant-facing projection, never `job_to_dict()`.
    "search_opportunities": ToolPolicy(
        name="search_opportunities",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_OPPORTUNITIES,
    ),
    "get_opportunity": ToolPolicy(
        name="get_opportunity",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_OPPORTUNITIES,
    ),
    # The only Career Agent tool that writes anything, and the only write tool
    # in the whole MCP surface. It creates one `applications` row for the bound
    # principal. It cannot change a status, cannot touch another candidate, and
    # cannot hire or reject anybody - those verbs have no tool.
    "submit_application": ToolPolicy(
        name="submit_application",
        allowed_roles=(ROLE_APPLICANT,),
        scope=SCOPE_SELF,
    ),

    # --- Internal HR Agent: the recruiter's tools ---------------------------
    #
    # Admin and HR only, matching `GET /candidates/`, `GET /applications/` and
    # `GET /cvs/`, which are already `require_roles(1, 2)`. **Manager is
    # deliberately absent.** A Manager may read their own team's attendance,
    # leave and performance, but recruitment is HR-owned in SmartHR's existing
    # access tiers and no rule there gives a Manager the candidate pipeline -
    # so giving their agent one would have widened access through the AI layer
    # that the REST layer refuses. Employee and Applicant are absent for the
    # same reason, more obviously.
    #
    # Every one of these reads. There is no HR Agent tool that writes, and
    # that is the structural reason the agent cannot hire, reject, advance or
    # withdraw anybody: not a rule the model is asked to follow, but a verb it
    # has no way to express. Moving a candidate through the pipeline stays
    # `PATCH /applications/{id}/status` in the Recruitment UI.
    #
    # These tools take ids - a job_id, a candidate_id - and that is not an
    # identity claim. Recruitment is organisation-scoped data this role may
    # already read in full, exactly as `parse_cv` takes a candidate_id. Who is
    # *asking* still comes from the bound principal, and `authorise()` still
    # re-reads the role from `users` before any handler runs, so a Manager or
    # Employee reaching one of these is refused whatever id they pass.
    "search_jobs": ToolPolicy(
        name="search_jobs",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "get_job": ToolPolicy(
        name="get_job",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "get_job_requirements": ToolPolicy(
        name="get_job_requirements",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "search_candidates": ToolPolicy(
        name="search_candidates",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "get_candidate": ToolPolicy(
        name="get_candidate",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "get_candidate_cv": ToolPolicy(
        name="get_candidate_cv",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "search_applications": ToolPolicy(
        name="search_applications",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "get_application": ToolPolicy(
        name="get_application",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "match_candidate_to_job": ToolPolicy(
        name="match_candidate_to_job",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),
    "rank_candidates_for_job": ToolPolicy(
        name="rank_candidates_for_job",
        allowed_roles=(ROLE_ADMIN, ROLE_HR),
        scope=SCOPE_RECRUITMENT,
    ),

    # --- Extension points for the next phases -------------------------------
    # The shape each future tool takes is already decided; only the handler is
    # missing. Uncomment alongside its @smarthr_mcp.tool() registration.
    #
    # "get_my_attendance":   SCOPE_SELF, all roles
    # "get_my_training":     SCOPE_SELF, all roles
    # "get_my_performance":  SCOPE_SELF, all roles
    # "get_my_profile":      SCOPE_SELF, all roles
    # "get_team_attendance": SCOPE_TEAM, (ADMIN, HR, MANAGER)
    # "get_team_leave":      SCOPE_TEAM, (ADMIN, HR, MANAGER)
    # "search_employees":    SCOPE_ORG,  (ADMIN, HR)
    # "get_recruitment_status": SCOPE_ORG, (ADMIN, HR)
    # "get_workforce_insights": SCOPE_ORG, (ADMIN, HR)
}


class ToolNotPermitted(Exception):
    """The caller's role may not run this tool."""

    def __init__(self, message: str, code: str = "forbidden"):
        super().__init__(message)
        self.code = code


def policy_for(tool_name: str) -> ToolPolicy | None:
    return TOOL_POLICIES.get(tool_name)


def tools_for_role(role_id: int | None) -> list[str]:
    """Tool names this role may run.

    Used to filter the list handed to the language model, so a model is never
    shown a capability its caller could not use. It is a convenience, not the
    boundary - `authorise()` is the boundary.
    """
    if role_id is None:
        return []

    return [
        policy.name
        for policy in TOOL_POLICIES.values()
        if role_id in policy.allowed_roles
    ]


def authorise(tool_name: str, user_id: int, db: Session) -> User:
    """Check the caller may run this tool, and return their current account.

    The role is read from `users` here and nowhere else. Raises
    `ToolNotPermitted` with a code: `unknown_tool`, `unknown_account`,
    `inactive_account`, `forbidden`.
    """
    policy = policy_for(tool_name)

    if policy is None:
        raise ToolNotPermitted(
            f"'{tool_name}' is not a SmartHR tool.", code="unknown_tool"
        )

    account = db.query(User).filter(User.id == user_id).first()

    if account is None:
        raise ToolNotPermitted(
            "This account no longer exists.", code="unknown_account"
        )

    if not account.is_active:
        raise ToolNotPermitted(
            "This account is not active.", code="inactive_account"
        )

    if account.role_id not in policy.allowed_roles:
        raise ToolNotPermitted(
            f"Your role does not have permission to use '{tool_name}'.",
            code="forbidden",
        )

    return account
