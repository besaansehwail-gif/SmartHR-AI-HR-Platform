"""Give every Applicant account the candidates row it signs in as.

    venv\\Scripts\\python.exe -m scripts.link_applicant_profiles           report
    venv\\Scripts\\python.exe -m scripts.link_applicant_profiles --apply   fix

Why this exists: an Applicant is a `users` row (role 5) plus the `candidates`
row whose `user_id` points back at it, and `get_current_candidate` resolves the
second from the first on every `/applicant/*` request. `POST
/applicant/register` has always created both. `POST /users/` - Admin user
management - created only the account, because it predates the Applicant
feature and knows nothing about `candidates`. An account made that way logs in
correctly and then fails every applicant route with "not linked to an applicant
profile".

`app/routers/users.py` now links on create and on promotion, so no *new*
account can arrive in that state. This script repairs the ones that already
did, which is a data problem and not something a code change can reach.

It calls the same `link_candidate_profile()` as registration, so there is one
definition of what linking means and the adopt-before-create rule applies here
too: an account whose address matches a candidate HR keyed in by hand is
attached to that row rather than given a second one.

**Idempotent.** An account that already has a profile is reported as
`already_linked` and nothing is written, so running this twice - or on a
healthy database - changes nothing. It reports by default and writes only with
`--apply`.
"""

import sys

from app.database import SessionLocal
from app.models import Candidate, User
from app.services.applicant_service import (
    ALREADY_LINKED,
    ROLE_APPLICANT,
    ApplicantError,
    link_candidate_profile,
)


def main(apply: bool) -> int:
    db = SessionLocal()

    try:
        accounts = (
            db.query(User)
            .filter(User.role_id == ROLE_APPLICANT)
            .order_by(User.id)
            .all()
        )

        if not accounts:
            print("No Applicant (role 5) accounts exist. Nothing to do.")
            return 0

        print(f"{len(accounts)} Applicant account(s) found.\n")

        changed = 0

        for account in accounts:
            existing = (
                db.query(Candidate)
                .filter(Candidate.user_id == account.id)
                .first()
            )

            if existing is not None:
                print(f"  [ok]      user {account.id} {account.email} "
                      f"-> candidate {existing.id} (already linked)")
                continue

            if not apply:
                # Say what would happen without doing it, so the operator can
                # see an adoption coming before it happens.
                adoptable = (
                    db.query(Candidate)
                    .filter(Candidate.email == account.email.lower())
                    .filter(Candidate.user_id.is_(None))
                    .order_by(Candidate.id)
                    .first()
                )
                action = (
                    f"would adopt existing candidate {adoptable.id}"
                    if adoptable else "would create a new candidate row"
                )
                print(f"  [MISSING] user {account.id} {account.email} -> {action}")
                changed += 1
                continue

            try:
                candidate, outcome = link_candidate_profile(account, db)
            except ApplicantError as exc:
                db.rollback()
                print(f"  [FAILED]  user {account.id} {account.email}: {exc}")
                continue

            db.commit()

            if outcome != ALREADY_LINKED:
                changed += 1

            print(f"  [linked]  user {account.id} {account.email} "
                  f"-> candidate {candidate.id} ({outcome})")

        print()

        if apply:
            print(f"{changed} account(s) linked.")
        elif changed:
            print(f"{changed} account(s) need a profile. "
                  f"Re-run with --apply to create or link them.")
        else:
            print("Every Applicant account already has a profile.")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))
