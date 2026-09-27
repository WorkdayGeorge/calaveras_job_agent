from __future__ import annotations

import json

from .config import env
from .profile_store import validate_candidate_profile


PROFILE_EXTRACTION_INSTRUCTIONS = """
You maintain a truthful candidate profile used to evaluate job fit.

Return JSON only, using exactly the same object structure as current_profile.
Merge facts supported by source_text into current_profile. Preserve existing
facts unless the source document clearly corrects them. Search terms describe desired
work and may be used only to improve career_targets and resume-selection rules;
they are not evidence of skills, work experience, education, or credentials.
Never infer a certification, software skill, license, or job duty that is not
explicitly supported. Preserve and strengthen truth_constraints. Coursework is
training, not employment. Keep list items concise and remove duplicates. The
profile name must be candidate_name; do not retain another candidate's name.
Populate career_targets with the enabled search terms. Extract every competency
explicitly supported by resume duties or skill sections into exactly one of the
four skills categories: accounting_office, data_technical, operations, or
transferable. Do not leave all four skill categories empty when the resume
contains supported competencies.

For every work-history entry, preserve the full description as concise
highlights. Do not return an experience entry with empty highlights when the
source includes duties, accomplishments, projects, or a narrative description.
For education and training, preserve the institution, degree or program, field
of study, attendance or completion dates, completion status, grade, activities,
and description when present. Include supported licenses, certifications, and
courses in education_training. Do not reduce a detailed education entry to only
the school name.
"""


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    return ""


def _items(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.replace("\r", "\n").split("\n")
        return [item.strip(" -•\t") for item in values if item.strip(" -•\t")]
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, dict):
        return [_text(item) for item in value.values() if _text(item)]
    return []


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = _text(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _combined_items(item: dict, *keys: str) -> list[str]:
    values = []
    for key in keys:
        values.extend(_items(item.get(key)))
    return _unique(values)


def _joined_details(item: dict, *keys: str) -> str:
    return " | ".join(_combined_items(item, *keys))


def _records(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


SKILL_ALIASES = {
    "accounting_office": (
        "accounting_office", "accounting", "office", "office_skills",
        "administrative", "administrative_skills",
    ),
    "data_technical": (
        "data_technical", "technical", "technical_skills", "technology",
        "computer", "computer_skills", "data", "data_skills",
    ),
    "operations": (
        "operations", "operational", "operational_skills", "warehouse",
        "logistics",
    ),
    "transferable": (
        "transferable", "transferable_skills", "soft_skills",
        "customer_service", "interpersonal",
    ),
}


def normalize_profile_proposal(
    proposal: dict,
    current_profile: dict,
    candidate_name: str | None = None,
    search_terms: list[str] | None = None,
) -> dict:
    """Normalize common resume-extraction shapes into the profile schema."""
    raw_skills = proposal.get("skills")
    skills = raw_skills if isinstance(raw_skills, dict) else {}
    current_skills = current_profile.get("skills", {})
    normalized_skills = {}
    for category, aliases in SKILL_ALIASES.items():
        values = []
        for alias in aliases:
            values.extend(_items(skills.get(alias)))
            values.extend(_items(proposal.get(alias)))
        if not values:
            values = _items(current_skills.get(category, []))
        normalized_skills[category] = _unique(values)
    if isinstance(raw_skills, list):
        normalized_skills["transferable"] = _unique(
            normalized_skills["transferable"] + _items(raw_skills)
        )
    experience_source = proposal.get("experience")
    if experience_source is None:
        experience_source = proposal.get(
            "work_experience", current_profile.get("experience", [])
        )
    experience = []
    for item in _records(experience_source):
        if isinstance(item, str):
            experience.append({
                "role": item.strip(), "company": "", "location": "",
                "dates": "", "highlights": [],
            })
            continue
        if not isinstance(item, dict):
            continue
        dates = _text(
            item.get("dates") or item.get("date_range")
            or item.get("period") or item.get("date")
        )
        if not dates:
            dates = " – ".join(
                value for value in (
                    _text(item.get("start_date") or item.get("start")),
                    _text(item.get("end_date") or item.get("end")),
                ) if value
            )
        experience.append({
            "role": _text(
                item.get("role") or item.get("title")
                or item.get("job_title") or item.get("position")
            ),
            "company": _text(
                item.get("company") or item.get("employer")
                or item.get("organization")
            ),
            "location": _text(item.get("location")),
            "dates": dates,
            "highlights": _combined_items(
                item,
                "highlights", "responsibilities", "duties", "achievements",
                "accomplishments", "description", "summary", "projects",
            ),
        })

    education_source = proposal.get("education_training")
    if education_source is None:
        education_source = proposal.get(
            "education", current_profile.get("education_training", [])
        )
    education_source = _records(education_source)
    for key in ("training", "courses", "certifications", "licenses"):
        education_source.extend(_records(proposal.get(key)))
    education = []
    for item in education_source:
        if isinstance(item, str):
            education.append({"name": item.strip(), "provider": "", "status": ""})
            continue
        if not isinstance(item, dict):
            continue
        name = _text(
            item.get("name") or item.get("program") or item.get("course")
            or item.get("degree") or item.get("degree_name")
            or item.get("training") or item.get("certification")
            or item.get("license")
        )
        field = _text(
            item.get("field_of_study") or item.get("field")
            or item.get("major") or item.get("specialization")
        )
        if field and field.casefold() not in name.casefold():
            name = f"{name} — {field}" if name else field
        education.append({
            "name": name,
            "provider": _text(
                item.get("provider") or item.get("institution")
                or item.get("school") or item.get("organization")
                or item.get("issuer")
            ),
            "status": _joined_details(
                item,
                "status", "dates", "date_range", "date", "grade",
                "activities", "activities_and_societies", "description",
                "details", "credential_id",
            ),
        })

    rules = proposal.get("resume_selection_rules")
    if not isinstance(rules, dict):
        rules = current_profile.get("resume_selection_rules", {})
    career_targets = _items(
        proposal.get("career_targets", current_profile.get("career_targets", []))
    )
    career_targets = _unique(career_targets + list(search_terms or []))
    return {
        "name": candidate_name or _text(proposal.get("name"))
        or _text(current_profile.get("name")),
        "location": _text(proposal.get("location"))
        or _text(current_profile.get("location")),
        "career_targets": career_targets,
        "skills": normalized_skills,
        "experience": experience,
        "education_training": education,
        "resume_selection_rules": {
            "focused": _items(rules.get("focused", [])),
            "all_work_experience": _items(rules.get("all_work_experience", [])),
        },
        "truth_constraints": _items(
            proposal.get("truth_constraints", current_profile.get("truth_constraints", []))
        ),
    }


def propose_profile_from_resume(
    resume_text: str,
    current_profile: dict,
    search_terms: list[str],
    candidate_name: str | None = None,
    source_label: str = "resume",
) -> dict:
    if not resume_text.strip():
        raise ValueError("No readable text was found in the source document.")
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI profile extraction is not configured.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    payload = {
        "current_profile": current_profile,
        "candidate_name": candidate_name or current_profile.get("name", ""),
        "search_terms": search_terms,
        "source_type": source_label,
        "source_text": resume_text[:50000],
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
    proposal = normalize_profile_proposal(
        proposal,
        current_profile,
        candidate_name=candidate_name,
        search_terms=search_terms,
    )
    errors = validate_candidate_profile(proposal)
    if errors:
        raise RuntimeError("The proposed profile was incomplete: " + " ".join(errors))
    return proposal
