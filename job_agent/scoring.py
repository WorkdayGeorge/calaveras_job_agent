\
from __future__ import annotations
import re
from typing import Iterable

WEIGHTS = {
    "required_qualifications": 25,
    "relevant_experience": 20,
    "transferable_skills": 15,
    "career_direction": 15,
    "education_training": 10,
    "location_commute": 10,
    "pay_schedule": 5,
}

def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+#./-]{1,}", text.lower())
        if len(t) >= 3
    }

def keyword_overlap_score(job_text: str, profile_terms: Iterable[str]) -> float:
    job_tokens = _tokens(job_text)
    if not job_tokens:
        return 0.0
    term_tokens: set[str] = set()
    for term in profile_terms:
        term_tokens |= _tokens(term)
    if not term_tokens:
        return 0.0
    overlap = len(job_tokens & term_tokens)
    # Saturates quickly by design; this is only a deterministic prior,
    # not the final semantic evaluation.
    return min(1.0, overlap / max(5, min(20, len(term_tokens))))

def deterministic_prior(job: dict, profile: dict) -> dict:
    text = " ".join([
        job.get("title") or "",
        job.get("description") or "",
        " ".join(job.get("requirements") or []),
    ])

    accounting = profile["skills"]["accounting_office"]
    technical = profile["skills"]["data_technical"]
    operations = profile["skills"]["operations"]
    transferable = profile["skills"]["transferable"]
    training = [x["name"] for x in profile["education_training"]]

    scores = {
        "required_qualifications": round(100 * keyword_overlap_score(text, accounting + technical + operations), 1),
        "relevant_experience": round(100 * keyword_overlap_score(text, operations + accounting), 1),
        "transferable_skills": round(100 * keyword_overlap_score(text, transferable), 1),
        "career_direction": round(100 * keyword_overlap_score(text, profile["career_targets"]), 1),
        "education_training": round(100 * keyword_overlap_score(text, training + accounting + technical), 1),
        "location_commute": 100.0 if job.get("is_local") else 0.0,
        "pay_schedule": 50.0,  # neutral unless explicitly parsed later
    }
    weighted = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS) / 100
    return {"score": round(weighted, 1), "breakdown": scores}

def classify(score: int | float) -> tuple[str, str]:
    if score >= 75:
        return "Strong Fit", "Apply"
    if score >= 60:
        return "Possible Fit", "Review"
    return "Poor Fit", "Skip"
