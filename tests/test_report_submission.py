import io
from PIL import Image
from models import db
from models.user import User
from models.complaint import Complaint


def _make_test_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color=(120, 160, 120)).save(buf, format="JPEG")
    buf.seek(0)
    return buf


def _register_and_login(client, email="reporter@example.com"):
    client.post("/register", data={
        "name": "Reporter", "email": email,
        "password": "longenough1", "confirm_password": "longenough1",
    })
    client.post("/login", data={"email": email, "password": "longenough1"})


def _get_form_token(client):
    resp = client.get("/report")
    # crude extraction: the hidden form_token input's value attribute
    html = resp.data.decode()
    marker = 'name="form_token" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


def test_report_page_requires_login(client):
    resp = client.get("/report", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_successful_complaint_submission(app, client):
    _register_and_login(client)
    token = _get_form_token(client)

    data = {
        "csrf_token": "",
        "form_token": token,
        "damage_category": "Pothole",
        "description": "A large pothole blocking half the lane.",
        "location_name": "MG Road",
        "latitude": "17.3297",
        "longitude": "76.8343",
        "photo": (_make_test_image_bytes(), "test.jpg"),
    }
    # fetch a real csrf token from the session via a fresh GET
    with client.session_transaction() as sess:
        data["csrf_token"] = sess.get("_csrf_token", "")

    resp = client.post("/report", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Complaint submitted" in resp.data

    with app.app_context():
        complaint = Complaint.query.first()
        assert complaint is not None
        assert complaint.damage_category == "Pothole"
        assert complaint.status == "Submitted"
        assert complaint.image_path is not None


def test_duplicate_form_token_is_rejected(client):
    _register_and_login(client, email="dup@example.com")
    token = _get_form_token(client)
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")

    data = {
        "csrf_token": csrf,
        "form_token": token,
        "damage_category": "Pothole",
        "description": "A pothole worth reporting twice by accident.",
        "location_name": "MG Road",
        "latitude": "17.3297",
        "longitude": "76.8343",
        "photo": (_make_test_image_bytes(), "test.jpg"),
    }
    resp1 = client.post("/report", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert resp1.status_code == 200

    # Re-using the same form_token (simulating a double-click / resubmit)
    data["photo"] = (_make_test_image_bytes(), "test2.jpg")
    resp2 = client.post("/report", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert b"already been submitted" in resp2.data


def test_missing_location_is_rejected(client):
    _register_and_login(client, email="nolocation@example.com")
    token = _get_form_token(client)
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")

    data = {
        "csrf_token": csrf,
        "form_token": token,
        "damage_category": "Pothole",
        "description": "Missing a location on purpose for this test.",
        "location_name": "MG Road",
        "latitude": "",
        "longitude": "",
        "photo": (_make_test_image_bytes(), "test.jpg"),
    }
    resp = client.post("/report", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_uploaded_photo_is_not_visible_to_other_users(app, client):
    _register_and_login(client, email="owner@example.com")
    token = _get_form_token(client)
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")

    data = {
        "csrf_token": csrf,
        "form_token": token,
        "damage_category": "Pothole",
        "description": "A private complaint photo for access-control testing.",
        "location_name": "MG Road",
        "latitude": "17.3297",
        "longitude": "76.8343",
        "photo": (_make_test_image_bytes(), "private.jpg"),
    }
    client.post("/report", data=data, content_type="multipart/form-data", follow_redirects=True)

    with app.app_context():
        complaint = Complaint.query.filter_by(location_name="MG Road").order_by(Complaint.id.desc()).first()
        image_filename = complaint.image_path

    client.get("/logout")
    _register_and_login(client, email="intruder@example.com")

    resp = client.get(f"/uploads/{image_filename}")
    assert resp.status_code == 403