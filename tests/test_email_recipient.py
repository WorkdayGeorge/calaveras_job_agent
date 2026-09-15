from job_agent.notify import (
    email_notify,
    normalize_email_address,
    normalize_us_phone,
)


def test_normalize_email_address_accepts_single_address():
    assert normalize_email_address(" jobs@example.com ") == "jobs@example.com"


def test_normalize_email_address_rejects_multiple_or_header_injection():
    assert normalize_email_address("one@example.com,two@example.com") is None
    assert normalize_email_address("one@example.com\nBcc: x@example.com") is None


def test_normalize_email_address_rejects_incomplete_address():
    assert normalize_email_address("jobs@example") is None


def test_normalize_us_phone():
    assert normalize_us_phone("(925) 555-1234") == "9255551234"
    assert normalize_us_phone("+1 925 555 1234") == "9255551234"
    assert normalize_us_phone("555-1234") is None


def test_email_notify_uses_settings_recipient_over_environment(monkeypatch):
    sent = []

    class SMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            sent.append(message["To"])

    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setenv("ALERT_EMAIL_TO", "old@example.com")
    monkeypatch.setattr("job_agent.notify.smtplib.SMTP", SMTP)

    success, _ = email_notify(
        {
            "title": "Test",
            "company": "Example",
            "location": "Sonora, CA",
            "freshness_status": "verified_fresh",
            "apply_url": "https://example.com/job",
        },
        {
            "fit_score": 100,
            "classification": "Test",
            "recommendation": "Test",
            "selected_resume": "focused",
            "reasoning": "Test",
            "missing_requirements": [],
        },
        "test",
        recipient="new@example.com",
        sms_phone_number="925-555-1234",
    )

    assert success is True
    assert sent == ["new@example.com", "9255551234@vtext.com"]
