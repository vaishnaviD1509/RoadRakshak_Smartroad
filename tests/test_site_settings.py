"""Site settings: the AI note on the home page, footer contact details
from config, and the default-SECRET_KEY warning."""
import logging

from app import create_app
from config import Config


# --- Home page AI note --------------------------------------------------

def test_home_page_says_ai_is_off_when_no_model(client, monkeypatch):
    monkeypatch.setattr("routes.main_routes.ai_available", lambda path: False)
    body = client.get("/").data
    assert b"AI analysis is not switched on yet" in body
    assert b"The AI model is active" not in body


def test_home_page_says_ai_is_active_when_model_available(client, monkeypatch):
    monkeypatch.setattr("routes.main_routes.ai_available", lambda path: True)
    body = client.get("/").data
    assert b"The AI model is active" in body
    assert b"AI analysis is not switched on yet" not in body


def test_home_page_no_longer_shows_foundation_build_text(client):
    body = client.get("/").data
    assert b"this build represents the foundation" not in body


def test_ai_available_needs_model_file_and_library(tmp_path, monkeypatch):
    from services import damage_detection

    model = tmp_path / "m.pt"
    model.write_bytes(b"x")
    monkeypatch.setattr(damage_detection.importlib.util, "find_spec", lambda name: object())
    assert damage_detection.ai_available(str(model)) is True
    assert damage_detection.ai_available(str(tmp_path / "missing.pt")) is False
    assert damage_detection.ai_available("") is False

    monkeypatch.setattr(damage_detection.importlib.util, "find_spec", lambda name: None)
    assert damage_detection.ai_available(str(model)) is False


# --- Footer contact details ----------------------------------------------

def test_footer_uses_configured_contact_details():
    class Custom(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        CONTACT_EMAIL = "help@kalaburagi-city.example"
        HELPDESK_PHONE = "08472-123456"

    body = create_app(Custom).test_client().get("/").data
    assert b"help@kalaburagi-city.example" in body
    assert b"08472-123456" in body
    assert b"support@roadrakshak.example" not in body


# --- SECRET_KEY warning --------------------------------------------------

def test_default_secret_key_logs_a_warning(caplog):
    class DefaultKey(Config):
        TESTING = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SECRET_KEY = "dev-only-change-me"

    with caplog.at_level(logging.WARNING):
        create_app(DefaultKey)
    assert "SECRET_KEY" in caplog.text


def test_custom_secret_key_logs_no_warning(caplog):
    class RealKey(Config):
        TESTING = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SECRET_KEY = "a-long-random-value-1234567890"

    with caplog.at_level(logging.WARNING):
        create_app(RealKey)
    assert "SECRET_KEY" not in caplog.text