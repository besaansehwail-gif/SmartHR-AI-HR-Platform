# -*- coding: utf-8 -*-
"""Ten Applicant test accounts, their candidate profiles and a CV each.

    venv\\Scripts\\python.exe -m scripts.create_applicant_test_accounts
    venv\\Scripts\\python.exe -m scripts.create_applicant_test_accounts --dry-run
    venv\\Scripts\\python.exe -m scripts.create_applicant_test_accounts --verify
    venv\\Scripts\\python.exe -m scripts.create_applicant_test_accounts --parse

QA fixtures for the applicant half of SmartHR: sign-in, the dashboard, CV
upload, the AI CV parser, matching, applications and reports.
Ten different profiles, because a matcher tested against one candidate tells
you nothing about skill gaps.

**Nothing here is a second implementation.** The account is hashed with the
same `password_hash` the login route verifies against, the candidate row is
created by `link_candidate_profile()` - the one definition of that link, which
registration and Admin user management also call - and the CV bytes go through
`cv_storage.store_cv_file()`, so the row and the file on disk are exactly what
`POST /cvs/upload` produces. A CV created here is indistinguishable from an
uploaded one.

**DOCX, not PDF.** `python-docx` can write a document and `pypdf` can only
read one, and there is no PDF writer in the venv. `cv_extraction` accepts both
and detects the type from the file's **signature**, so a DOCX exercises the
same path a real upload does - which is why the fixtures here already
builds its test CV this way. Adding a PDF-writing dependency to produce a file
the pipeline treats identically would buy nothing.

**Nothing is faked.** No parsed CV field, no match score and no analysis result
is written to the database: those are what the QA run is for, and a stored
answer would make the test pass by describing itself. `--parse` runs the real
`analyse_cv_bytes()` against each file and reports what came back.

**Idempotent, and narrow.** Every write is keyed on one of the ten
`@smarthr.test` addresses; the script refuses to run if that is ever not true,
and it never reads, updates or deletes rows outside those fixtures. Run it twice
and the second run reports ten skips.

Set `TEST_ACCOUNT_PASSWORD=<LOCAL_TEST_PASSWORD>` in your local environment
before running this script, replacing the placeholder locally. Do not store
test credentials in source control.
"""

import argparse
import io
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.cv_storage import CV_UPLOAD_DIR, PROJECT_ROOT, display_filename, store_cv_file
from app.database import SessionLocal
from app.models import CV, Candidate, Role, User
from app.services.applicant_service import ROLE_APPLICANT, link_candidate_profile

def _test_account_password() -> str:
    """Return the locally configured password for generated test accounts."""
    password = os.environ.get("TEST_ACCOUNT_PASSWORD", "")
    if not password:
        raise SystemExit(
            "Set TEST_ACCOUNT_PASSWORD in your local environment before running."
        )
    return password


#: Every generated address uses this reserved test-only domain.
TEST_DOMAIN = "@smarthr.test"

@dataclass(frozen=True)
class Profile:
    """One synthetic applicant: the account, the candidate row and the CV."""

    number: int
    role_title: str
    location: str
    phone: str
    #: Goes into `candidates.skills`, comma-separated - the applicant's own
    #: words, which is what matching reads. Deliberately *not* the same list
    #: as the CV mentions for every profile, so a skills-vs-CV difference is
    #: testable.
    skills: list[str]
    summary: str
    education: list[str]
    experience: list[str]
    projects: list[str]
    certifications: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["English", "Arabic"])

    @property
    def email(self) -> str:
        return f"applicant{self.number:02d}{TEST_DOMAIN}"

    @property
    def full_name(self) -> str:
        return f"Applicant Test {self.number:02d}"

    @property
    def first_name(self) -> str:
        return "Applicant"

    @property
    def last_name(self) -> str:
        return f"Test {self.number:02d}"

    @property
    def cv_filename(self) -> str:
        return f"applicant{self.number:02d}_cv.docx"


# ===========================================================================
# The ten profiles
#
# Different on every axis the parser and the matcher read: job family, skills,
# years, education, projects and certifications. Several carry a deliberate
# gap - 01 has no cloud or engineering experience, 07 has no Kubernetes, 09 has
# no certification - so "missing skills" is something a run can actually show
# rather than something the fixtures make impossible.
# ===========================================================================

