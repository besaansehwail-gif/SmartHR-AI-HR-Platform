"""The daily AI Employee Celebration sweep.

    venv\\Scripts\\python.exe -m scripts.run_daily_celebrations
    venv\\Scripts\\python.exe -m scripts.run_daily_celebrations --dry-run
    venv\\Scripts\\python.exe -m scripts.run_daily_celebrations --date 2026-03-01

Finds whose work anniversary is today, runs the three-agent LangGraph
workflow once per person, and leaves a `pending` draft for HR. **It posts
nothing** - `approve_draft()` is the only path to the feed and it needs a
signed-in recruiter, which this process does not have.

Why a script and a scheduled task rather than a scheduler inside the app
-----------------------------------------------------------------------

SmartHR has no scheduler and this did not add one. `interview_service`
already documents the same judgement: `expire_if_stale()` runs on read
"because SmartHR has none". Three reasons an in-process loop was the wrong
shape here:

  * `uvicorn --reload` runs a reloader **and** a worker, so a loop inside the
    application fires twice a day, not once;
  * a loop dies with the process it lives in, and nothing says it stopped -
    the interviews feature has already been bitten once by a background job
    that looked alive and was not;
  * it makes the API responsible for wall-clock time, which is the operating
    system's job and which the operating system already does well.

So: one query, one loop, one command. Register it once with Windows Task
Scheduler (daily, 09:00):

    schtasks /Create /SC DAILY /ST 09:00 /TN "SmartHR celebrations" ^
      /TR "C:\\...\\SmartHR\\venv\\Scripts\\python.exe -m scripts.run_daily_celebrations" ^
      /RU <account>

**Running it twice is safe**, and that is a property of the database rather
than of this file: `celebration_drafts` carries
`UNIQUE (employee_id, occasion, occasion_date)`, so a second run of the day
cannot create a second celebration for the same person's same anniversary.
The service also checks for the row first, so the second run spends no model
calls at all.

Exit code 0 when the sweep completed - including when nobody was celebrating,
which is the normal answer on most days. 1 only when it could not run.
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services import celebration_service  # noqa: E402


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a date in YYYY-MM-DD form."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare today's employee celebrations for HR to approve."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report who would be celebrated and write nothing.",
    )
    parser.add_argument(
        "--date", type=_parse_date, default=None,
        help="run as if it were this date (YYYY-MM-DD). For testing.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="print the summary only.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )

    when = args.date or datetime.utcnow().date()

    print("=" * 74)
    print("AI EMPLOYEE CELEBRATION - daily sweep")
    print("=" * 74)
    print(f"  date    : {when.isoformat()}")
    print(f"  dry run : {args.dry_run}")
    print()

    db = SessionLocal()
    try:
        summary = celebration_service.run_daily(
            db, today=when, dry_run=args.dry_run
        )
    except Exception:
        logging.getLogger("smarthr.ai.celebration").exception(
            "The celebration sweep could not run"
        )
        print("  THE SWEEP FAILED. Nothing was posted; see the traceback above.")
        return 1
    finally:
        db.close()

    for draft in summary["drafts"]:
        name = draft.get("employee_name") or f"employee {draft.get('employee_id')}"
        if draft.get("would_run"):
            print(f"  WOULD PREPARE  {name} - {draft.get('years')} years")
            continue

        verdict = "approved" if draft["review"]["approved"] else "NOT approved"
        print(f"  prepared       {name} - {draft['years']} years - {verdict}")
        if draft.get("message"):
            print(f"                 {draft['message'][:96]}")
        if not draft["review"]["approved"]:
            print(f"                 reviewer: {draft['review']['reason'][:80]}")

    print()
    print(f"  found            : {summary['found']}")
    print(f"  prepared         : {summary['prepared']}")
    print(f"  already prepared : {summary['skipped_existing']}")
    print(f"  no occasion      : {summary['no_occasion']}")
    print(f"  failed           : {summary['failed']}")
    print()

    if summary["prepared"]:
        print("  Nothing has been posted. The drafts are waiting for HR in the")
        print("  Social Hub, where a person approves and posts them.")
    elif not summary["found"]:
        print("  Nobody has a work anniversary today. That is the usual answer.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
