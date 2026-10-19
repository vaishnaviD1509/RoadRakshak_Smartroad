"""Email notifications to citizens when their complaint status changes.

Email is optional, like the AI model: if the mail settings are missing the
app works exactly as before and simply sends nothing. A failed email is
logged and swallowed - it must never stop a staff member's update from
being saved.

Settings are read from environment variables (put them in .env):
  MAIL_USERNAME   the sending address (required to turn email on)
  MAIL_PASSWORD   its password, e.g. a Gmail App Password (required)
  MAIL_SERVER     default smtp.gmail.com
  MAIL_PORT       default 587 (STARTTLS)
  MAIL_USE_TLS    default true
  MAIL_FROM       default: the same as MAIL_USERNAME
  APP_BASE_URL    optional, e.g. https://roadrakshak.onrender.com - adds a
                  tracking link to the email
"""
import logging
import os
import smtplib
from email.message import EmailMessage

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)


def _setting(name, default=None):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def mail_configured() -> bool:
    """True when a sending address and password have been provided."""
    return bool(_setting("MAIL_USERNAME") and _setting("MAIL_PASSWORD"))


def _skip_because_testing() -> bool:
    """Tests never send real email unless a test opts in on purpose."""
    if not has_app_context():
        return False
    config = current_app.config
    return bool(config.get("TESTING")) and not config.get("MAIL_SEND_IN_TESTS")


def build_status_message(complaint, previous_status, new_status, remarks=None) -> EmailMessage:
    """Build the email for a status change (no sending happens here)."""
    citizen = complaint.submitted_by
    sender = _setting("MAIL_FROM") or _setting("MAIL_USERNAME")

    message = EmailMessage()
    message["Subject"] = f"Road Rakshak: complaint {complaint.complaint_id} is now {new_status}"
    message["From"] = sender
    message["To"] = citizen.email

    lines = [
        f"Hello {citizen.name},",
        "",
        f"The status of your complaint {complaint.complaint_id} has changed.",
        "",
        f"Previous status: {previous_status}",
        f"New status:      {new_status}",
    ]
    if remarks:
        lines += ["", "Note from the municipal team:", remarks]

    base_url = _setting("APP_BASE_URL")
    if base_url:
        lines += ["", f"Track your complaint: {base_url.rstrip('/')}/track"]

    lines += ["", "Thank you for helping keep our roads safe.", "Road Rakshak"]
    message.set_content("\n".join(lines))
    return message


def send_status_email(complaint, previous_status, new_status, remarks=None) -> bool:
    """Email the citizen about a status change. Returns True only if sent.

    Never raises: any problem is logged and False is returned.
    """
    if _skip_because_testing() or not mail_configured():
        return False

    try:
        citizen = complaint.submitted_by
        if citizen is None or not citizen.email:
            return False

        message = build_status_message(complaint, previous_status, new_status, remarks)

        host = _setting("MAIL_SERVER", "smtp.gmail.com")
        port = int(_setting("MAIL_PORT", "587"))
        use_tls = _setting("MAIL_USE_TLS", "true").lower() != "false"

        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            server.login(_setting("MAIL_USERNAME"), _setting("MAIL_PASSWORD"))
            server.send_message(message)
        return True
    except Exception:  # noqa: BLE001 - email trouble must never break a status update
        logger.exception("Could not send the status email for %s", getattr(complaint, "complaint_id", "?"))
        return False