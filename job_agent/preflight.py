from __future__ import annotations

from urllib.parse import urlsplit

from .config import env
from .notify import normalize_email_address


def production_readiness(environment: dict[str, str | None] | None = None) -> list[str]:
    """Return safe, non-secret configuration errors for database auth rollout."""
    values = environment or {}

    def value(name: str, default: str = "") -> str:
        if name in values:
            return str(values.get(name) or "").strip()
        return str(env(name, default) or "").strip()

    errors: list[str] = []
    if value("APP_ENV", "development").lower() != "production":
        errors.append("APP_ENV must be production.")
    if value("AUTH_MODE", "legacy").lower() != "database":
        errors.append("AUTH_MODE must be database.")
    if not value("DATABASE_URL").startswith("postgresql+"):
        errors.append("DATABASE_URL must use PostgreSQL.")
    if len(value("SESSION_SECRET")) < 32:
        errors.append("SESSION_SECRET must contain at least 32 characters.")
    if len(value("ADMIN_PASSWORD")) < 12:
        errors.append("ADMIN_PASSWORD must contain at least 12 characters.")
    if not normalize_email_address(value("ADMIN_EMAIL")):
        errors.append("ADMIN_EMAIL must be a valid email address.")
    if value("SMTP_ENABLED").lower() not in {"1", "true", "yes", "on"}:
        errors.append("SMTP_ENABLED must be true for MFA and password reset.")
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "ALERT_EMAIL_FROM"):
        if not value(name):
            errors.append(f"{name} is required.")
    parsed = urlsplit(value("PUBLIC_BASE_URL"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
        errors.append("PUBLIC_BASE_URL must be an HTTPS origin without a path.")
    return errors


def main() -> int:
    errors = production_readiness()
    if errors:
        print("Production readiness check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Production readiness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
