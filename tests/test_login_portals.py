"""Tests for the separate citizen and municipal login portals."""
from models import db
from models.user import User


def _make_user(app, email, role="citizen", password="longenough1"):
    with app.app_context():
        u = User(name=f"{role.title()} User", email=email, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()


def _post(client, path, email, password="longenough1", **kwargs):
    return client.post(path, data={"email": email, "password": password}, **kwargs)


def test_both_login_pages_load(client):
    assert client.get("/login").status_code == 200
    assert b"Citizen login" in client.get("/login").data
    assert client.get("/municipal/login").status_code == 200
    assert b"Municipal login" in client.get("/municipal/login").data


def test_citizen_logs_in_through_citizen_portal(app, client):
    _make_user(app, "c@example.com")
    resp = _post(client, "/login", "c@example.com")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["role"] == "citizen"


def test_admin_logs_in_through_municipal_portal(app, client):
    _make_user(app, "a@example.com", role="admin")
    resp = _post(client, "/municipal/login", "a@example.com")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/")
    with client.session_transaction() as sess:
        assert sess["role"] == "admin"


def test_admin_cannot_use_citizen_portal(app, client):
    _make_user(app, "a@example.com", role="admin")
    resp = _post(client, "/login", "a@example.com")
    assert resp.status_code == 403
    assert b"municipal login" in resp.data.lower()
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_citizen_cannot_use_municipal_portal(app, client):
    _make_user(app, "c@example.com")
    resp = _post(client, "/municipal/login", "c@example.com")
    assert resp.status_code == 403
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_wrong_password_is_401_on_both_portals(app, client):
    _make_user(app, "c@example.com")
    _make_user(app, "a@example.com", role="admin")
    assert _post(client, "/login", "c@example.com", "nope").status_code == 401
    assert _post(client, "/municipal/login", "a@example.com", "nope").status_code == 401


def test_wrong_portal_hint_not_shown_without_correct_password(app, client):
    """A wrong password must not reveal that the account is a staff account."""
    _make_user(app, "a@example.com", role="admin")
    resp = _post(client, "/login", "a@example.com", "wrongpass")
    assert resp.status_code == 401
    assert b"This is the citizen login" not in resp.data
    assert b"This is the municipal staff login" not in resp.data


def test_unknown_email_gets_same_error_as_wrong_password(app, client):
    resp = _post(client, "/municipal/login", "ghost@example.com")
    assert resp.status_code == 401


def test_admin_pages_send_anonymous_users_to_municipal_login(app, client):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/municipal/login" in resp.headers["Location"]


def test_citizen_pages_send_anonymous_users_to_citizen_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].split("?")[0].endswith("/login")
    assert "/municipal" not in resp.headers["Location"]


def test_next_url_is_followed_when_safe(app, client):
    _make_user(app, "a@example.com", role="admin")
    resp = _post(client, "/municipal/login?next=/admin/analytics", "a@example.com")
    assert resp.headers["Location"].endswith("/admin/analytics")


def test_open_redirect_via_next_is_ignored(app, client):
    _make_user(app, "c@example.com")
    resp = _post(client, "/login?next=//evil.example.com", "c@example.com")
    assert resp.status_code == 302
    assert "evil.example.com" not in resp.headers["Location"]


def test_admin_logout_returns_to_municipal_login(app, client):
    _make_user(app, "a@example.com", role="admin")
    _post(client, "/municipal/login", "a@example.com")
    resp = client.get("/logout", follow_redirects=False)
    assert "/municipal/login" in resp.headers["Location"]