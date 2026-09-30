from pathlib import Path


def test_application_tracking_is_hidden_until_package_exists():
    template = Path("web/templates/application.html").read_text()
    package_guard = template.index("{% if package %}")
    tracking = template.index("Application Tracking")
    guard_end = template.index("{% endif %}", tracking)

    assert package_guard < tracking < guard_end
