import httpx

from src.shared.config import get_settings


async def send_otp_email(*, to: str, code: str) -> None:
    """Send a 6-digit OTP. In EMAIL_DEV_MODE prints to stdout instead of calling Brevo."""
    settings = get_settings()
    subject = "Your IIM C Alumni verification code"
    body_html = (
        f"<p>Your verification code is <strong>{code}</strong>.</p>"
        f"<p>It expires in 10 minutes and can be used once.</p>"
        f"<p>If you didn't request this, you can ignore this email.</p>"
    )
    body_text = (
        f"Your verification code is {code}.\n"
        f"It expires in 10 minutes and can be used once.\n"
        f"If you didn't request this, you can ignore this email."
    )

    if settings.email_dev_mode:
        print(f"[DEV EMAIL] to={to} subject={subject!r} code={code}")  # noqa: T201
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": settings.brevo_api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json={
                "sender": {
                    "email": settings.brevo_from_email,
                    "name": settings.brevo_from_name,
                },
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": body_html,
                "textContent": body_text,
            },
        )
        resp.raise_for_status()
