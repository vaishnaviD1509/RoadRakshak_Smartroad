import io
import os

import pytest
from PIL import Image

from app import create_app
from config import Config
from models import db
from models.complaint import Complaint
from models.complaint_update import ComplaintUpdate
from models.repair_evidence import RepairEvidence
from models.user import User


@pytest.fixture
def app(tmp_path):
    """App whose uploads go to a throwaway folder, so tests leave nothing behind."""
    class UploadsInTmp(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        UPLOAD_FOLDER = str(tmp_path)
    return create_app(UploadsInTmp)


def _make_user(app, email, role="citizen", name="Some User"):
    with app.app_context():
        user = User(name=name, email=email, role=role)
        user.set_password("longenough1")
        db.session.add(user)
        db.session.commit()
        return user.id


def _sign_in(client, app, email):
    """Put the user's identity straight into the session (login itself is tested elsewhere)."""
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        ident = (user.id, user.name, user.role)
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = ident


def _make_complaint(app, owner_email, location="MG Road", status="Submitted", **extra):
    with app.app_context():
        owner = User.query.filter_by(email=owner_email).first()
        c = Complaint(
            user_id=owner.id, damage_category="Pothole",
            description="Seeded for admin tests.", location_name=location,
            status=status, latitude=extra.pop("latitude", 17.33),
            longitude=extra.pop("longitude", 76.83), **extra,
        )
        db.session.add(c)
        db.session.commit()
        return c.complaint_id


def _get(app, cid):
    with app.app_context():
        return Complaint.query.filter_by(complaint_id=cid).first()


def _jpeg(color=(90, 120, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color=color).save(buf, format="JPEG")
    buf.seek(0)
    return buf


@pytest.fixture
def setup(app, client):
    """An admin, a citizen who owns one complaint, and the complaint's ID."""
    _make_user(app, "admin@example.com", role="admin", name="Admin Person")
    _make_user(app, "citizen@example.com", name="Citizen Person")
    cid = _make_complaint(app, "citizen@example.com")
    return cid


# --- Access control -----------------------------------------------------

def test_admin_pages_require_login(client, setup):
    for path in ("/admin/", f"/admin/complaints/{setup}"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


def test_citizen_cannot_open_admin_pages(app, client, setup):
    _sign_in(client, app, "citizen@example.com")
    for path in ("/admin/", f"/admin/complaints/{setup}"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" not in resp.headers["Location"]


def test_citizen_cannot_use_admin_actions(app, client, setup):
    _sign_in(client, app, "citizen@example.com")
    client.post(f"/admin/complaints/{setup}/status", data={"status": "Verified"})
    client.post(f"/admin/complaints/{setup}/classification", data={"classification": "Road Cracks"})
    client.post(f"/admin/complaints/{setup}/evidence", data={
        "kind": "After repair", "photo": (_jpeg(), "x.jpg"),
    }, content_type="multipart/form-data")

    c = _get(app, setup)
    assert c.status == "Submitted"
    assert c.ai_prediction is None
    with app.app_context():
        assert RepairEvidence.query.count() == 0


def test_csrf_is_enforced_on_admin_actions_outside_testing(setup):
    class RealCsrf(Config):
        TESTING = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    app = create_app(RealCsrf)
    _make_user(app, "root@example.com", role="admin")
    cid = _make_complaint(app, "root@example.com")
    client = app.test_client()
    _sign_in(client, app, "root@example.com")

    resp = client.post(f"/admin/complaints/{cid}/status", data={"status": "Verified"})
    assert resp.status_code == 400
    assert _get(app, cid).status == "Submitted"


def test_admin_login_lands_on_admin_dashboard(app, client, setup):
    resp = client.post("/login", data={"email": "admin@example.com", "password": "longenough1"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/")


# --- Dashboard ----------------------------------------------------------

def test_dashboard_summary_counts(app, client, setup):
    for status in ["Under Review", "Verified", "Assigned for Repair", "Repair in Progress", "Resolved", "Rejected"]:
        _make_complaint(app, "citizen@example.com", location=f"Road {status}", status=status)
    _sign_in(client, app, "admin@example.com")

    html = client.get("/admin/").data.decode()

    def number_before(label):
        chunk = html[:html.index(label)]
        start = chunk.rindex('rr-stat-number">') + len('rr-stat-number">')
        return int(chunk[start:chunk.index("<", start)])

    assert number_before("Total complaints") == 7
    assert number_before(">New<") == 1
    assert number_before("Awaiting verification") == 1
    assert number_before("Assigned or in repair") == 2
    assert number_before(">Resolved<") == 1


def test_dashboard_status_filter(app, client, setup):
    _make_complaint(app, "citizen@example.com", location="Verified Lane", status="Verified")
    _sign_in(client, app, "admin@example.com")

    body = client.get("/admin/?status=Verified").data.decode()
    # The filter applies to the table; the overview map intentionally shows everything.
    assert "Verified Lane" in body
    assert f'<td class="rr-complaint-id">{setup}</td>' not in body


def test_dashboard_paginates(app, client, setup):
    for i in range(16):
        _make_complaint(app, "citizen@example.com", location=f"Bulk Street {i}")
    _sign_in(client, app, "admin@example.com")

    page1 = client.get("/admin/").data.decode()
    page2 = client.get("/admin/?page=2").data.decode()
    assert page1.count('class="rr-complaint-id"') == 15
    assert page2.count('class="rr-complaint-id"') == 2
    assert "Page 1 of 2" in page1


def test_complaint_without_coordinates_does_not_break_pages(app, client, setup):
    cid = _make_complaint(app, "citizen@example.com", location="No Pin Road", latitude=None, longitude=None)
    _sign_in(client, app, "admin@example.com")

    assert client.get("/admin/").status_code == 200
    detail = client.get(f"/admin/complaints/{cid}")
    assert detail.status_code == 200
    assert b"No map coordinates were recorded" in detail.data


def test_map_popups_data_is_escaped(app, client, setup):
    _make_complaint(app, "citizen@example.com", location="</script><script>alert(1)</script>")
    _sign_in(client, app, "admin@example.com")

    body = client.get("/admin/").data.decode()
    assert "</script><script>alert(1)" not in body


# --- Status updates -----------------------------------------------------

def _update(client, cid, **data):
    return client.post(f"/admin/complaints/{cid}/status", data=data, follow_redirects=True)


def test_status_update_is_saved_and_logged(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _update(client, setup, status="Under Review", assigned_team="", remarks="Looking into it.")

    c = _get(app, setup)
    assert c.status == "Under Review"
    with app.app_context():
        log = ComplaintUpdate.query.filter_by(complaint_id=c.id).order_by(ComplaintUpdate.id.desc()).first()
        assert (log.previous_status, log.new_status) == ("Submitted", "Under Review")
        assert log.remarks == "Looking into it."
        assert log.created_at is not None
        assert log.updated_by is not None


def test_rejecting_requires_a_reason_and_citizen_sees_it(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _update(client, setup, status="Rejected", assigned_team="", remarks="")
    assert _get(app, setup).status == "Submitted"

    _update(client, setup, status="Rejected", assigned_team="", remarks="Duplicate of another report.")
    assert _get(app, setup).status == "Rejected"

    _sign_in(client, app, "citizen@example.com")
    page = client.get(f"/track?complaint_id={setup}").data
    assert b"Duplicate of another report." in page


def test_repair_statuses_require_a_team(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _update(client, setup, status="Assigned for Repair", assigned_team="", remarks="")
    assert _get(app, setup).status == "Submitted"

    _update(client, setup, status="Assigned for Repair", assigned_team="Ward 12 Roads", remarks="")
    c = _get(app, setup)
    assert (c.status, c.assigned_team) == ("Assigned for Repair", "Ward 12 Roads")


def test_cannot_resolve_before_verification(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _update(client, setup, status="Resolved", assigned_team="", remarks="Done")
    assert _get(app, setup).status == "Submitted"

    _update(client, setup, status="Verified", assigned_team="", remarks="")
    _update(client, setup, status="Resolved", assigned_team="", remarks="Fixed and inspected.")
    assert _get(app, setup).status == "Resolved"


def test_invalid_status_is_rejected(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _update(client, setup, status="Banana", assigned_team="", remarks="")
    assert _get(app, setup).status == "Submitted"


def test_remark_without_status_change_is_logged_as_a_note(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _update(client, setup, status="Submitted", assigned_team="", remarks="Called the reporter.")

    with app.app_context():
        c = Complaint.query.filter_by(complaint_id=setup).first()
        log = ComplaintUpdate.query.filter_by(complaint_id=c.id).order_by(ComplaintUpdate.id.desc()).first()
        assert log.previous_status == log.new_status == "Submitted"
        assert log.remarks == "Called the reporter."


def test_empty_update_is_refused_and_creates_no_log_row(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    with app.app_context():
        before = ComplaintUpdate.query.count()
    _update(client, setup, status="Submitted", assigned_team="", remarks="")
    with app.app_context():
        assert ComplaintUpdate.query.count() == before


def test_team_change_is_written_to_the_log(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _update(client, setup, status="Verified", assigned_team="Night Crew", remarks="")

    with app.app_context():
        c = Complaint.query.filter_by(complaint_id=setup).first()
        log = ComplaintUpdate.query.filter_by(complaint_id=c.id).order_by(ComplaintUpdate.id.desc()).first()
        assert "Night Crew" in log.remarks


# --- AI classification review -------------------------------------------

def _classify(client, cid, label):
    return client.post(f"/admin/complaints/{cid}/classification", data={"classification": label}, follow_redirects=True)


def test_correcting_the_ai_result_clears_confidence_and_is_logged(app, client, setup):
    cid = _make_complaint(app, "citizen@example.com", location="AI Road", ai_prediction="Pothole", ai_confidence=0.87)
    _sign_in(client, app, "admin@example.com")
    _classify(client, cid, "Road Cracks")

    c = _get(app, cid)
    assert (c.ai_prediction, c.ai_confidence) == ("Road Cracks", None)
    assert c.ai_admin_reviewed is True
    with app.app_context():
        log = ComplaintUpdate.query.filter_by(complaint_id=c.id).order_by(ComplaintUpdate.id.desc()).first()
        assert "Pothole" in log.remarks and "87.0%" in log.remarks and "Road Cracks" in log.remarks

    # And the citizen's pages must cope with a prediction that has no confidence
    _sign_in(client, app, "citizen@example.com")
    assert client.get(f"/track?complaint_id={cid}").status_code == 200
    assert client.get(f"/report/confirmation/{cid}").status_code == 200


def test_confirming_the_ai_result_keeps_its_confidence(app, client, setup):
    cid = _make_complaint(app, "citizen@example.com", location="AI Road 2", ai_prediction="Pothole", ai_confidence=0.9)
    _sign_in(client, app, "admin@example.com")
    _classify(client, cid, "Pothole")

    c = _get(app, cid)
    assert (c.ai_prediction, c.ai_confidence) == ("Pothole", 0.9)
    assert c.ai_admin_reviewed is False


def test_admin_can_classify_when_ai_was_unavailable(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _classify(client, setup, "Waterlogging")
    assert _get(app, setup).ai_prediction == "Waterlogging"


def test_invalid_classification_is_rejected(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _classify(client, setup, "Not A Category")
    assert _get(app, setup).ai_prediction is None


# --- Repair photos ------------------------------------------------------

def _upload(client, cid, file, kind="After repair", note=""):
    return client.post(f"/admin/complaints/{cid}/evidence", data={
        "kind": kind, "note": note, "photo": file,
    }, content_type="multipart/form-data", follow_redirects=True)


def test_repair_photo_is_stored_and_visible_to_owner_only(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _upload(client, setup, (_jpeg(), "after.jpg"), kind="After repair", note="Fresh asphalt")

    with app.app_context():
        evidence = RepairEvidence.query.one()
        filename, description = evidence.image_path, evidence.description
        assert os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    assert description == "After repair: Fresh asphalt"

    _sign_in(client, app, "citizen@example.com")
    assert client.get(f"/uploads/{filename}").status_code == 200
    assert b"Fresh asphalt" in client.get(f"/track?complaint_id={setup}").data

    _make_user(app, "stranger@example.com")
    _sign_in(client, app, "stranger@example.com")
    assert client.get(f"/uploads/{filename}").status_code == 403


def test_non_image_repair_upload_is_rejected(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _upload(client, setup, (io.BytesIO(b"definitely not an image"), "fake.jpg"))

    with app.app_context():
        assert RepairEvidence.query.count() == 0
    assert os.listdir(app.config["UPLOAD_FOLDER"]) == []


def test_repair_upload_needs_a_valid_kind(app, client, setup):
    _sign_in(client, app, "admin@example.com")
    _upload(client, setup, (_jpeg(), "x.jpg"), kind="Whatever")
    with app.app_context():
        assert RepairEvidence.query.count() == 0