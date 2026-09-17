\
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone

def save_resume(
    filename: str,
    content: bytes,
    resume_type: str,
    user_id: str | None = None,
) -> str:
    bucket_name = os.getenv("GCS_BUCKET")
    safe_name = Path(filename).name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    owner = user_id or "legacy"
    object_name = f"resumes/{owner}/{resume_type}/{stamp}-{safe_name}"

    if bucket_name:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(content)
        return f"gs://{bucket_name}/{object_name}"

    upload_dir = (
        Path(__file__).resolve().parents[1]
        / "data" / "uploads" / owner / resume_type
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{stamp}-{safe_name}"
    path.write_bytes(content)
    return str(path)
