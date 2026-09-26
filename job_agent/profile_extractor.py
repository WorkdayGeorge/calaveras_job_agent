from __future__ import annotations

import json

from .config import env
from .profile_store import validate_candidate_profile


PROFILE_EXTRACTION_INSTRUCTIONS = """
You maintain a truthful candidate profile used to evaluate job fit.

Return JSON only, using exactly the same object structure as current_profile.
Merge facts supported by resume_text into current_profile. Preserve existing
facts unless the resume clearly corrects them. Search terms describe desired
work and may be used only to improve career_targets and resume-selection rules;
they are not evidence of skills, work experience, education, or credentials.
Never infer a certification, software skill, license, or job duty that is not
explicitly supported. Preserve and strengthen truth_constraints. Coursework is
training, not employment. Keep list items concise and remove duplicates. The
profile name must be candidate_name; do not retain another candidate's name.
"""


def propose_profile_from_resume(
    resume_text: str,
    current_profile: dict,
    search_terms: list[str],
    candidate_name: str | None = None,
) -> dict:
    if not resume_text.strip():
        raise ValueError("No readable text was found in the resume.")
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI profile extraction is not configured.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    payload = {
        "current_profile": current_profile,
        "candidate_name": candidate_name or current_profile.get("name", ""),
        "search_terms": search_terms,
        "resume_text": resume_text[:50000],
    }
    response = client.responses.create(
        model=env("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=PROFILE_EXTRACTION_INSTRUCTIONS,
        input=json.dumps(payload),
    )
    try:
        output = response.output_text.strip()
        if output.startswith("```"):
            output = output.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        proposal = json.loads(output)
    except Exception as exc:
        raise RuntimeError("The resume profile response was not valid JSON.") from exc
    if candidate_name:
        proposal["name"] = candidate_name
    errors = validate_candidate_profile(proposal)
    if errors:
        raise RuntimeError("The proposed profile was incomplete: " + " ".join(errors))
    return proposal
