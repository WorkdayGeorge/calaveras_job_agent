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
