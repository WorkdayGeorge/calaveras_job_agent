from __future__ import annotations

from sqlalchemy import select

from .db import SessionLocal, init_db
from .models import ResumeAsset, User
from .resume_search_terms import propose_search_terms_from_resume
from .user_search import add_resume_search_terms, ensure_user_search_terms
from web.resume_storage import extract_resume_text, read_resume


def regenerate_current_resume_search_terms() -> dict:
    init_db()
    summary = {
        "status": "success",
        "users": 0,
        "resumes": 0,
        "terms_added": 0,
        "errors": [],
    }
    with SessionLocal() as session:
        users = session.scalars(
            select(User).where(User.status != "archived").order_by(User.id)
        ).all()
        for user in users:
            assets = session.scalars(
                select(ResumeAsset).where(
                    ResumeAsset.user_id == user.id,
                    ResumeAsset.is_current.is_(True),
                ).order_by(ResumeAsset.uploaded_at)
            ).all()
            if not assets:
                continue
            summary["users"] += 1
            for asset in assets:
                summary["resumes"] += 1
                try:
                    resume_text = asset.extracted_text
                    if not resume_text:
                        resume_text = extract_resume_text(
                            asset.filename,
                            read_resume(asset.storage_uri),
                        )
                        asset.extracted_text = resume_text
                        session.commit()
                    existing = ensure_user_search_terms(session, user)
                    suggestions = propose_search_terms_from_resume(
                        resume_text,
                        [item.term for item in existing],
                    )
                    added = add_resume_search_terms(session, user.id, suggestions)
                    summary["terms_added"] += len(added)
                except Exception as exc:
                    summary["errors"].append(
                        f"{user.id}/{asset.filename}: {exc}"
                    )
        if summary["errors"]:
            summary["status"] = "completed_with_errors"
    return summary


if __name__ == "__main__":
    print(f"Resume search-term backfill: {regenerate_current_resume_search_terms()}")