PROFILES: list[Profile] = [
    Profile(
        number=1,
        role_title="Junior Data Analyst",
        location="Amman, Jordan",
        phone="+1-202-555-0100",
        skills=["Python", "SQL", "Excel", "Power BI", "Statistics"],
        summary=(
            "Junior data analyst with one year of reporting experience. "
            "Comfortable turning a spreadsheet process into a query and a "
            "dashboard. Looking for a first full analytics role."
        ),
        education=["BSc Statistics, University of Jordan, 2024"],
        experience=[
            "Data Analyst Intern, Levant Retail Group (2024-2025). Rebuilt the "
            "weekly sales report in SQL and Power BI, replacing a manual Excel "
            "workbook that took a day to assemble.",
            "Teaching Assistant, Statistics Department (2023-2024). Ran lab "
            "sessions on descriptive statistics and hypothesis testing.",
        ],
        projects=[
            "Retail basket analysis in Python and pandas over 40,000 synthetic "
            "transactions, presented as a Power BI dashboard.",
        ],
        certifications=["Microsoft Power BI Data Analyst (PL-300), 2025"],
    ),
    Profile(
        number=2,
        role_title="Frontend Developer",
        location="Dubai, United Arab Emirates",
        phone="+1-202-555-0101",
        skills=["React", "TypeScript", "JavaScript", "HTML", "CSS", "REST APIs"],
        summary=(
            "Frontend developer with three years building product interfaces "
            "in React and TypeScript. Particular interest in accessibility and "
            "in design systems that survive more than one team."
        ),
        education=["BSc Computer Science, American University of Sharjah, 2022"],
        experience=[
            "Frontend Developer, Mirage Software (2023-2026). Owned the "
            "component library for a customer portal used by 12,000 accounts; "
            "moved it from JavaScript to TypeScript over two quarters.",
            "Junior Developer, Bayt Digital (2022-2023). Built marketing sites "
            "in HTML, CSS and vanilla JavaScript.",
        ],
        projects=[
            "An open-source React table component with keyboard navigation and "
            "screen-reader labelling, published to npm.",
            "A REST API client generator that produces typed hooks from an "
            "OpenAPI document.",
        ],
    ),
    Profile(
        number=3,
        role_title="Backend Developer",
        location="Cairo, Egypt",
        phone="+1-202-555-0102",
        skills=["Python", "FastAPI", "PostgreSQL", "REST APIs", "Docker"],
        summary=(
            "Backend developer with four years on Python services, mostly "
            "FastAPI against PostgreSQL. Comfortable owning a schema, its "
            "migrations and the queries that read it."
        ),
        education=["BSc Computer Engineering, Cairo University, 2021"],
        experience=[
            "Backend Developer, Nile Logistics Platform (2022-2026). Designed "
            "and maintained the shipment tracking API; cut p95 latency from "
            "800ms to 120ms by adding two composite indexes and removing an "
            "N+1 in the consignment serializer.",
            "Software Engineer, Delta Systems (2021-2022). Built internal REST "
            "services and containerised the deployment with Docker.",
        ],
        projects=[
            "A rate-limiting middleware for FastAPI backed by Redis, used "
            "across four internal services.",
        ],
        certifications=["AWS Certified Developer - Associate, 2024"],
    ),
    Profile(
        number=4,
        role_title="QA Engineer",
        location="Riyadh, Saudi Arabia",
        phone="+1-202-555-0103",
        skills=[
            "Manual Testing",
            "Test Cases",
            "Bug Reporting",
            "SQL",
            "API Testing",
            "Postman",
        ],
        summary=(
            "QA engineer with three years of manual and API testing on "
            "regulated financial software. Writes test cases other people can "
            "run, and bug reports that reproduce."
        ),
        education=["BSc Information Systems, King Saud University, 2022"],
        experience=[
            "QA Engineer, Tadawul Fintech (2023-2026). Owned the regression "
            "suite for a payments product: 400 manual cases, plus API checks "
            "in Postman run before every release.",
            "QA Analyst, Najd Software House (2022-2023). Verified data "
            "migrations by writing SQL reconciliation queries against staging.",
        ],
        projects=[
            "A Postman collection covering a public REST API end to end, with "
            "environment files for three deployment tiers.",
        ],
        certifications=["ISTQB Certified Tester, Foundation Level, 2023"],
    ),
    Profile(
        number=5,
        role_title="AI / ML Engineer",
        location="Beirut, Lebanon",
        phone="+1-202-555-0104",
        skills=[
            "Python",
            "Machine Learning",
            "Pandas",
            "NumPy",
            "Scikit-learn",
            "TensorFlow",
        ],
        summary=(
            "Machine learning engineer with five years taking models from a "
            "notebook to a service somebody depends on. More interested in "
            "evaluation and drift than in leaderboard scores."
        ),
        education=[
            "MSc Computer Science (Machine Learning), American University of "
            "Beirut, 2021",
            "BSc Mathematics, Lebanese University, 2019",
        ],
        experience=[
            "ML Engineer, Cedar Analytics (2022-2026). Built a demand "
            "forecasting service in scikit-learn and TensorFlow; added a "
            "monthly backtest that caught a feature pipeline regression three "
            "weeks before it would have reached a customer.",
            "Data Scientist, Phoenicia Telecom (2021-2022). Churn modelling in "
            "pandas and NumPy over 2 million subscriber records.",
        ],
        projects=[
            "An open-source drift detector comparing training and serving "
            "feature distributions, with alerting thresholds per feature.",
        ],
        certifications=["TensorFlow Developer Certificate, 2022"],
    ),
    Profile(
        number=6,
        role_title="HR / Recruitment Specialist",
        location="Amman, Jordan",
        phone="+1-202-555-0105",
        skills=[
            "Recruitment",
            "Candidate Screening",
            "Interview Coordination",
            "Excel",
            "HR Operations",
        ],
        summary=(
            "Recruitment specialist with six years hiring for technical and "
            "commercial roles. Runs a pipeline that candidates hear back from."
        ),
        education=["BA Business Administration, Yarmouk University, 2019"],
        experience=[
            "Senior Recruiter, Jordan Talent Partners (2022-2026). Filled 60 "
            "roles a year across engineering and sales; cut average time to "
            "offer from 41 days to 26 by moving screening calls before the "
            "technical review.",
            "HR Coordinator, Amman Manufacturing (2019-2022). Ran onboarding, "
            "interview scheduling and the HR records in Excel.",
        ],
        projects=[
            "A structured interview scorecard adopted across three hiring "
            "teams, replacing free-text notes.",
        ],
        certifications=["CIPD Level 3 Foundation Certificate in People "
                        "Practice, 2021"],
    ),
    Profile(
        number=7,
        role_title="DevOps Junior",
        location="Tunis, Tunisia",
        phone="+1-202-555-0106",
        skills=["Linux", "Docker", "Git", "CI/CD", "AWS"],
        summary=(
            "Junior DevOps engineer, eighteen months in. Comfortable on Linux, "
            "with Docker and with keeping a CI pipeline green. Has not yet run "
            "Kubernetes in production."
        ),
        education=["BEng Computer Networks, University of Tunis El Manar, 2024"],
        experience=[
            "DevOps Engineer (Junior), Medina Cloud Services (2024-2026). "
            "Maintains GitLab CI pipelines for nine repositories; containerised "
            "four legacy services and moved their builds off a developer's "
            "laptop.",
            "Systems Intern, Carthage Hosting (2023-2024). Linux server "
            "administration and backup verification.",
        ],
        projects=[
            "A reproducible development environment in Docker Compose adopted "
            "by the whole backend team.",
        ],
    ),
    Profile(
        number=8,
        role_title="UI/UX Designer",
        location="Casablanca, Morocco",
        phone="+1-202-555-0107",
        skills=[
            "Figma",
            "User Research",
            "Wireframing",
            "Prototyping",
            "Design Systems",
        ],
        summary=(
            "Product designer with four years on enterprise software, where "
            "the users did not choose the tool and cannot be delighted into "
            "using it. Research first, then wireframes, then pixels."
        ),
        education=["BA Visual Communication, ESAV Marrakech, 2021"],
        experience=[
            "Product Designer, Atlas Business Software (2022-2026). Designed "
            "the reporting module used daily by 3,000 internal staff; ran 40 "
            "moderated sessions that changed the navigation model before a "
            "line was built.",
            "UI Designer, Souk Digital (2021-2022). Marketing pages and a "
            "first design system in Figma.",
        ],
        projects=[
            "A design system in Figma with 120 components, documented tokens "
            "and a contribution process.",
        ],
        languages=["English", "Arabic", "French"],
    ),
    Profile(
        number=9,
        role_title="Cybersecurity Junior",
        location="Doha, Qatar",
        phone="+1-202-555-0108",
        skills=[
            "Network Security",
            "Linux",
            "OWASP",
            "SQL Injection",
            "Security Testing",
        ],
        summary=(
            "Junior security analyst with two years in a SOC and a growing "
            "interest in application security. Works through the OWASP Top Ten "
            "methodically rather than by tool output."
        ),
        education=["BSc Cybersecurity, Qatar University, 2024"],
        experience=[
            "Security Analyst (Junior), Gulf Secure Operations (2024-2026). "
            "Triages alerts on a 24/7 rota; wrote the runbook the team now "
            "uses for suspected credential stuffing.",
            "IT Support, Doha Medical Centre (2023-2024). Endpoint hardening "
            "and Linux patching.",
        ],
        projects=[
            "A deliberately vulnerable practice application demonstrating SQL "
            "injection and broken access control, used for internal training.",
        ],
    ),
    Profile(
        number=10,
        role_title="Business Analyst",
        location="Kuwait City, Kuwait",
        phone="+1-202-555-0109",
        skills=[
            "Requirements Gathering",
            "SQL",
            "Excel",
            "Process Analysis",
            "Documentation",
        ],
        summary=(
            "Business analyst with seven years between operations teams and "
            "engineering. Writes the requirement the developer can build and "
            "the tester can verify."
        ),
        education=[
            "MBA, Gulf University for Science and Technology, 2020",
            "BSc Industrial Engineering, Kuwait University, 2017",
        ],
        experience=[
            "Senior Business Analyst, Gulf Insurance Systems (2021-2026). Led "
            "requirements for a claims workflow replacement; mapped the "
            "existing 34-step process and removed nine steps that existed only "
            "to work around the old system.",
            "Business Analyst, Kuwait Logistics Co (2017-2021). Reporting in "
            "SQL and Excel, and the documentation for two ERP rollouts.",
        ],
        projects=[
            "A requirements template with acceptance criteria adopted as the "
            "standard across four project teams.",
        ],
        certifications=["IIBA Entry Certificate in Business Analysis, 2019"],
    ),
]


