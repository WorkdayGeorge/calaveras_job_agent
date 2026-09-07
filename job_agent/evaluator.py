\
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from .config import env
from .prompts import EVALUATOR_SYSTEM_PROMPT
from .scoring import deterministic_prior, classify

def load_candidate_profile(path: str | None = None) -> dict:
    p = Path(path) if path else Path(__file__).resolve().parents[1] / "data" / "candidate_profile.json"
    return json.loads(p.read_text(encoding="utf-8"))

def _select_resume_fallback(job: dict, profile: dict) -> str:
    text = f"{job.get('title','')} {job.get('description','')}".lower()
    for term in profile["resume_selection_rules"]["focused"]:
        if term in text:
            return "focused"
    return "all-work-experience"

def evaluate_without_ai(job: dict, profile: dict) -> dict:
    prior = deterministic_prior(job, profile)
    score = int(round(prior["score"]))
    classification, recommendation = classify(score)
    return {
        "fit_score": score,
        "classification": classification,
        "recommendation": recommendation,
        "selected_resume": _select_resume_fallback(job, profile),
        "matching_skills": [],
        "transferable_skills": [],
        "missing_requirements": [],
        "uncertain_requirements": ["AI evaluation disabled; deterministic prior only."],
        "reasoning": "Deterministic fallback score based on resume/job term overlap and location.",
        "score_breakdown": prior["breakdown"],
    }

def evaluate_job(job: dict, profile: dict) -> dict:
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        return evaluate_without_ai(job, profile)

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    payload = {
        "job": job,
        "candidate_profile": profile,
        "deterministic_prior": deterministic_prior(job, profile),
    }

    response = client.responses.create(
        model=env("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=EVALUATOR_SYSTEM_PROMPT,
        input=json.dumps(payload),
    )

    try:
        result = json.loads(response.output_text)
    except Exception as exc:
        raise RuntimeError(f"Evaluator returned non-JSON output: {response.output_text[:500]}") from exc

    # Hard validation/normalization.
    result["fit_score"] = max(0, min(100, int(result["fit_score"])))
    result["classification"], result["recommendation"] = classify(result["fit_score"])
    if result.get("selected_resume") not in {"focused", "all-work-experience"}:
        result["selected_resume"] = _select_resume_fallback(job, profile)
    return result
