from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from backend.app.core.config import settings
from backend.app.core.logging import logger

Base = declarative_base()

# Resolve DATABASE_URL: enforce PostgreSQL in staging/production, allow SQLite in development
database_url = settings.DATABASE_URL
if not database_url:
    if settings.ENVIRONMENT in ("production", "staging"):
        raise ValueError(
            f"DATABASE_URL is required in {settings.ENVIRONMENT} mode. "
            "Cannot fall back to local SQLite database in production/staging environments."
        )
    database_url = "sqlite:///./farmer_dev.db"
    logger.info("DATABASE_URL not set; using local SQLite database for development.")
elif settings.ENVIRONMENT in ("production", "staging") and "sqlite" in database_url.lower():
    raise ValueError(
        f"SQLite database is not permitted in {settings.ENVIRONMENT} mode. "
        "A valid PostgreSQL/Supabase connection string is required."
    )

engine = create_engine(
    database_url,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    } if "sqlite" not in database_url.lower() else {"check_same_thread": False},
    pool_pre_ping=True,
    pool_recycle=60,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to yield database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
