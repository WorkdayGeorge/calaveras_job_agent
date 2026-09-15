\
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from .config import env
from .models import Base

DATABASE_URL = env("DATABASE_URL", "sqlite:///./jobs.db")
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def init_db() -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("run_logs")
        }
        provider_type = columns.get("provider", {}).get("type")
        if getattr(provider_type, "length", None) is not None:
            # create_all does not modify existing columns. Widen the legacy
            # VARCHAR(100) once; PostgreSQL preserves all current run history.
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE run_logs "
                        "ALTER COLUMN provider TYPE TEXT"
                    )
                )
