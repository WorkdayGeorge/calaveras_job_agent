from __future__ import annotations

import json
from typing import Any

from .config import env


SEARCH_TERM_INSTRUCTIONS = """
You create practical job-board search phrases from a candidate resume.

Return JSON only as an array of strings. Suggest 6 to 15 concise phrases a
candidate would realistically type into a job search. Prefer common job titles,
recognized title variants, and specialty phrases supported by the resume.
Include both current-experience roles and reasonable adjacent roles when the
resume directly supports them. Do not invent credentials, licenses, seniority,
or experience. Avoid employer names, locations, sentences, vague traits, and
isolated software or skill names unless they are commonly used as a job-search
phrase. Each phrase must contain no more than eight words.
"""


def normalize_resume_search_terms(value: Any, *, limit: int = 15) -> list[str]:
    if not isinstance(value, list):
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        term = " ".join(item.split()).strip(" ,.;:-")
        key = term.casefold()
        if not term or len(term) > 100 or len(term.split()) > 8 or key in seen:
            continue
        seen.add(key)
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def propose_search_terms_from_resume(
    resume_text: str,
    existing_terms: list[str] | None = None,
) -> list[str]:
    if not str(resume_text or "").strip():
        raise ValueError("No readable text was found in the resume.")
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI search-term generation is not configured.")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=env("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=SEARCH_TERM_INSTRUCTIONS,
        input=json.dumps({
            "existing_terms": list(existing_terms or []),
            "resume_text": resume_text[:50000],
        }),
    )
    try:
        output = response.output_text.strip()
        if output.startswith("```"):
            output = output.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        suggestions = json.loads(output)
    except Exception as exc:
        raise RuntimeError("The resume search-term response was not valid JSON.") from exc
    return normalize_resume_search_terms(suggestions)
