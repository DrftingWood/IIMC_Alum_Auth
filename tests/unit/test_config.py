import pytest
from pydantic import ValidationError

from src.shared.config import Settings


def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")
    monkeypatch.setenv("OTP_PEPPER", "x" * 32)
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")
    monkeypatch.setenv("EMAIL_DEV_MODE", "true")

    s = Settings()
    assert s.telegram_group_chat_id == -100123
    assert s.email_dev_mode is True
    assert s.otp_pepper == "x" * 32


def test_settings_missing_pepper_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTP_PEPPER", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_loads_linkedin_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")
    monkeypatch.setenv("OTP_PEPPER", "x" * 32)
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "li-client")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "li-secret")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://example.com/oauth/linkedin/callback")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")

    from src.shared import config

    config._settings = None
    s = config.Settings()
    assert s.linkedin_client_id == "li-client"
    assert s.linkedin_client_secret == "li-secret"
    assert s.linkedin_redirect_uri == "https://example.com/oauth/linkedin/callback"
    assert s.public_base_url == "https://example.com"
