"""Citizens deleting their own complaints."""
import os

from models import db
from models.complaint import Complaint
from models.complaint_update import ComplaintUpdate
from models.user import User


def _make_user(app, email, role="citizen"):
    with app.app_context():
        u = User(name="Citizen", email=email, role=role)
        u.set_password("longenough1")
        db.session.add(u)
        db.session.commit()


def _sign_in(client, app, email):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        ident = (u.id, u.name, u.role)
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = ident


def _add_complaint(app, owner_email, status="Submitted", image_path=None):
    with app.app_context():
        owner = User.query.filter_by(email=owner_email).first()
        c = Complaint(
            user_id=owner.id, damage_category="Pothole", description="Seeded for delete tests.",
            location_name="MG Road", status=status, image_path=image_path,
        )
        db.session.add(c)
        db.session.flush()
        db.session.add(ComplaintUpdate(complaint_id=c.id, new_status=status, remarks="first"))
        db.session.commit()
        return c.complaint_id


def _exists(app, complaint_id):
    with app.app_context():
        return Complaint.query.filter_by(complaint_id=complaint_id).first() is not None


def test_owner_can_delete_a_submitted_complaint(app, client):
    _make_user(app, "me@example.com")
    cid = _add_complaint(app, "me@example.com")
    _sign_in(client, app, "me@example.com")

    resp = client.post(f"/report/{cid}/delete")
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers["Location"]
    assert not _exists(app, cid)
    with app.app_context():
        assert ComplaintUpdate.query.count() == 0  # history removed too


def test_owner_can_delete_a_rejected_complaint(app, client):
    _make_user(app, "me@example.com")
    cid = _add_complaint(app, "me@example.com", status="Rejected")
    _sign_in(client, app, "me@example.com")
    client.post(f"/report/{cid}/delete")
    assert not _exists(app, cid)


def test_cannot_delete_once_staff_are_working_on_it(app, client):
    _make_user(app, "me@example.com")
    _sign_in(client, app, "me@example.com")
    for status in ["Under Review", "Verified", "Assigned for Repair", "Repair in Progress", "Resolved"]:
        cid = _add_complaint(app, "me@example.com", status=status)
        resp = client.post(f"/report/{cid}/delete")
        assert resp.status_code == 302
        assert "/track" in resp.headers["Location"]
        assert _exists(app, cid), status


def test_cannot_delete_someone_elses_complaint(app, client):
    _make_user(app, "owner@example.com")
    _make_user(app, "other@example.com")
    cid = _add_complaint(app, "owner@example.com")
    _sign_in(client, app, "other@example.com")
    assert client.post(f"/report/{cid}/delete").status_code == 404
    assert _exists(app, cid)


def test_unknown_complaint_is_404(app, client):
    _make_user(app, "me@example.com")
    _sign_in(client, app, "me@example.com")
    assert client.post("/report/RR-NOPE0000/delete").status_code == 404


def test_delete_requires_login_and_post(app, client):
    _make_user(app, "me@example.com")
    cid = _add_complaint(app, "me@example.com")
    resp = client.post(f"/report/{cid}/delete")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
    _sign_in(client, app, "me@example.com")
    assert client.get(f"/report/{cid}/delete").status_code == 405
    assert _exists(app, cid)


def test_delete_also_removes_the_photo_file(app, client, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    photo = tmp_path / "abc123.jpg"
    photo.write_bytes(b"x")
    _make_user(app, "me@example.com")
    cid = _add_complaint(app, "me@example.com", image_path="abc123.jpg")
    _sign_in(client, app, "me@example.com")
    client.post(f"/report/{cid}/delete")
    assert not photo.exists()
    assert not os.listdir(tmp_path)


def test_delete_button_only_shows_while_deletable(app, client):
    _make_user(app, "me@example.com")
    open_id = _add_complaint(app, "me@example.com", status="Submitted")
    busy_id = _add_complaint(app, "me@example.com", status="Repair in Progress")
    _sign_in(client, app, "me@example.com")

    html = client.get("/dashboard").data.decode()
    assert f"/report/{open_id}/delete" in html
    assert f"/report/{busy_id}/delete" not in html

    assert f"/report/{open_id}/delete" in client.get(f"/track?complaint_id={open_id}").data.decode()
    assert f"/report/{busy_id}/delete" not in client.get(f"/track?complaint_id={busy_id}").data.decode()


def test_delete_needs_csrf_token_outside_tests(app, client):
    _make_user(app, "me@example.com")
    cid = _add_complaint(app, "me@example.com")
    _sign_in(client, app, "me@example.com")
    app.config["TESTING"] = False
    try:
        assert client.post(f"/report/{cid}/delete").status_code == 400
        assert _exists(app, cid)
    finally:
        app.config["TESTING"] = True