# ===========================================================================
# The CV document
# ===========================================================================

def build_cv_docx(profile: Profile) -> bytes:
    """A real DOCX with a real text layer.

    Written with `python-docx`, which is already installed because
    `cv_extraction` reads DOCX with it. Every section the parser looks for is
    present and every value is synthetic.
    """
    from docx import Document

    document = Document()

    document.add_heading(profile.full_name, level=1)
    document.add_paragraph(
        f"{profile.role_title} | {profile.location} | {profile.email} | "
        f"{profile.phone}"
    )

    document.add_heading("Professional Summary", level=2)
    document.add_paragraph(profile.summary)

    document.add_heading("Skills", level=2)
    document.add_paragraph(", ".join(profile.skills))

    document.add_heading("Experience", level=2)
    for entry in profile.experience:
        document.add_paragraph(entry)

    document.add_heading("Education", level=2)
    for entry in profile.education:
        document.add_paragraph(entry)

    document.add_heading("Projects", level=2)
    for entry in profile.projects:
        document.add_paragraph(entry)

    if profile.certifications:
        document.add_heading("Certifications", level=2)
        for entry in profile.certifications:
            document.add_paragraph(entry)

    document.add_heading("Languages", level=2)
    document.add_paragraph(", ".join(profile.languages))

    document.add_paragraph(
        "This document is synthetic test data created for SmartHR QA. It "
        "does not describe a real person."
    )

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ===========================================================================
# Safety
# ===========================================================================

