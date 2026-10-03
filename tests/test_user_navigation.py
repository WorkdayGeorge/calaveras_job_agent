from pathlib import Path


def test_completed_user_navigation_omits_dashboard_and_setup():
    template = Path("web/templates/base.html").read_text()
    user_navigation = template.split(
        '{% if request.session.get("role", "administrator") != "administrator" %}',
        1,
    )[1].split("{% endif %}", 1)[0]

    assert '>Dashboard</a>' not in user_navigation
    assert 'href="/jobs">Jobs</a>' in user_navigation
    assert 'request.session.get("onboarding_complete") is sameas false' in template


def test_admin_navigation_manages_profiles_through_users():
    template = Path("web/templates/base.html").read_text()
    admin_navigation = template.split(
        '<aside class="admin-sidebar" aria-label="Administrator navigation">',
        1,
    )[1].split("</aside>", 1)[0]

    assert 'href="/admin/users"' in admin_navigation
    assert 'href="/resumes"' in admin_navigation
    assert 'href="/profile"' not in admin_navigation
    assert 'href="/application-assistant"' not in admin_navigation
    assert 'href="/onboarding"' not in admin_navigation
    assert "My Account" not in admin_navigation
