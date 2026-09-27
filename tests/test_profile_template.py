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


def test_linkedin_import_is_separate_from_application_resumes():
    template = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "templates"
        / "resumes.html"
    ).read_text()

    assert 'name="resume_type" value="linkedin-profile"' in template
    assert 'accept=".pdf,application/pdf"' in template
    assert "Import LinkedIn PDF" in template
