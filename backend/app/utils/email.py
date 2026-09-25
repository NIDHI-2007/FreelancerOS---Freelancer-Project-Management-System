"""SMTP delivery helpers."""

import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def smtp_is_configured():
    config = current_app.config
    return bool(config.get("SMTP_HOST") and config.get("SMTP_FROM"))


def send_password_reset_email(recipient, reset_url):
    config = current_app.config
    if not smtp_is_configured():
        raise RuntimeError("SMTP_HOST and SMTP_FROM must be configured to send reset mail.")

    message = EmailMessage()
    message["Subject"] = "Reset your FreelanceOS password"
    message["From"] = config["SMTP_FROM"]
    message["To"] = recipient
    message.set_content(
        "We received a request to reset your FreelanceOS password.\n\n"
        f"Use this one-time link within {config['PASSWORD_RESET_TOKEN_MINUTES']} minutes:\n"
        f"{reset_url}\n\n"
        "If you did not request this reset, you can ignore this email."
    )

    with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=15) as server:
        if config["SMTP_USE_TLS"]:
            server.starttls(context=ssl.create_default_context())
        if config.get("SMTP_USER"):
            server.login(config["SMTP_USER"], config.get("SMTP_PASSWORD", ""))
        server.send_message(message)
