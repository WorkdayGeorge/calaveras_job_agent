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


def test_linkedin_profile_source_is_identified_in_extraction_payload(monkeypatch):
    proposal = valid_profile()
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_text=json.dumps(proposal))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", lambda api_key: client)

    propose_profile_from_resume(
        "LinkedIn profile text",
        valid_profile(),
        [],
        source_label="LinkedIn profile",
    )

    payload = json.loads(captured["input"])
    assert payload["source_type"] == "LinkedIn profile"
    assert payload["source_text"] == "LinkedIn profile text"
    assert "resume_text" not in payload


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
    proposal["career_targets"] = []
    proposal["skills"] = {
        "office_skills": ["Microsoft Office"],
        "technical_skills": ["Computer troubleshooting"],
        "customer_service": ["Guest service"],
    }

    result = normalize_profile_proposal(
        proposal,
        valid_profile(),
        candidate_name="Monte O. George IV",
        search_terms=["Hotel Front Desk"],
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
    assert result["career_targets"] == ["Hotel Front Desk"]
    assert result["skills"]["accounting_office"] == ["Microsoft Office"]
    assert result["skills"]["data_technical"] == ["Computer troubleshooting"]
    assert result["skills"]["transferable"] == ["Guest service"]


def test_linkedin_details_are_preserved_in_highlights_and_education():
    proposal = valid_profile()
    proposal["experience"] = [{
        "title": "Workday Integration Consultant",
        "company": "Example Consulting",
        "start_date": "January 2020",
        "end_date": "June 2025",
        "description": "Built Workday integrations\nSupported production releases",
        "projects": ["Automated reconciliation reporting"],
    }]
    proposal["education_training"] = [{
        "school": "Example College",
        "degree_name": "Certificate",
        "field_of_study": "Accounting and Bookkeeping",
        "dates": "2024-2025",
        "activities_and_societies": "Accounting Club",
        "description": "Completed coursework; final certification not awarded.",
    }]
    proposal["certifications"] = [{
        "name": "Excel Essential Training",
        "issuer": "LinkedIn Learning",
        "date": "2025",
    }]

    result = normalize_profile_proposal(proposal, valid_profile())

    assert result["experience"][0]["dates"] == "January 2020 – June 2025"
    assert result["experience"][0]["highlights"] == [
        "Built Workday integrations",
        "Supported production releases",
        "Automated reconciliation reporting",
    ]
    assert result["education_training"][0] == {
        "name": "Certificate — Accounting and Bookkeeping",
        "provider": "Example College",
        "status": (
            "2024-2025 | Accounting Club | "
            "Completed coursework; final certification not awarded."
        ),
    }
    assert result["education_training"][1] == {
        "name": "Excel Essential Training",
        "provider": "LinkedIn Learning",
        "status": "2025",
    }
