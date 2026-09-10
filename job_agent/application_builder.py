from __future__ import annotations

import json

from .config import env
from .evaluator import load_candidate_profile

APPLICATION_BUILDER_PROMPT = """
You create truthful, job-specific application materials for Joshua George.

Use ONLY facts present in candidate_profile. You may reorder, shorten, rephrase,
and emphasize supported experience, but you must never invent or exaggerate.

Hard truth rules:
- Never claim Joshua has a Google Data Analytics professional certificate.
- Google Data Analytics is coursework only; the final project was not completed.
- Never claim QuickBooks experience unless the profile explicitly says so.
- Never claim direct AP, AR, payroll, journal-entry, or tax-preparation employment
  unless the profile explicitly supports it.
- Coursework and training must be described as coursework/training, not job experience.
- Do not change employers, job titles, locations, or employment dates.
- Do not invent metrics, dollar amounts, team sizes, software, certifications, licenses,
  responsibilities, education, or achievements.
- If a job requirement is unsupported, do not imply Joshua has it.
- Tailor by emphasizing genuine transferable skills and relevant supported experience.

Return ONLY valid JSON with exactly these top-level keys:
{
  "tailored_resume": "plain-text resume",
  "cover_letter": "plain-text cover letter",
  "interview_questions": [
    {
      "question": "likely interview question",
      "talking_points": "truthful suggested talking points using supported facts"
    }
  ],
  "truth_check_notes": [
    "brief note about an important claim that was avoided, qualified, or kept as training"
  ]
}

Resume requirements:
- Keep it concise and ATS-friendly.
- Include Joshua George and Avery, CA.
- Lead with a professional summary tailored to this job.
- Include relevant skills.
- Include the most relevant supported work history.
- Include education/training with accurate status wording.
- Do not add references, salary requirements, or unsupported credentials.

Cover-letter requirements:
- Usually 3-5 short paragraphs.
- Explain fit using supported experience and transferable skills.
- Acknowledge career transition naturally when relevant.
- Do not apologize for missing qualifications or invent experience.

Interview requirements:
- Generate 6-10 likely questions for this specific job.
- Talking points must be grounded in candidate_profile.
"""

def _validate_result(result: dict) -> dict:
    required_strings = ("tailored_resume", "cover_letter")
    for key in required_strings:
        value = result.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Application builder returned invalid {key}.")

    questions = result.get("interview_questions")
    if not isinstance(questions, list):
        raise RuntimeError("Application builder returned invalid interview_questions.")

    normalized_questions = []
    for item in questions:
        if isinstance(item, str):
            normalized_questions.append({
                "question": item.strip(),
                "talking_points": "",
            })
        elif isinstance(item, dict):
            question = str(item.get("question", "")).strip()
            if question:
                normalized_questions.append({
                    "question": question,
                    "talking_points": str(item.get("talking_points", "")).strip(),
                })

    notes = result.get("truth_check_notes")
    if not isinstance(notes, list):
        notes = []

    result["tailored_resume"] = result["tailored_resume"].strip()
    result["cover_letter"] = result["cover_letter"].strip()
    result["interview_questions"] = normalized_questions
    result["truth_check_notes"] = [str(n).strip() for n in notes if str(n).strip()]
    return result

def build_application_materials(job: dict, profile: dict | None = None) -> dict:
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    if profile is None:
        profile = load_candidate_profile()

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    payload = {
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "employment_type": job.get("employment_type"),
            "description": job.get("description"),
            "requirements": job.get("requirements") or [],
            "source": job.get("source"),
        },
        "candidate_profile": profile,
    }

    response = client.responses.create(
        model=env("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=APPLICATION_BUILDER_PROMPT,
        input=json.dumps(payload),
    )

    try:
        result = json.loads(response.output_text)
    except Exception as exc:
        preview = response.output_text[:500]
        raise RuntimeError(
            f"Application builder returned non-JSON output: {preview}"
        ) from exc

    return _validate_result(result)
