"""
Email utilities for transactional messages.
"""

import os
import smtplib
import logging
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_link: str, token: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    if not smtp_host or not smtp_from:
        logger.warning("SMTP not configured; skipping reset email.")
        return

    message = EmailMessage()
    message["Subject"] = "Reset your RAW Labour Hire password"
    message["From"] = smtp_from
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "We received a request to reset your password.",
                "",
                f"Reset link: {reset_link}",
                "",
                f"If the link doesn't work, use this code in the app: {token}",
                "",
                "If you didn't request this, you can ignore this email.",
            ]
        )
    )

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if use_tls:
            server.starttls()
        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)
        server.send_message(message)
