from job_agent.application_builder import APPLICATION_BUILDER_PROMPT


def test_application_builder_uses_only_supported_ats_keywords():
    assert "ATS keywords" in APPLICATION_BUILDER_PROMPT
    assert "candidate_profile or candidate_resume_text supports them" in APPLICATION_BUILDER_PROMPT
    assert "Avoid keyword stuffing" in APPLICATION_BUILDER_PROMPT
    assert "candidate_resume_text" in APPLICATION_BUILDER_PROMPT
