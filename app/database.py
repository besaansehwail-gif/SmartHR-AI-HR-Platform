from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import settings

# Phase 10: the URL (with its credentials) comes from SMARTHR_DATABASE_URL in
# the environment or .env.local - never from the source. Missing is a startup
# error, not a fallback database.
DATABASE_URL = settings.database_url()
engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)
