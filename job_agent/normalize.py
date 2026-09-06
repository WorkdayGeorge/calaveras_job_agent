\
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from .schemas import RawJob, NormalizedJob

TRACKING_PREFIXES = ("utm_", "sar_id", "jpos", "ref", "source")

def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    # Remove query/fragment for stable dedupe. Provider job id/title/company
    # remain in the fingerprint, so this is intentionally conservative.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))

def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()

def fingerprint(raw: RawJob) -> str:
    pieces = [
        clean_text(raw.provider_job_id),
        clean_text(raw.title).lower(),
        clean_text(raw.company).lower(),
        clean_text(raw.location).lower(),
        canonicalize_url(raw.apply_url),
    ]
    return hashlib.sha256("|".join(pieces).encode("utf-8")).hexdigest()

def is_local_location(location: str | None, settings: dict) -> bool:
    if not location:
        return False
    l = location.lower()
    primary = settings["location"]["primary"].lower()
    if "calaveras county" in l or primary in l:
        return True
    for locality in settings["location"].get("allowed_localities", []):
        if locality.lower() in l and ("ca" in l or "california" in l):
            return True
    return False

def freshness_status(posted_at: datetime | None, settings: dict, now: datetime | None = None) -> tuple[str, str]:
    if posted_at is None:
        return "unverified", "unverified"

    now = now or datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    age_minutes = (now - posted_at).total_seconds() / 60
    window = settings["fresh_job_window_minutes"]

    if age_minutes < -5:
        return "invalid_future_timestamp", "unverified"
    if age_minutes <= window:
        return "verified_fresh", "verified"
    return "older_than_window", "verified"

def normalize_job(raw: RawJob, settings: dict, now: datetime | None = None) -> NormalizedJob:
    freshness, confidence = freshness_status(raw.posted_at, settings, now=now)
    return NormalizedJob(
        provider_job_id=raw.provider_job_id,
        title=clean_text(raw.title),
        company=clean_text(raw.company),
        location=clean_text(raw.location) or None,
        employment_type=clean_text(raw.employment_type) or None,
        description=clean_text(raw.description) or None,
        requirements=[clean_text(x) for x in raw.requirements if clean_text(x)],
        posted_at=raw.posted_at,
        posted_time_confidence=confidence,
        apply_url=raw.apply_url,
        source=raw.source,
        source_url=raw.source_url,
        job_fingerprint=fingerprint(raw),
        is_local=is_local_location(raw.location, settings),
        freshness_status=freshness,
    )
