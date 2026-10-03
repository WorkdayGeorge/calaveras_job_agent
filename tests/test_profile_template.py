from pathlib import Path


def test_profile_form_always_posts_to_user_profile_save_route():
    template = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "templates"
        / "user_profile.html"
    ).read_text()

    assert (
        '<form method="post" action="/admin/users/{{ user.id }}/profile">'
        in template
    )


def test_resume_upload_uses_only_all_work_experience():
    template = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "templates"
        / "resumes.html"
    ).read_text()

    assert "All Work Experience" in template
    assert 'name="resume_type"' not in template
    assert "Import LinkedIn PDF" not in template


def test_resume_upload_button_is_disabled_during_submission():
    template = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "templates"
        / "resumes.html"
    ).read_text()

    assert 'id="resume-upload-form"' in template
    assert 'id="resume-upload-button"' in template
    assert '<script src="/static/resume-upload.js" defer></script>' in template

    script = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "static"
        / "resume-upload.js"
    ).read_text()
    assert "button.disabled = true" in script
    assert 'button.textContent = "Uploading…"' in script
