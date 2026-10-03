from pathlib import Path


def test_application_tracking_is_hidden_until_package_exists():
    template = Path("web/templates/application.html").read_text()
    package_guard = template.index("{% if package %}")
    tracking = template.index("Application Tracking")
    guard_end = template.index("{% endif %}", tracking)

    assert package_guard < tracking < guard_end


def test_application_prep_shows_full_job_details():
    template = Path("web/templates/application.html").read_text()

    assert "Full Job Description" in template
    assert "{{ job.description }}" in template
    assert "Requirements and Qualifications" in template
    assert "{% for requirement in job.requirements %}" in template
    assert "A complete description was not supplied" in template
    assert "Show Complete Details" in template
    assert 'action="/jobs/{{ job.id }}/description/expand"' in template
    assert '<script src="/static/application-details.js" defer></script>' in template

    script = Path("web/static/application-details.js").read_text()
    assert 'button.textContent = "Loading Details…"' not in script
    assert 'completeDetailsButton.textContent = "Loading Details…"' in script
    assert 'window.addEventListener("pageshow", resetCompleteDetailsButton)' in script
    assert "Paste Complete Posting Details" in template
    assert 'action="/jobs/{{ job.id }}/description/manual"' in template
    assert "state.manual_job_description" in template
