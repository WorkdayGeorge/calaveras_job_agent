import json
from types import SimpleNamespace

import openai

from job_agent.profile_extractor import propose_profile_from_resume
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
