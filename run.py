import os

from job_agent.pipeline import run_once


if __name__ == "__main__":
    force = os.getenv("FORCE_RUN", "false").lower() in {"1", "true", "yes", "on"}
    run_once(force=force)
