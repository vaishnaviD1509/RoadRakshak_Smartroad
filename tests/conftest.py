import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from config import Config
from services.damage_detection import reset_model_cache


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    # Tests must behave the same on every machine, whether or not a trained
    # model exists in ai_models/. Point the app at a file that never exists.
    AI_MODEL_PATH = os.path.join("ai_models", "this_model_does_not_exist.pt")


@pytest.fixture
def app():
    reset_model_cache()
    app = create_app(TestConfig)
    yield app
    reset_model_cache()


@pytest.fixture
def client(app):
    return app.test_client()