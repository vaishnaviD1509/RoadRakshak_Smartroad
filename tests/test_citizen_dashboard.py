from models import db
from models.complaint import Complaint
from models.user import User


def _register_and_login(client, email):
    client.get("/register")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/register", data={
        "name": "Dash User", "email": email,
        "password": "longenough1", "confirm_password": "longenough1",
        "csrf_token": csrf,
    })
    client.get("/login")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/login", data={"email": email, "password": "longenough1", "csrf_token": csrf})


def _add_complaint(app, email, location, status="Submitted"):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        db.session.add(Complaint(
            user_id=user.id, damage_category="Pothole",
            description="Seeded directly for dashboard tests.",
            location_name=location, status=status,
        ))
        db.session.commit()


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_dashboard_empty_state_for_new_user(client):
    _register_and_login(client, "empty@example.com")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"haven&#39;t reported any road damage yet" in resp.data or b"haven't reported any road damage yet" in resp.data


def test_dashboard_lists_only_own_complaints(app, client):
    _register_and_login(client, "mine@example.com")
    client.get("/logout")
    _register_and_login(client, "other@example.com")
    client.get("/logout")

    _add_complaint(app, "mine@example.com", "My Own Street")
    _add_complaint(app, "other@example.com", "Someone Elses Street")

    client.post("/login", data={"email": "mine@example.com", "password": "longenough1"})
    resp = client.get("/dashboard")
    assert b"My Own Street" in resp.data
    assert b"Someone Elses Street" not in resp.data


def test_dashboard_summary_counts_match_statuses(app, client):
    _register_and_login(client, "counts@example.com")
    for i, status in enumerate([
        "Submitted", "Under Review", "Assigned for Repair",
        "Repair in Progress", "Resolved", "Rejected",
    ]):
        _add_complaint(app, "counts@example.com", f"Road {i}", status=status)

    resp = client.get("/dashboard")
    html = resp.data.decode()

    def number_before(label):
        idx = html.index(label)
        chunk = html[:idx]
        start = chunk.rindex('rr-stat-number">') + len('rr-stat-number">')
        return int(chunk[start:chunk.index("<", start)])

    assert number_before("Total complaints") == 6
    assert number_before("Under review") == 2
    assert number_before("Being repaired") == 2
    assert number_before("Resolved") == 1


def test_dashboard_view_details_links_to_tracking_page(app, client):
    _register_and_login(client, "links@example.com")
    _add_complaint(app, "links@example.com", "Link Street")
    with app.app_context():
        cid = Complaint.query.filter_by(location_name="Link Street").first().complaint_id

    resp = client.get("/dashboard")
    assert f"/track?complaint_id={cid}".encode() in resp.data