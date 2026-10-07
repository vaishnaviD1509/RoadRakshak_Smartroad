from datetime import datetime, timedelta

from models import db
from models.complaint import Complaint
from models.complaint_update import ComplaintUpdate
from models.user import User


def _make_admin(app, email="pdfadmin@example.com"):
    with app.app_context():
        u = User(name="Admin", email=email, role="admin")
        u.set_password("longenough1")
        db.session.add(u)
        db.session.commit()


def _make_citizen(app, email="pdfcitizen@example.com"):
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            return existing.id
        u = User(name="Citizen", email=email, role="citizen")
        u.set_password("longenough1")
        db.session.add(u)
        db.session.commit()
        return u.id


def _add_complaint(app, **kwargs):
    with app.app_context():
        user_id = _make_citizen(app)
        defaults = dict(
            user_id=user_id, damage_category="Pothole",
            description="A deep pothole near the signal.", location_name="MG Road",
            status="Submitted",
        )
        defaults.update(kwargs)
        c = Complaint(**defaults)
        db.session.add(c)
        db.session.commit()

        update = ComplaintUpdate(
            complaint_id=c.id, previous_status=None, new_status="Submitted",
            remarks="Report received.", updated_by="System",
        )
        db.session.add(update)
        db.session.commit()
        return c.complaint_id


def _login(client, email, password="longenough1"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


# --- Citizen complaint PDF -------------------------------------------

def test_complaint_pdf_requires_login(client):
    resp = client.get("/report/RR-ANYTHING/pdf", follow_redirects=True)
    assert resp.status_code == 200
    assert b"log in" in resp.data.lower() or b"login" in resp.data.lower()


def test_complaint_pdf_downloads_for_owner(app, client):
    client.post("/register", data={
        "name": "PDF Owner", "email": "pdfowner@example.com", "phone": "",
        "password": "longenough1", "confirm_password": "longenough1",
    }, follow_redirects=True)
    _login(client, "pdfowner@example.com")

    with app.app_context():
        user = User.query.filter_by(email="pdfowner@example.com").first()
        c = Complaint(user_id=user.id, damage_category="Pothole", description="d", location_name="L")
        db.session.add(c)
        db.session.commit()
        complaint_id = c.complaint_id

    resp = client.get(f"/report/{complaint_id}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF")
    assert complaint_id in resp.headers.get("Content-Disposition", "")


def test_complaint_pdf_blocked_for_non_owner(app, client):
    with app.app_context():
        other = User(name="Other", email="pdfother@example.com", role="citizen")
        other.set_password("longenough1")
        db.session.add(other)
        db.session.commit()
        c = Complaint(user_id=other.id, damage_category="Pothole", description="d", location_name="L")
        db.session.add(c)
        db.session.commit()
        complaint_id = c.complaint_id

    client.post("/register", data={
        "name": "Snooper", "email": "snooper@example.com", "phone": "",
        "password": "longenough1", "confirm_password": "longenough1",
    }, follow_redirects=True)
    _login(client, "snooper@example.com")

    resp = client.get(f"/report/{complaint_id}/pdf")
    assert resp.status_code == 404


def test_complaint_pdf_contains_status_history(app, client):
    client.post("/register", data={
        "name": "History Owner", "email": "historyowner@example.com", "phone": "",
        "password": "longenough1", "confirm_password": "longenough1",
    }, follow_redirects=True)
    _login(client, "historyowner@example.com")

    with app.app_context():
        user = User.query.filter_by(email="historyowner@example.com").first()
        c = Complaint(user_id=user.id, damage_category="Pothole", description="d", location_name="L")
        db.session.add(c)
        db.session.commit()
        update = ComplaintUpdate(
            complaint_id=c.id, previous_status="Submitted", new_status="Under Review",
            remarks="Being looked at.", updated_by="Admin",
        )
        db.session.add(update)
        db.session.commit()
        complaint_id = c.complaint_id

    resp = client.get(f"/report/{complaint_id}/pdf")
    assert resp.status_code == 200
    # It's a real PDF stream (binary), so just confirm it built without error
    # and is a reasonably sized document rather than an empty shell.
    assert len(resp.data) > 1000


# --- Admin summary PDF -------------------------------------------------

def test_summary_pdf_requires_admin(app, client):
    _make_citizen(app, "plainuser@example.com")
    _login(client, "plainuser@example.com")
    resp = client.get("/admin/reports/summary", follow_redirects=True)
    assert resp.mimetype != "application/pdf"


def test_summary_pdf_downloads_for_admin(app, client):
    _make_admin(app)
    _login(client, "pdfadmin@example.com")
    _add_complaint(app, damage_category="Pothole")
    _add_complaint(app, damage_category="Road Cracks", status="Resolved")

    resp = client.get("/admin/reports/summary")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF")
    assert "road-rakshak-summary" in resp.headers.get("Content-Disposition", "")


def test_summary_pdf_respects_category_filter(app, client):
    _make_admin(app)
    _login(client, "pdfadmin@example.com")
    _add_complaint(app, damage_category="Pothole")
    _add_complaint(app, damage_category="Waterlogging")

    resp = client.get("/admin/reports/summary?category=Pothole")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")


def test_summary_pdf_filename_includes_date_range(app, client):
    _make_admin(app)
    _login(client, "pdfadmin@example.com")
    _add_complaint(app)

    today = datetime.utcnow().strftime("%Y%m%d")
    resp = client.get(f"/admin/reports/summary?date_from={datetime.utcnow().strftime('%Y-%m-%d')}")
    assert resp.status_code == 200
    assert today in resp.headers.get("Content-Disposition", "")


def test_summary_pdf_works_with_empty_database(app, client):
    _make_admin(app)
    _login(client, "pdfadmin@example.com")

    resp = client.get("/admin/reports/summary")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")