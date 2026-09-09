\
from __future__ import annotations
import os

def trigger_worker() -> str:
    mode = os.getenv("RUN_NOW_MODE", "local").lower()

    if mode == "local":
        from job_agent.pipeline import run_once
        result = run_once(force=True)
        return f"Local run completed: {result}"

    if mode != "cloud_run_job":
        raise RuntimeError(f"Unsupported RUN_NOW_MODE={mode}")

    from google.cloud import run_v2
    project = os.environ["GCP_PROJECT_ID"]
    region = os.getenv("GCP_REGION", "us-west1")
    job_name = os.getenv("CLOUD_RUN_JOB_NAME", "calaveras-job-agent-worker")
    name = f"projects/{project}/locations/{region}/jobs/{job_name}"

    client = run_v2.JobsClient()

    overrides = run_v2.RunJobRequest.Overrides(
        container_overrides=[
            run_v2.RunJobRequest.Overrides.ContainerOverride(
                env=[
                    run_v2.EnvVar(
                        name="FORCE_RUN",
                        value="true",
                    )
                ]
            )
        ]
    )

    request = run_v2.RunJobRequest(
        name=name,
        overrides=overrides,
    )

    operation = client.run_job(request=request)

    return f"Cloud Run Job triggered: {name}; operation={operation.operation.name}"
