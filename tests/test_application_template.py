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
    assert '<script src="/static/application-details.js?v=20261003-4" defer></script>' in template

    script = Path("web/static/application-details.js").read_text()
    assert 'button.textContent = "Loading Details…"' not in script
    assert 'completeDetailsButton.textContent = "Loading Details…"' in script
    assert 'window.addEventListener("pageshow", function ()' in script
    assert "resetCompleteDetailsButton();" in script
    assert "Paste Complete Posting Details" not in template
    assert "Pull Description from Job Posting and Paste Below" in template
    assert 'action="/jobs/{{ job.id }}/description/manual"' in template
    assert "Generate Resume and Cover Letter" in template
    assert "Save Posting Details" not in template
    assert "state.manual_job_description" in template
    assert 'id="manual-details-section"' in template
    assert "{% if not show_manual_details %} hidden{% endif %}" in template
    assert "{% if not package and details_ready %}" in template
    assert "COMPLETE_DETAILS_TIMEOUT_MS = 20000" in script
    assert "controller.abort()" in script
    assert "manualDetailsSection.hidden = false" in script
    assert "completeDetailsForm.hidden = true" in script
    manual_section = template.split('id="manual-details-section"', 1)[1]
    assert 'href="{{ job.apply_url }}"' in manual_section
    assert 'class="btn"' in manual_section
    assert "Pull Description from Job Posting and Paste Below" in manual_section
    assert "state and state.manual_job_description" in manual_section
    assert "Apply" in manual_section
    assert "Complete details could not be loaded. Copy the posting's" not in manual_section
    assert "request.query_params.get(\"message\") and not show_manual_details" in template
    assert "{% if show_manual_details %} hidden{% endif %}" in template
    assert "completeDetailsMessage.hidden = true" in script
    assert 'id="job-description-content"' in template
    assert 'jobDescriptionContent.hidden = true' in script
    header = template.split('{% if request.query_params.get("message")', 1)[0]
    assert 'href="{{ job.apply_url }}"' not in header


def test_manual_posting_save_triggers_package_generation():
    app_source = Path("web/app.py").read_text()

    manual_handler = app_source.split(
        'def save_manual_job_description(',
        1,
    )[1].split(
        '@app.post("/jobs/{job_id}/application/build")',
        1,
    )[0]
    assert "state.manual_job_description = details" in manual_handler
    assert "session.commit()" in manual_handler
    assert "return build_application_package(job_id, request)" in manual_handler


def test_application_prep_action_colors():
    template = Path("web/templates/application.html").read_text()

    assert 'id="complete-details-button" class="btn"' in template
    assert 'id="generate-application-button" class="btn good"' in template
    assert "Generate Resume and Cover Letter</button>" in template


def test_generation_button_waits_for_complete_manual_description():
    template = Path("web/templates/application.html").read_text()
    script = Path("web/static/application-details.js").read_text()

    assert 'id="posting-details"' in template
    assert 'minlength="100"' in template
    assert 'id="generate-application-button"' in template
    assert "state.manual_job_description|trim|length < 100" in template
    assert "postingDetails.value.trim().length < 100" in script
    assert 'postingDetails.addEventListener("input"' in script
    assert "updateGenerateApplicationButton();" in script
