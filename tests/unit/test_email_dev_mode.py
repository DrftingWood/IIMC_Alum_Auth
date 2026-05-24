import httpx
import pytest
import respx

from src.shared.email import send_otp_email


@pytest.mark.asyncio
async def test_dev_mode_writes_to_outbox(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EMAIL_DEV_MODE", "true")
    from src.shared import config

    config._settings = None  # reset cache

    await send_otp_email(to="user@example.com", code="123456")

    out = capsys.readouterr().out
    assert "user@example.com" in out
    assert "123456" in out


@pytest.mark.asyncio
async def test_brevo_mode_calls_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_DEV_MODE", "false")
    monkeypatch.setenv("BREVO_API_KEY", "fake-key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")
    from src.shared import config

    config._settings = None

    with respx.mock(base_url="https://api.brevo.com") as r:
        route = r.post("/v3/smtp/email").mock(
            return_value=httpx.Response(201, json={"messageId": "abc"})
        )
        await send_otp_email(to="user@example.com", code="654321")
        assert route.called
        request = route.calls.last.request
        body = request.read().decode()
        assert "user@example.com" in body
        assert "654321" in body
        assert request.headers["api-key"] == "fake-key"
