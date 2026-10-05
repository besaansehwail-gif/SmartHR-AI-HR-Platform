from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import settings

from app.routers.employees import router as employees_router
from app.routers.departments import router as departments_router
from app.routers.positions import router as positions_router
from app.routers.jobs import router as jobs_router
from app.routers.candidates import router as candidates_router
from app.routers.applications import router as applications_router
from app.routers.interviews import router as interviews_router
from app.routers.cvs import router as cvs_router
from app.routers.attendance import router as attendance_router
from app.routers.leave_requests import router as leave_requests_router
from app.routers.trainings import router as trainings_router
from app.routers.employee_trainings import router as employee_trainings_router
from app.routers.performance_reviews import router as performance_reviews_router
from app.routers.notifications import router as notifications_router
from app.routers.audit_logs import router as audit_logs_router
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.dashboard import router as dashboard_router
from app.routers.ai import router as ai_router
from app.routers.applicant import router as applicant_router
from app.routers.career_agent import router as career_agent_router
from app.routers.hr_agent import router as hr_agent_router
from app.routers.social import router as social_router
from app.routers.celebrations import router as celebrations_router
from app.routers.ai_interview import router as ai_interview_router
from app.routers.interview_questions import router as interview_questions_router


app = FastAPI(
    title="SmartHR API",
    description="Human Resources Management System API",
    version="1.0.0"
)


# Phase 10: SMARTHR_CORS_ORIGINS (app/settings.py). Unset in development is
# "*", as before; production must name its frontend origin(s), https only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "SmartHR Backend is running!"
    }


app.include_router(employees_router)
app.include_router(departments_router)
app.include_router(positions_router)
app.include_router(jobs_router)
app.include_router(candidates_router)
app.include_router(applications_router)
app.include_router(interviews_router)
app.include_router(cvs_router)
app.include_router(attendance_router)
app.include_router(leave_requests_router)
app.include_router(trainings_router)
app.include_router(employee_trainings_router)
app.include_router(performance_reviews_router)
app.include_router(notifications_router)
app.include_router(audit_logs_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(dashboard_router)
app.include_router(ai_router)

# The Applicant / Job Seeker surface. Registered last because the Career
# Agent router mounts under /applicant/agent, and FastAPI matches in
# registration order - the agent's literal prefix must not be shadowed by
# /applicant/{...} paths.
app.include_router(career_agent_router)
app.include_router(applicant_router)

# The Internal HR Agent. Its own prefix (/hr/agent), so there is no
# ordering constraint against another router the way there is between
# the Career Agent and /applicant/{...}.
app.include_router(hr_agent_router)

# The Social Hub. Its own /social prefix, so it collides with nothing, and
# every route inside it carries require_staff (roles 1-4) - an Applicant is
# refused by the router's own dependency, not by the frontend hiding a link.
app.include_router(social_router)

# AI Employee Celebration - the Social Hub's three-agent LangGraph workflow.
# Registered after the Social Hub and declared with its own longer literal
# prefix (/social/celebration), so it matches before nothing and after
# nothing: the Social Hub declares no /social/{something} catch-all. It is
# guarded more narrowly than the Social Hub itself - roles 1-2, because it
# reads employee records - which is why it is its own router.
app.include_router(celebrations_router)

# AI Interview - the LiveKit voice interviewer. Its own /ai-interview prefix,
# deliberately apart from the recruitment /interviews/{interview_id} API, so
# neither can shadow the other. The agent itself is a separate process
# (app/ai/interview/worker.py); this router only authorises and mints tokens.
app.include_router(ai_interview_router)
# The Question Bank's HR management API - Admin + HR only, a stricter guard
# than the applicant-facing routes above, so it is its own router. Its own
# literal prefix (/ai-interview/questions), so neither router shadows the other.
app.include_router(interview_questions_router)