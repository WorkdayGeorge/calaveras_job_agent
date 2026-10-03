from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal, init_db
from .models import ResumeAsset


def cleanup_plan(assets: list[ResumeAsset]) -> tuple[list[ResumeAsset], list[ResumeAsset]]:
    """Keep the newest current All Work Experience resume for each user."""
    grouped: dict[str, list[ResumeAsset]] = defaultdict(list)
    delete: list[ResumeAsset] = []
    for asset in assets:
        if asset.user_id:
            grouped[asset.user_id].append(asset)
        else:
            delete.append(asset)

    keep: list[ResumeAsset] = []
    for user_assets in grouped.values():
        candidates = [
            asset for asset in user_assets
            if asset.resume_type == "all-work-experience" and asset.is_current
        ]
        keeper = max(candidates, key=lambda item: item.uploaded_at) if candidates else None
        if keeper:
            keep.append(keeper)
        delete.extend(asset for asset in user_assets if asset is not keeper)
    return keep, delete


def delete_stored_resume(storage_uri: str) -> str:
    if storage_uri.startswith("gs://"):
        bucket_name, object_name = storage_uri[5:].split("/", 1)
        from google.cloud import storage

        blob = storage.Client().bucket(bucket_name).blob(object_name)
        if not blob.exists():
            return "missing"
        blob.delete()
        return "deleted"

    path = Path(storage_uri)
    if not path.is_file():
        return "missing"
    path.unlink()
    return "deleted"


def remove_noncurrent_resume_assets() -> dict:
    init_db()
    summary = {
        "status": "success",
        "kept": 0,
        "records_deleted": 0,
        "files_deleted": 0,
        "files_missing": 0,
        "errors": [],
    }
    with SessionLocal() as session:
        assets = session.scalars(
            select(ResumeAsset).order_by(ResumeAsset.user_id, ResumeAsset.uploaded_at)
        ).all()
        keep, delete = cleanup_plan(assets)
        summary["kept"] = len(keep)
        for asset in delete:
            try:
                storage_result = delete_stored_resume(asset.storage_uri)
                summary[f"files_{storage_result}"] += 1
            except Exception as exc:
                summary["errors"].append(f"{asset.id}/{asset.filename}: {exc}")
                continue
            session.delete(asset)
            summary["records_deleted"] += 1
        session.commit()
    if summary["errors"]:
        summary["status"] = "completed_with_errors"
    return summary


if __name__ == "__main__":
    print(f"Resume asset cleanup: {remove_noncurrent_resume_assets()}")
