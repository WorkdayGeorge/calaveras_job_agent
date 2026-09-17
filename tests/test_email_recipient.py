from job_agent.notify import (
    email_high_priority_digest,
    email_notify,
    normalize_email_address,
)


def test_normalize_email_address_accepts_single_address():
    assert normalize_email_address(" jobs@example.com ") == "jobs@example.com"


def test_normalize_email_address_rejects_multiple_or_header_injection():
    assert normalize_email_address("one@example.com,two@example.com") is None
    assert normalize_email_address("one@example.com\nBcc: x@example.com") is None


def test_normalize_email_address_rejects_incomplete_address():
    assert normalize_email_address("jobs@example") is None


def test_email_notify_uses_settings_recipient_over_environment(monkeypatch):
    sent = {}

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
            sent["to"] = message["To"]

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
    )

    assert success is True
    assert sent["to"] == "new@example.com"


def test_digest_includes_last_30_days_threshold_section(monkeypatch):
    sent = {}

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
            sent["subject"] = message["Subject"]
            sent["body"] = message.get_content()

    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("job_agent.notify.smtplib.SMTP", SMTP)

    success, detail = email_high_priority_digest(
        [],
        recipient="jobs@example.com",
        recent_immediate_items=[
            (
                {
                    "title": "Accounting Technician",
                    "company": "Example Agency",
                    "location": "Sonora, CA",
                    "apply_url": "https://example.com/job",
                },
                {
                    "fit_score": 82,
                    "classification": "Strong fit",
                    "recommendation": "Apply",
                    "evaluated_at": "2026-09-16T18:30:00+00:00",
                },
            )
        ],
        immediate_alert_score=75,
    )

    assert success is True
    assert detail == "sent"
    assert sent["subject"] == "High-Priority Job Digest — 0 new, 1 recent"
    assert "Last 30 Days — Immediate Alert Threshold" in sent["body"]
    assert "met or exceeded 75/100" in sent["body"]
    assert "Accounting Technician" in sent["body"]
    assert "2026-09-16T18:30:00+00:00" in sent["body"]


def test_digest_preview_can_send_empty_sections(monkeypatch):
    sent = {}

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
            sent["subject"] = message["Subject"]
            sent["body"] = message.get_content()

    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("job_agent.notify.smtplib.SMTP", SMTP)

    success, _ = email_high_priority_digest(
        [],
        recipient="jobs@example.com",
        recent_immediate_items=[],
        immediate_alert_score=75,
        subject_prefix="[TEST] ",
        allow_empty=True,
    )

    assert success is True
    assert sent["subject"] == "[TEST] High-Priority Job Digest — 0 new, 0 recent"
    assert "No newly queued jobs" in sent["body"]
    assert "No qualifying jobs in the last 30 days" in sent["body"]
