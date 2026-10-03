import json

import pytest

from job_agent.job_detail_fetcher import JobDetailError, extract_job_description


def test_extracts_jobposting_json_ld_description():
    description = "<p>Lead accounting operations.</p><p>" + ("Detailed duties. " * 20) + "</p>"
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting", "description": description})
        + "</script>"
    )

    result = extract_job_description(html)

    assert "Lead accounting operations." in result
    assert "Detailed duties." in result


def test_extracts_common_job_description_container():
    html = '<main><div class="job-description">' + ("Complete role details. " * 20) + "</div></main>"

    assert "Complete role details." in extract_job_description(html)


def test_rejects_pages_without_meaningful_job_details():
    with pytest.raises(JobDetailError):
        extract_job_description("<html><body>Not found</body></html>")
