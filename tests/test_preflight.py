from job_agent.preflight import production_readiness


def ready_environment():
    return {
        "APP_ENV": "production",
        "AUTH_MODE": "database",
        "DATABASE_URL": "postgresql+psycopg://user:secret@/jobagent",
        "SESSION_SECRET": "s" * 32,
        "ADMIN_PASSWORD": "a-secure-admin-password",
        "ADMIN_EMAIL": "admin@example.com",
        "SMTP_ENABLED": "true",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_USERNAME": "smtp-user",
        "SMTP_PASSWORD": "smtp-password",
        "ALERT_EMAIL_FROM": "alerts@example.com",
        "PUBLIC_BASE_URL": "https://jobs.example.com",
    }


def test_ready_production_configuration_passes():
    assert production_readiness(ready_environment()) == []


def test_preflight_reports_rollout_blockers_without_secret_values():
    values = ready_environment()
    values.update({
        "AUTH_MODE": "legacy",
        "SMTP_ENABLED": "false",
        "SESSION_SECRET": "short",
        "PUBLIC_BASE_URL": "http://jobs.example.com/reset",
    })
    errors = production_readiness(values)
    assert "AUTH_MODE must be database." in errors
    assert "SMTP_ENABLED must be true for MFA and password reset." in errors
    assert "SESSION_SECRET must contain at least 32 characters." in errors
    assert "PUBLIC_BASE_URL must be an HTTPS origin without a path." in errors
    assert all("smtp-password" not in error for error in errors)
