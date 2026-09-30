from pathlib import Path


def test_user_jobs_apply_action_routes_through_application_prep():
    template = Path("web/templates/jobs.html").read_text()

    assert 'href="/jobs/{{ job.id }}/application">Apply</a>' in template
    assert '>Build Resume</a>' not in template
    assert 'href="{{ job.apply_url }}" target="_blank" rel="noopener">Open</a>' not in template
    assert '<th>Status</th>' not in template
    assert 'action="/jobs/{{ job.id }}/status"' not in template


def test_administrator_can_still_view_source_job_posting():
    template = Path("web/templates/jobs.html").read_text()

    assert '>View Job</a>' in template
