from database.base import Base
from database.engine import engine
from database import models  # noqa: F401 — registers all models on Base.metadata


def create_tables():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_tables()