def assert_safe() -> None:
    """Refuse to run at all if the fixture list could touch anything real.

    Checked before the first query rather than trusted: this is the guard that
    keeps a typo in `PROFILES` from writing to a production account.
    """
    for profile in PROFILES:
        if not profile.email.endswith(TEST_DOMAIN):
            raise SystemExit(
                f"Refusing to run: {profile.email} is not a {TEST_DOMAIN} "
                f"address."
            )

    if len({p.email for p in PROFILES}) != len(PROFILES):
        raise SystemExit("Refusing to run: duplicate addresses in PROFILES.")

    if len(PROFILES) != 10:
        raise SystemExit(f"Expected 10 profiles, found {len(PROFILES)}.")


# ===========================================================================
# The work
# ===========================================================================

@dataclass
class Outcome:
    profile: Profile
    user_id: int | None = None
    candidate_id: int | None = None
    cv_id: int | None = None
    cv_path: str | None = None
    user_state: str = "-"
    candidate_state: str = "-"
    cv_state: str = "-"
    file_exists: bool = False
    password_ok: bool | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return (
            not self.errors
            and self.user_id is not None
            and self.candidate_id is not None
            and self.cv_id is not None
            and self.file_exists
            and self.password_ok is not False
        )


def ensure_user(profile: Profile, db: Session, write: bool) -> tuple[User | None, str]:
    """The account, hashed the way the login route verifies.

    An existing account is **reused unchanged** - the password is not reset and
    the row is not rewritten, because re-running this must not disturb a
    fixture somebody is midway through testing with.
    """
    from app.routers.auth import password_hash

    existing = db.query(User).filter(User.email == profile.email).first()

    if existing is not None:
        if existing.role_id != ROLE_APPLICANT:
            return existing, "wrong-role"
        return existing, "exists"

    if not write:
        return None, "would-create"

    user = User(
        email=profile.email,
        password_hash=password_hash.hash(_test_account_password()),
        role_id=ROLE_APPLICANT,
        is_active=True,
    )
    db.add(user)
    db.flush()

    return user, "created"


