import io
from PIL import Image
from models import db
from models.user import User
from models.complaint import Complaint
from models.complaint_update import ComplaintUpdate


def _register_and_login(client, email):
    client.get("/register")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/register", data={
        "name": "Test User", "email": email,
        "password": "longenough1", "confirm_password": "longenough1",
        "csrf_token": csrf,
    })
    client.get("/login")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/login", data={"email": email, "password": "longenough1", "csrf_token": csrf})


def _submit_complaint(client, location_name="MG Road"):
    resp = client.get("/report")
    html = resp.data.decode()
    marker = 'name="form_token" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    form_token = html[start:end]

    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color=(120, 160, 120)).save(buf, format="JPEG")
    buf.seek(0)

    client.post("/report", data={
        "csrf_token": csrf,
        "form_token": form_token,
        "damage_category": "Pothole",
        "description": "A pothole for tracking-page tests.",
        "location_name": location_name,
        "latitude": "17.3297",
        "longitude": "76.8343",
        "photo": (buf, "test.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)


def test_track_page_requires_login(client):
    resp = client.get("/track", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_searching_nonexistent_complaint_shows_generic_message(client):
    _register_and_login(client, "searcher@example.com")
    resp = client.get("/track?complaint_id=RR-DOESNOTEXIST")
    assert resp.status_code == 200
    assert b"don&#39;t have permission" in resp.data or b"don't have permission" in resp.data


def test_owner_can_view_their_own_complaint(app, client):
    _register_and_login(client, "owner@example.com")
    _submit_complaint(client, location_name="Owner Test Road")

    with app.app_context():
        complaint = Complaint.query.filter_by(location_name="Owner Test Road").first()
        complaint_id = complaint.complaint_id

    resp = client.get(f"/track?complaint_id={complaint_id}")
    assert resp.status_code == 200
    assert complaint_id.encode() in resp.data
    assert b"Owner Test Road" in resp.data
    assert b"Status timeline" in resp.data


def test_other_user_cannot_view_someone_elses_complaint(app, client):
    _register_and_login(client, "owner2@example.com")
    _submit_complaint(client, location_name="Private Road")

    with app.app_context():
        complaint = Complaint.query.filter_by(location_name="Private Road").first()
        complaint_id = complaint.complaint_id

    client.get("/logout")
    _register_and_login(client, "intruder@example.com")

    resp = client.get(f"/track?complaint_id={complaint_id}")
    assert resp.status_code == 200
    # The searched ID is legitimately echoed back in the search box value
    # (the intruder typed it themselves) - what matters is that none of
    # the complaint's actual private details are revealed.
    assert b"Private Road" not in resp.data
    assert b"Status timeline" not in resp.data


def test_admin_can_view_any_complaint(app, client):
    _register_and_login(client, "regular_owner@example.com")
    _submit_complaint(client, location_name="Admin Viewable Road")

    with app.app_context():
        complaint = Complaint.query.filter_by(location_name="Admin Viewable Road").first()
        complaint_id = complaint.complaint_id

    client.get("/logout")
    _register_and_login(client, "admin_user@example.com")
    with app.app_context():
        admin = User.query.filter_by(email="admin_user@example.com").first()
        admin.role = "admin"
        db.session.commit()
    # role is cached in the session from login, so log back in to refresh it
    client.get("/logout")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.get("/municipal/login")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/municipal/login", data={"email": "admin_user@example.com", "password": "longenough1", "csrf_token": csrf})

    resp = client.get(f"/track?complaint_id={complaint_id}")
    assert resp.status_code == 200
    assert b"Admin Viewable Road" in resp.data


def test_rejected_complaint_shows_rejection_reason(app, client):
    _register_and_login(client, "rejected_owner@example.com")
    _submit_complaint(client, location_name="Rejected Road")

    with app.app_context():
        complaint = Complaint.query.filter_by(location_name="Rejected Road").first()
        complaint.status = "Rejected"
        update = ComplaintUpdate(
            complaint_id=complaint.id,
            previous_status="Submitted",
            new_status="Rejected",
            remarks="Duplicate of an existing complaint.",
            updated_by=None,
        )
        db.session.add(update)
        db.session.commit()
        complaint_id = complaint.complaint_id

    resp = client.get(f"/track?complaint_id={complaint_id}")
    assert resp.status_code == 200
    assert b"rejected" in resp.data.lower()
    assert b"Duplicate of an existing complaint." in resp.data