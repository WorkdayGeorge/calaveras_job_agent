\
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass
class RawJob:
    provider_job_id: str | None
    title: str
    company: str
    location: str | None
    employment_type: str | None
    description: str | None
    posted_at: datetime | None
    apply_url: str
    source: str
    source_url: str | None = None
    requirements: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class NormalizedJob:
    provider_job_id: str | None
    title: str
    company: str
    location: str | None
    employment_type: str | None
    description: str | None
    requirements: list[str]
    posted_at: datetime | None
    posted_time_confidence: str
    apply_url: str
    source: str
    source_url: str | None
    job_fingerprint: str
    is_local: bool
    freshness_status: str