def ensure_candidate(
    profile: Profile, user: User, db: Session, write: bool
) -> tuple[Candidate | None, str]:
    """The candidate row, through the one function that defines that link.

    `link_candidate_profile()` is what registration and Admin user management
    call, so a fixture is linked exactly as a real applicant is - including
    its `already_linked` outcome, which is what makes a second run harmless.
    """
    existing = db.query(Candidate).filter(Candidate.user_id == user.id).first()

    if existing is not None:
        # Fill in the QA detail the link function does not set, and only when
        # it is still empty: never overwrite something a tester typed.
        changed = []

        if write:
            if not existing.skills:
                existing.skills = ", ".join(profile.skills)
                changed.append("skills")
            if not existing.phone:
                existing.phone = profile.phone[:30]
                changed.append("phone")
            if not existing.location:
                existing.location = profile.location[:150]
                changed.append("location")

        return existing, "exists" + (f" (+{'+'.join(changed)})" if changed else "")

    if not write:
        return None, "would-create"

    candidate, _outcome = link_candidate_profile(user, db, full_name=profile.full_name)

    candidate.first_name = profile.first_name
    candidate.last_name = profile.last_name
    candidate.skills = ", ".join(profile.skills)
    candidate.phone = profile.phone[:30]
    candidate.location = profile.location[:150]

    db.flush()

    return candidate, "created"


def ensure_cv(
    profile: Profile, candidate: Candidate, db: Session, write: bool
) -> tuple[CV | None, str]:
    """The stored file and its row, through the real storage module.

    A CV is considered present when a row exists for this candidate **and its
    file is on disk**: a row pointing at a file somebody deleted is not a
    usable fixture, so that case is repaired rather than skipped.
    """
    rows = (
        db.query(CV)
        .filter(CV.candidate_id == candidate.id)
        .order_by(CV.id.desc())
        .all()
    )

    for row in rows:
        if (PROJECT_ROOT / row.file_path).is_file():
            return row, "exists"

    if not write:
        return None, "would-create"

    data = build_cv_docx(profile)
    stored_path = store_cv_file(data, "docx")

    cv = CV(
        candidate_id=candidate.id,
        file_name=display_filename(profile.cv_filename),
        file_path=stored_path,
    )
    db.add(cv)
    db.flush()

    return cv, "created" if not rows else "replaced-missing-file"


