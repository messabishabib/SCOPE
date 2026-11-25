import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .base import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./capacity_planner.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)

