import logging
import time
from typing import Any

from app.core.celery_app import celery_app


@celery_app.task(name="test_celery_task", bind=True)  # type: ignore[untyped-decorator]
def test_celery_task(self: Any, word: str) -> str:
    time.sleep(2)
    return f"Celery processed the word: {word}"


@celery_app.task(name="send_otp_email_async")  # type: ignore[untyped-decorator]
def send_otp_email_async(to: str, code: str) -> None:
    """Send an OTP code email via the configured provider (sync wrapper for Celery)."""
    from app.core.config import settings

    if settings.EMAIL_PROVIDER == "resend":
        import httpx
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": "Your Khana Bazaar login code",
                "text": f"Your one-time login code is: {code}\n\nExpires in 10 minutes.",
            },
            timeout=10,
        )
        resp.raise_for_status()
    else:
        logging.getLogger(__name__).info("EMAIL to=%s code=%s", to, code)