def process(db: Session, write: bool) -> list[Outcome]:
    from app.routers.auth import password_hash

    outcomes: list[Outcome] = []

    for profile in PROFILES:
        outcome = Outcome(profile=profile)

        try:
            user, outcome.user_state = ensure_user(profile, db, write)

            if user is None:
                outcomes.append(outcome)
                continue

            if outcome.user_state == "wrong-role":
                outcome.errors.append(
                    f"account exists with role {user.role_id}, not Applicant "
                    f"({ROLE_APPLICANT}); left untouched"
                )
                outcome.user_id = user.id
                outcomes.append(outcome)
                continue

            outcome.user_id = user.id
            outcome.password_ok = password_hash.verify(_test_account_password(), user.password_hash)

            candidate, outcome.candidate_state = ensure_candidate(
                profile, user, db, write
            )

            if candidate is None:
                outcomes.append(outcome)
                continue

            outcome.candidate_id = candidate.id

            cv, outcome.cv_state = ensure_cv(profile, candidate, db, write)

            if cv is not None:
                outcome.cv_id = cv.id
                outcome.cv_path = cv.file_path
                outcome.file_exists = (PROJECT_ROOT / cv.file_path).is_file()

        except Exception as error:  # pragma: no cover - reported, not raised
            outcome.errors.append(f"{type(error).__name__}: {error}")

        outcomes.append(outcome)

    return outcomes


# ===========================================================================
# Verification
# ===========================================================================

def verify(db: Session, outcomes: list[Outcome]) -> None:
    """Re-read every relationship from the database, not from memory."""
    print("\nRelationship verification")
    print("-" * 64)

    for outcome in outcomes:
        profile = outcome.profile
        problems: list[str] = []

        user = db.query(User).filter(User.email == profile.email).first()

        if user is None:
            problems.append("no account")
        else:
            if user.role_id != ROLE_APPLICANT:
                problems.append(f"role {user.role_id}")
            if not user.is_active:
                problems.append("inactive")

            candidate = (
                db.query(Candidate).filter(Candidate.user_id == user.id).first()
            )

            if candidate is None:
                problems.append("no candidate linked")
            else:
                if candidate.email != profile.email:
                    problems.append(
                        f"candidate email {candidate.email} != {profile.email}"
                    )

                cvs = db.query(CV).filter(CV.candidate_id == candidate.id).all()

                if not cvs:
                    problems.append("no CV row")
                else:
                    for row in cvs:
                        if not (PROJECT_ROOT / row.file_path).is_file():
                            problems.append(f"CV {row.id} file missing")

        print(
            f"  {'OK  ' if not problems else 'FAIL'}  {profile.email:<28} "
            f"{'user -> candidate -> cv' if not problems else '; '.join(problems)}"
        )


