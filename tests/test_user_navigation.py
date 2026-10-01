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
