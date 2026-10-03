from datetime import datetime, timedelta, timezone

from job_agent.models import ResumeAsset
from job_agent.resume_asset_cleanup import cleanup_plan, delete_stored_resume


def asset(asset_id, user_id, resume_type, current, uploaded_at):
    return ResumeAsset(
        id=asset_id,
        user_id=user_id,
        resume_type=resume_type,
        filename=f"{asset_id}.pdf",
        storage_uri=f"/tmp/{asset_id}.pdf",
        extracted_text="resume",
        uploaded_at=uploaded_at,
        is_current=current,
    )


def test_cleanup_keeps_only_newest_current_all_work_resume_per_user():
    now = datetime.now(timezone.utc)
    assets = [
        asset("old-all", "u1", "all-work-experience", False, now - timedelta(days=2)),
        asset("current-all", "u1", "all-work-experience", True, now),
        asset("focused", "u1", "focused", True, now),
        asset("linkedin", "u1", "linkedin-profile", True, now),
        asset("only-focused", "u2", "focused", True, now),
        asset("legacy-orphan", None, "all-work-experience", True, now),
    ]

    keep, delete = cleanup_plan(assets)

    assert [item.id for item in keep] == ["current-all"]
    assert {item.id for item in delete} == {
        "old-all", "focused", "linkedin", "only-focused", "legacy-orphan",
    }


def test_delete_stored_resume_removes_only_exact_file(tmp_path):
    target = tmp_path / "resume.pdf"
    neighbor = tmp_path / "keep.pdf"
    target.write_bytes(b"resume")
    neighbor.write_bytes(b"keep")

    assert delete_stored_resume(str(target)) == "deleted"
    assert not target.exists()
    assert neighbor.exists()
    assert delete_stored_resume(str(target)) == "missing"