def parse_check(db: Session) -> None:
    """Run the **real** CV pipeline over each stored file.

    `analyse_cv_bytes()` is the same function `POST /cvs/upload` and the
    `parse_cv` MCP tool call. Nothing it returns is written anywhere: this
    reports what the parser did, which is the point of having the fixtures.

    With no API key configured the analysis half returns
    `llm_not_configured` and extraction still succeeds - that is a correct
    result and is reported as such, not as a failure.
    """
    from app.services.cv_service import CvServiceError, analyse_cv_bytes

    print("\nAI CV parser - real run against each stored file")
    print("-" * 64)

    for profile in PROFILES:
        user = db.query(User).filter(User.email == profile.email).first()
        candidate = (
            db.query(Candidate).filter(Candidate.user_id == user.id).first()
            if user
            else None
        )
        cv = (
            db.query(CV)
            .filter(CV.candidate_id == candidate.id)
            .order_by(CV.id.desc())
            .first()
            if candidate
            else None
        )

        if cv is None:
            print(f"  {profile.email:<28} no CV to parse")
            continue

        path = PROJECT_ROOT / cv.file_path

        try:
            result = analyse_cv_bytes(cv.file_name, path.read_bytes())
        except CvServiceError as error:
            print(f"  {profile.email:<28} REFUSED  {error.code}")
            continue
        except Exception as error:  # pragma: no cover
            print(f"  {profile.email:<28} ERROR    {type(error).__name__}")
            continue

        chars = len(result.text)

        if result.parsed is None:
            # Not a failure of the fixture: extraction succeeded and only the
            # analysis half is unavailable, which is what an unconfigured key
            # correctly produces.
            print(
                f"  {profile.email:<28} {result.file_type}  text {chars:>5} chars"
                f"  analysis: {result.analysis_error_code}"
            )
            continue

        parsed = result.parsed
        print(
            f"  {profile.email:<28} {result.file_type}  text {chars:>5} chars"
            f"  parsed: {len(parsed.skills):>2} skills, "
            f"{len(parsed.experience)} roles, "
            f"{len(parsed.education)} education, "
            f"{len(parsed.certifications)} certs"
        )


# ===========================================================================
# Reporting
# ===========================================================================

def report(outcomes: list[Outcome], write: bool) -> int:
    print("\nApplicant Test Data")
    print("===================\n")

    for outcome in outcomes:
        profile = outcome.profile
        status = "READY" if outcome.ready else ("PENDING" if not write else "ERROR")

        print(f"{profile.number:02d} {profile.email}")
        print(f"   Candidate: {profile.full_name}   ({profile.role_title})")
        print(
            f"   User id:   {outcome.user_id or '-'}   "
            f"Candidate id: {outcome.candidate_id or '-'}   "
            f"CV id: {outcome.cv_id or '-'}"
        )
        print(f"   CV:        {outcome.cv_path or profile.cv_filename}")
        print(
            f"   File:      {'present' if outcome.file_exists else 'MISSING'}"
            f"   Password:  "
            f"{'verifies' if outcome.password_ok else ('-' if outcome.password_ok is None else 'DOES NOT VERIFY')}"
        )
        print(
            f"   State:     user {outcome.user_state}, "
            f"candidate {outcome.candidate_state}, cv {outcome.cv_state}"
        )

        for error in outcome.errors:
            print(f"   ERROR:     {error}")

        print(f"   Status:    {status}\n")

    created_users = sum(1 for o in outcomes if o.user_state == "created")
    created_candidates = sum(1 for o in outcomes if o.candidate_state == "created")
    created_cvs = sum(1 for o in outcomes if o.cv_state.startswith(("created", "replaced")))
    skipped = sum(
        1
        for o in outcomes
        if o.user_state == "exists"
        and o.candidate_state.startswith("exists")
        and o.cv_state == "exists"
    )
    errors = sum(len(o.errors) for o in outcomes)

    print("Summary:")
    print(f"Users created:      {created_users}")
    print(f"Candidates created: {created_candidates}")
    print(f"CV files created:   {created_cvs}")
    print(f"CV records created: {created_cvs}")
    print(f"Duplicates skipped: {skipped}")
    print(f"Errors:             {errors}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be created and write nothing",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="check the existing fixtures only; writes nothing",
    )
    parser.add_argument(
        "--parse",
        action="store_true",
        help="also run the real AI CV parser over each stored CV",
    )
    args = parser.parse_args()

    assert_safe()
    _test_account_password()

    write = not (args.dry_run or args.verify)

    db = SessionLocal()

    try:
        outcomes = process(db, write)

        if write:
            db.commit()
        else:
            db.rollback()

        errors = report(outcomes, write)
        verify(db, outcomes)

        if args.parse:
            parse_check(db)

        if not write:
            print(
                "\nNothing was written "
                f"({'--dry-run' if args.dry_run else '--verify'})."
            )

        print(
            f"\nCV files live in {CV_UPLOAD_DIR.relative_to(PROJECT_ROOT)}"
            " - the same directory a real upload writes to."
        )

        return 1 if errors else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
