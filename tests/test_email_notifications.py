from types import SimpleNamespace

import pytest
from flask import has_app_context  # noqa: F401  (kept so the import style matches other tests)

from models import db
from models.complaint import Complaint
from models.user import User
from services import email_service
from services.complaint_service import apply_status_update

STATUSES = [
    "Submitted", "Under Review", "Verified",
    "Assigned for Repair", "Repair in Progress", "Resolved", "Rejected",
]


class FakeSMTP:
    """Stands in for smtplib.SMTP so no real email is ever sent."""
    instances = []
    fail = False

    def __init__(self, host, port, timeout=None):
        if FakeSMTP.fail:
            raise OSError("connection refused")
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.messages.append(message)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail = False
    monkeypatch.setattr("services.email_service.smtplib.SMTP", FakeSMTP)
    return FakeSMTP


@pytest.fixture
def mail_env(monkeypatch):
    monkeypatch.setenv("MAIL_USERNAME", "sender@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "app-password")
    monkeypatch.setenv("MAIL_SERVER", "smtp.test.local")
    monkeypatch.setenv("MAIL_PORT", "587")
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("MAIL_USE_TLS", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)


def _fake_complaint():
    return SimpleNamespace(
        complaint_id="RR-ABCD1234",
        submitted_by=SimpleNamespace(name="Citizen Person", email="citizen@example.com"),
    )


def _seed_complaint():
    user = User(name="Citizen Person", email="citizen@example.com", role="citizen")
    user.set_password("longenough1")
    db.session.add(user)
    db.session.commit()
    complaint = Complaint(
        user_id=user.id, damage_category="Pothole", description="Seeded for email tests.",
        location_name="MG Road", status="Submitted", latitude=17.33, longitude=76.83,
    )
    db.session.add(complaint)
    db.session.commit()
    return user, complaint


def test_message_has_recipient_subject_status_and_note(mail_env):
    message = email_service.build_status_message(
        _fake_complaint(), "Submitted", "Under Review", "We are checking this."
    )
    assert message["To"] == "citizen@example.com"
    assert message["From"] == "sender@example.com"
    assert "RR-ABCD1234" in message["Subject"]
    assert "Under Review" in message["Subject"]
    body = message.get_content()
    assert "Citizen Person" in body
    assert "Submitted" in body
    assert "We are checking this." in body


def test_nothing_is_sent_when_mail_is_not_configured(app, smtp, monkeypatch):
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    app.config["MAIL_SEND_IN_TESTS"] = True
    with app.app_context():
        sent = email_service.send_status_email(_fake_complaint(), "Submitted", "Under Review")
    assert sent is False
    assert smtp.instances == []


def test_nothing_is_sent_during_tests_even_if_configured(app, smtp, mail_env):
    # TESTING is on and MAIL_SEND_IN_TESTS is not set, so real email is blocked.
    with app.app_context():
        sent = email_service.send_status_email(_fake_complaint(), "Submitted", "Under Review")
    assert sent is False
    assert smtp.instances == []


def test_email_is_sent_when_configured(app, smtp, mail_env):
    app.config["MAIL_SEND_IN_TESTS"] = True
    with app.app_context():
        sent = email_service.send_status_email(_fake_complaint(), "Submitted", "Verified", "Looks real.")
    assert sent is True
    assert len(smtp.instances) == 1
    server = smtp.instances[0]
    assert server.host == "smtp.test.local"
    assert server.port == 587
    assert server.started_tls is True
    assert server.logged_in == ("sender@example.com", "app-password")
    assert server.messages[0]["To"] == "citizen@example.com"


def test_smtp_failure_returns_false_and_does_not_raise(app, smtp, mail_env):
    app.config["MAIL_SEND_IN_TESTS"] = True
    smtp.fail = True
    with app.app_context():
        sent = email_service.send_status_email(_fake_complaint(), "Submitted", "Verified")
    assert sent is False


def test_status_change_emails_the_citizen(app, smtp, mail_env):
    app.config["MAIL_SEND_IN_TESTS"] = True
    with app.app_context():
        user, complaint = _seed_complaint()
        apply_status_update(complaint, user.id, "Under Review", None, "Checked", STATUSES)

        assert len(smtp.instances) == 1
        message = smtp.instances[0].messages[0]
        assert message["To"] == "citizen@example.com"
        assert "Under Review" in message["Subject"]
        assert "Checked" in message.get_content()


def test_remark_without_status_change_sends_no_email(app, smtp, mail_env):
    app.config["MAIL_SEND_IN_TESTS"] = True
    with app.app_context():
        user, complaint = _seed_complaint()
        apply_status_update(complaint, user.id, "Submitted", None, "Just a note", STATUSES)
        assert smtp.instances == []


def test_failed_email_does_not_block_the_status_update(app, smtp, mail_env):
    app.config["MAIL_SEND_IN_TESTS"] = True
    smtp.fail = True
    with app.app_context():
        user, complaint = _seed_complaint()
        apply_status_update(complaint, user.id, "Under Review", None, "Checked", STATUSES)
        assert Complaint.query.get(complaint.id).status == "Under Review"