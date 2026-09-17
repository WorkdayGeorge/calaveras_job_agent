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
    inspector = inspect(engine)
    ownership_tables = ("evaluations", "notifications", "resume_assets", "application_packages")
    with engine.begin() as connection:
        for table_name in ownership_tables:
            if table_name not in inspector.get_table_names():
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "user_id" not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN user_id VARCHAR(36)")
                )

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

        # Replace legacy global uniqueness with per-user uniqueness. These
        # operations are idempotent and preserve all existing records.
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE evaluations DROP CONSTRAINT IF EXISTS uq_job_resume_version"
            ))
            connection.execute(text(
                "ALTER TABLE application_packages "
                "DROP CONSTRAINT IF EXISTS uq_application_package_job_version"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_job_resume_version_idx "
                "ON evaluations (user_id, job_id, resume_version)"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_application_package_job_version_idx "
                "ON application_packages (user_id, job_id, version)"
            ))
            for table_name in ownership_tables:
                connection.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table_name}_user_id "
                    f"ON {table_name} (user_id)"
                ))
