import pytest

from models import db
from models.user import User
from services.user_service import create_or_promote_admin


def test_creates_a_new_admin(app):
    with app.app_context():
        user, created = create_or_promote_admin("New.Admin@Example.com", name="New Admin", password="longenough1")
        assert created is True
        assert user.email == "new.admin@example.com"
        assert user.role == "admin"
        assert user.check_password("longenough1")
        assert user.password_hash != "longenough1"


def test_promoting_an_existing_user_keeps_their_password(app):
    with app.app_context():
        existing = User(name="Already Here", email="here@example.com", role="citizen")
        existing.set_password("theirOwnPassword1")
        db.session.add(existing)
        db.session.commit()

        user, created = create_or_promote_admin("here@example.com")
        assert created is False
        assert user.role == "admin"
        assert user.check_password("theirOwnPassword1")


@pytest.mark.parametrize("kwargs, message", [
    ({"email": "not-an-email", "name": "X", "password": "longenough1"}, "valid email"),
    ({"email": "a@example.com", "name": "", "password": "longenough1"}, "name is required"),
    ({"email": "a@example.com", "name": "X", "password": "short"}, "at least 8"),
])
def test_invalid_input_is_refused(app, kwargs, message):
    with app.app_context():
        with pytest.raises(ValueError, match=message):
            create_or_promote_admin(**kwargs)
        assert User.query.count() == 0