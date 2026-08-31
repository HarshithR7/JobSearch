from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from config import settings

if settings.DATABASE_URL:
    # Managed Postgres (Neon) connection string, used verbatim — it carries
    # required query params (sslmode=require, channel_binding, ...) that
    # reconstructing from DB_HOST/DB_PORT/... below would lose.
    DATABASE_URL = settings.DATABASE_URL
else:
    DATABASE_URL = URL.create(
        "postgresql+psycopg2",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD or None,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
    )

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    # Pages routinely read an object inside `with get_session()` and use it
    # after the block exits (session closed). Default expire_on_commit=True
    # would mark attributes stale on commit and try to re-fetch them on next
    # access, raising DetachedInstanceError once the session is closed.
    expire_on_commit=False,
    bind=engine,
)
