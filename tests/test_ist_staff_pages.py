from datetime import datetime

from flask import url_for

from models import db
from models.complaint import Complaint
from models.user import User


def _admin_and_complaint(app, created_at):
    """A staff account, a citizen and one complaint made at a known UTC time."""
    with app.app_context():
        admin = User(name="Admin Person", email="ist-admin@example.com", role="admin")
        admin.set_password("longenough1")
        citizen = User(name="Citizen Person", email="ist-citizen@example.com", role="citizen")
        citizen.set_password("longenough1")
        db.session.add_all([admin, citizen])
        db.session.commit()

        complaint = Complaint(
            user_id=citizen.id, damage_category="Pothole",
            description="Seeded for IST staff page tests.", location_name="MG Road",
            status="Submitted", latitude=17.33, longitude=76.83, created_at=created_at,
        )
        db.session.add(complaint)
        db.session.commit()
        return (admin.id, admin.name, admin.role), complaint.complaint_id


def _sign_in(client, identity):
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = identity


def test_staff_complaint_page_shows_times_in_ist(app, client):
    identity, complaint_id = _admin_and_complaint(app, datetime(2026, 10, 15, 12, 0))
    _sign_in(client, identity)

    with app.test_request_context():
        url = url_for("admin.complaint_detail", complaint_id=complaint_id)
    response = client.get(url)

    assert response.status_code == 200
    assert b"15 Oct 2026, 05:30 PM IST" in response.data
    assert b" UTC" not in response.data


def test_staff_dashboard_uses_the_ist_date(app, client):
    # 20:00 UTC is already the next day (01:30) in India.
    identity, _ = _admin_and_complaint(app, datetime(2026, 10, 15, 20, 0))
    _sign_in(client, identity)

    with app.test_request_context():
        url = url_for("admin.dashboard")
    response = client.get(url)

    assert response.status_code == 200
    assert b"16 Oct 2026" in response.data


def test_staff_accounts_page_still_loads(app, client):
    identity, _ = _admin_and_complaint(app, datetime(2026, 10, 15, 12, 0))
    _sign_in(client, identity)

    with app.test_request_context():
        url = url_for("admin.staff")
    response = client.get(url)

    assert response.status_code == 200
    assert b"Staff accounts" in response.data