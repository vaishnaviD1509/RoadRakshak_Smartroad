import pytest
from models import db
from models.user import User
from models.complaint import Complaint


def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Report road damage" in resp.data or b"Road Rakshak" in resp.data


def test_user_password_hashing(app):
    with app.app_context():
        u = User(name="Test User", email="test@example.com", role="citizen")
        u.set_password("secret123")
        assert u.password_hash != "secret123"
        assert u.check_password("secret123") is True
        assert u.check_password("wrong") is False


def test_registration_and_login_flow(client):
    # Registration validation: password too short
    resp = client.post("/register", data={
        "name": "New Citizen", "email": "new@example.com",
        "password": "short", "confirm_password": "short",
    })
    assert resp.status_code == 400

    # Successful registration
    resp = client.post("/register", data={
        "name": "New Citizen", "email": "new@example.com",
        "password": "longenough1", "confirm_password": "longenough1",
    }, follow_redirects=True)
    assert resp.status_code == 200

    # Duplicate email is rejected
    resp = client.post("/register", data={
        "name": "Dup Citizen", "email": "new@example.com",
        "password": "longenough1", "confirm_password": "longenough1",
    })
    assert resp.status_code == 400

    # Wrong password is rejected
    resp = client.post("/login", data={"email": "new@example.com", "password": "wrongpass"})
    assert resp.status_code == 401

    # Correct login succeeds and sets the session
    resp = client.post("/login", data={
        "email": "new@example.com", "password": "longenough1",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("role") == "citizen"
        assert sess.get("user_name") == "New Citizen"

    # Logout clears the session
    client.get("/logout")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_login_required_decorator_blocks_anonymous_access(app, client):
    from routes.decorators import login_required

    @app.route("/__test_protected")
    @login_required
    def _protected():
        return "secret content"

    resp = client.get("/__test_protected", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_required_decorator_blocks_citizen(app, client):
    from routes.decorators import admin_required

    @app.route("/__test_admin_only")
    @admin_required
    def _admin_only():
        return "admin content"

    client.post("/register", data={
        "name": "Plain Citizen", "email": "plain@example.com",
        "password": "longenough1", "confirm_password": "longenough1",
    })
    client.post("/login", data={"email": "plain@example.com", "password": "longenough1"})

    resp = client.get("/__test_admin_only", follow_redirects=True)
    assert resp.status_code == 200
    assert b"admin content" not in resp.data


def test_complaint_gets_unique_id(app):
    with app.app_context():
        u = User(name="Citizen", email="citizen@example.com", role="citizen")
        u.set_password("pw")
        db.session.add(u)
        db.session.commit()

        c1 = Complaint(
            user_id=u.id, damage_category="Pothole",
            description="Large pothole", location_name="MG Road",
        )
        c2 = Complaint(
            user_id=u.id, damage_category="Pothole",
            description="Another pothole", location_name="MG Road",
        )
        db.session.add_all([c1, c2])
        db.session.commit()

        assert c1.complaint_id != c2.complaint_id
        assert c1.status == "Submitted"