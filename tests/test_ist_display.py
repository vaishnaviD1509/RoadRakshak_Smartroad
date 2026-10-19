from datetime import datetime

from flask import url_for

from models import db
from models.complaint import Complaint
from models.user import User


def _citizen_with_complaint(app, created_at):
    """A citizen and one complaint made at a known UTC time."""
    with app.app_context():
        user = User(name="Citizen Person", email="ist@example.com", role="citizen")
        user.set_password("longenough1")
        db.session.add(user)
        db.session.commit()
        complaint = Complaint(
            user_id=user.id, damage_category="Pothole",
            description="Seeded for IST tests.", location_name="MG Road",
            status="Submitted", created_at=created_at,
        )
        db.session.add(complaint)
        db.session.commit()
        return (user.id, user.name, user.role), complaint.complaint_id


def _sign_in(client, identity):
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = identity


def test_track_page_shows_times_in_ist(app, client):
    identity, complaint_id = _citizen_with_complaint(app, datetime(2026, 10, 15, 12, 0))
    _sign_in(client, identity)

    with app.test_request_context():
        url = url_for("tracking.track", complaint_id=complaint_id)
    response = client.get(url)

    assert response.status_code == 200
    assert b"15 Oct 2026, 05:30 PM IST" in response.data
    assert b" UTC" not in response.data


def test_citizen_dashboard_uses_the_ist_date(app, client):
    # 20:00 UTC is already the next day (01:30) in India.
    identity, _ = _citizen_with_complaint(app, datetime(2026, 10, 15, 20, 0))
    _sign_in(client, identity)

    with app.test_request_context():
        url = url_for("citizen.dashboard")
    response = client.get(url)

    assert response.status_code == 200
    assert b"16 Oct 2026" in response.data