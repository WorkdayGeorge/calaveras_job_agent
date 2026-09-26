import json
from types import SimpleNamespace

import openai

from job_agent.profile_extractor import (
    normalize_profile_proposal,
    propose_profile_from_resume,
)
from tests.test_profile_store import valid_profile


def test_resume_profile_proposal_accepts_reviewable_json(monkeypatch):
    proposal = valid_profile()
    proposal["career_targets"] = ["hotel front desk"]
    response = SimpleNamespace(
        output_text=f"```json\n{json.dumps(proposal)}\n```"
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: response)
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", lambda api_key: client)

    result = propose_profile_from_resume(
        "Customer service experience",
        valid_profile(),
        ["hotel front desk"],
        candidate_name="Monte O. George IV",
    )

    assert result["career_targets"] == ["hotel front desk"]
    assert result["name"] == "Monte O. George IV"


def test_resume_profile_proposal_requires_readable_text():
    try:
        propose_profile_from_resume("  ", valid_profile(), [])
        assert False, "Expected empty resume text to be rejected"
    except ValueError as exc:
        assert "No readable text" in str(exc)


def test_common_resume_shapes_are_normalized_before_validation():
    proposal = valid_profile()
    proposal["experience"] = [{
        "job_title": "Front Desk Clerk",
        "employer": "Example Hotel",
        "date_range": "2024-2025",
        "responsibilities": "Welcomed guests\nAnswered phones",
    }]
    proposal["education_training"] = [
        "High school diploma",
        {"program": "Customer Service Training", "institution": "Example School"},
    ]

    result = normalize_profile_proposal(
        proposal,
        valid_profile(),
        candidate_name="Monte O. George IV",
    )

    assert result["experience"][0] == {
        "role": "Front Desk Clerk",
        "company": "Example Hotel",
        "location": "",
        "dates": "2024-2025",
        "highlights": ["Welcomed guests", "Answered phones"],
    }
    assert result["education_training"][0] == {
        "name": "High school diploma", "provider": "", "status": "",
    }
    assert result["education_training"][1]["provider"] == "Example School"
