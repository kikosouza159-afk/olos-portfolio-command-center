from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
(ROOT / "data").mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/portfolio.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs = {
    "pool_pre_ping": True,
    "connect_args": connect_args,
}

if not is_sqlite:
    # Mantém um pequeno pool quente para reduzir reconexões ao Neon/Render.
    engine_kwargs.update(
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        pool_use_lifo=True,
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
