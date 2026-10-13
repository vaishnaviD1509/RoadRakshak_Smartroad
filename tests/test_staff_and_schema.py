"""Staff accounts page, immediate effect of removing staff access, and the
upgrade that adds new columns to a database made by an older version."""
import sqlite3

import pytest

from app import create_app
from config import Config
from models import db
from models.complaint import Complaint
from models.schema_upgrade import upgrade_schema
from models.user import User
from services.user_service import remove_admin_access


def _make_user(app, email, role="citizen", name="Some User", password="longenough1"):
    with app.app_context():
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def _sign_in(client, app, email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        ident = (user.id, user.name, user.role)
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = ident


def _role(app, email):
    with app.app_context():
        return User.query.filter_by(email=email).first().role


@pytest.fixture
def admin(app, client):
    _make_user(app, "admin@example.com", role="admin", name="Admin Person")
    _sign_in(client, app, "admin@example.com")


# --- Staff page ---------------------------------------------------------

def test_staff_page_lists_administrators_only(app, client, admin):
    _make_user(app, "second@example.com", role="admin", name="Second Officer")
    _make_user(app, "citizen@example.com", name="Plain Citizen")
    page = client.get("/admin/staff").data.decode()
    assert "Admin Person" in page and "Second Officer" in page
    assert "Plain Citizen" not in page
    assert "(you)" in page


def test_staff_pages_need_an_admin(app, client):
    _make_user(app, "citizen@example.com")
    _sign_in(client, app, "citizen@example.com")
    assert client.get("/admin/staff").status_code == 302
    client.post("/admin/staff/add", data={"name": "X", "email": "x@example.com", "password": "longenough1"})
    with app.app_context():
        assert User.query.filter_by(email="x@example.com").first() is None


def test_new_staff_member_can_log_in_at_the_municipal_page(app, client, admin):
    client.post("/admin/staff/add", data={
        "name": "New Officer", "email": "New.Officer@Example.com", "password": "temporary-pass-1",
    })
    assert _role(app, "new.officer@example.com") == "admin"

    other = app.test_client()
    resp = other.post("/municipal/login", data={"email": "new.officer@example.com", "password": "temporary-pass-1"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/admin/")


def test_existing_citizen_is_promoted_and_keeps_their_password(app, client, admin):
    _make_user(app, "citizen@example.com", password="their-own-password")
    client.post("/admin/staff/add", data={"name": "", "email": "citizen@example.com", "password": ""})
    assert _role(app, "citizen@example.com") == "admin"

    other = app.test_client()
    resp = other.post("/municipal/login", data={"email": "citizen@example.com", "password": "their-own-password"})
    assert resp.status_code == 302


def test_staff_form_refuses_weak_or_incomplete_details(app, client, admin):
    client.post("/admin/staff/add", data={"name": "Short", "email": "short@example.com", "password": "abc"})
    client.post("/admin/staff/add", data={"name": "", "email": "noname@example.com", "password": "longenough1"})
    client.post("/admin/staff/add", data={"name": "Bad", "email": "not-an-email", "password": "longenough1"})
    with app.app_context():
        assert User.query.count() == 1  # only the signed-in admin


# --- Removing staff access ------------------------------------------------

def test_removing_access_turns_the_account_into_a_citizen(app, client, admin):
    other_id = _make_user(app, "second@example.com", role="admin")
    client.post(f"/admin/staff/{other_id}/remove")
    assert _role(app, "second@example.com") == "citizen"


def test_you_cannot_remove_your_own_access(app, client, admin):
    with app.app_context():
        my_id = User.query.filter_by(email="admin@example.com").first().id
    client.post(f"/admin/staff/{my_id}/remove")
    assert _role(app, "admin@example.com") == "admin"


def test_the_last_administrator_can_never_be_removed(app, admin):
    with app.app_context():
        only = User.query.filter_by(email="admin@example.com").first().id
        with pytest.raises(ValueError, match="At least one administrator"):
            remove_admin_access(only, acting_admin_id=999)
        assert User.query.filter_by(role="admin").count() == 1


def test_removing_a_citizen_or_unknown_account_is_refused(app, client, admin):
    citizen_id = _make_user(app, "citizen@example.com")
    client.post(f"/admin/staff/{citizen_id}/remove")
    client.post("/admin/staff/9999/remove")
    assert _role(app, "citizen@example.com") == "citizen"


def test_removed_staff_lose_access_immediately_even_with_an_old_session(app, client, admin):
    other_id = _make_user(app, "second@example.com", role="admin")
    second = app.test_client()
    _sign_in(second, app, "second@example.com")
    assert second.get("/admin/").status_code == 200

    client.post(f"/admin/staff/{other_id}/remove")

    resp = second.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302 and "/municipal/login" in resp.headers["Location"]
    with second.session_transaction() as sess:
        assert "user_id" not in sess


def test_a_deleted_account_cannot_keep_using_staff_pages(app, client, admin):
    with app.app_context():
        db.session.delete(User.query.filter_by(email="admin@example.com").first())
        db.session.commit()
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302 and "/municipal/login" in resp.headers["Location"]


# --- Upgrading an older database ------------------------------------------

OLD_COMPLAINTS_TABLE = """
CREATE TABLE complaints (
    id INTEGER PRIMARY KEY, complaint_id VARCHAR(20) NOT NULL UNIQUE, user_id INTEGER NOT NULL,
    damage_category VARCHAR(50) NOT NULL, description TEXT NOT NULL, location_name VARCHAR(255) NOT NULL,
    latitude FLOAT, longitude FLOAT, image_path VARCHAR(255), ai_prediction VARCHAR(255),
    ai_confidence FLOAT, status VARCHAR(30) NOT NULL, assigned_team VARCHAR(120),
    created_at DATETIME, updated_at DATETIME
)
"""


def _old_database(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(OLD_COMPLAINTS_TABLE)
    conn.execute(
        "INSERT INTO complaints (complaint_id, user_id, damage_category, description, location_name, status, created_at) "
        "VALUES ('RR-OLD00001', 1, 'Pothole', 'From before priority existed', 'Old Road', 'Submitted', '2026-01-01 10:00:00')"
    )
    conn.commit()
    conn.close()
    return path


def test_older_database_gets_the_priority_column_and_keeps_its_data(tmp_path):
    path = _old_database(tmp_path)

    class OldDb(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"

    app = create_app(OldDb)  # create_all + upgrade run here
    with app.app_context():
        complaint = Complaint.query.filter_by(complaint_id="RR-OLD00001").one()
        assert complaint.priority == "Normal"
        assert complaint.location_name == "Old Road"

        complaint.priority = "Urgent"
        db.session.commit()
        assert Complaint.query.one().priority == "Urgent"


def test_upgrade_is_safe_to_run_twice(tmp_path):
    path = _old_database(tmp_path)

    class OldDb(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"

    app = create_app(OldDb)
    with app.app_context():
        assert upgrade_schema(db.engine) == []  # create_app already did it


def test_a_fresh_database_needs_no_upgrade(app):
    with app.app_context():
        assert upgrade_schema(db.engine) == []