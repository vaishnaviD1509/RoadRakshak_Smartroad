from datetime import datetime, timedelta

from models import db
from models.complaint import Complaint
from models.user import User


def _make_admin(app, email="admin@example.com"):
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            return
        u = User(name="Admin", email=email, role="admin")
        u.set_password("longenough1")
        db.session.add(u)
        db.session.commit()


def _make_citizen(app, email="citizen@example.com"):
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
            description="Seeded for analytics tests.", location_name="MG Road",
            status="Submitted",
        )
        defaults.update(kwargs)
        c = Complaint(**defaults)
        db.session.add(c)
        db.session.commit()
        return c.complaint_id


def _login_admin(client, app, email="admin@example.com"):
    _make_admin(app, email)
    return client.post("/login", data={"email": email, "password": "longenough1"}, follow_redirects=True)


def test_analytics_page_requires_admin(client):
    resp = client.get("/admin/analytics", follow_redirects=True)
    # Not logged in at all -> redirected to login, never the analytics page.
    assert b"Analytics" not in resp.data


def test_analytics_page_loads_for_admin(app, client):
    _login_admin(client, app)
    resp = client.get("/admin/analytics")
    assert resp.status_code == 200
    assert b"Analytics" in resp.data


def test_analytics_api_rejects_non_admin(app, client):
    _make_citizen(app, "plain@example.com")
    client.post("/login", data={"email": "plain@example.com", "password": "longenough1"}, follow_redirects=True)
    resp = client.get("/admin/api/analytics", follow_redirects=True)
    # admin_required redirects non-admins away rather than serving JSON.
    assert resp.request.path != "/admin/api/analytics" or resp.status_code != 200


def test_analytics_api_counts_by_category(app, client):
    _login_admin(client, app)
    _add_complaint(app, damage_category="Pothole")
    _add_complaint(app, damage_category="Pothole")
    _add_complaint(app, damage_category="Road Cracks")

    data = client.get("/admin/api/analytics").get_json()
    by_category = dict(zip(data["by_category"]["labels"], data["by_category"]["values"]))
    assert by_category["Pothole"] == 2
    assert by_category["Road Cracks"] == 1
    assert data["total"] == 3


def test_analytics_api_counts_by_status(app, client):
    _login_admin(client, app)
    _add_complaint(app, status="Submitted")
    _add_complaint(app, status="Resolved")
    _add_complaint(app, status="Resolved")

    data = client.get("/admin/api/analytics").get_json()
    by_status = dict(zip(data["by_status"]["labels"], data["by_status"]["values"]))
    assert by_status["Resolved"] == 2
    assert by_status["Submitted"] == 1


def test_analytics_api_resolved_vs_unresolved(app, client):
    _login_admin(client, app)
    _add_complaint(app, status="Resolved")
    _add_complaint(app, status="Submitted")
    _add_complaint(app, status="Under Review")

    data = client.get("/admin/api/analytics").get_json()
    assert data["resolved_vs_unresolved"]["resolved"] == 1
    assert data["resolved_vs_unresolved"]["unresolved"] == 2


def test_analytics_api_timeline_includes_todays_submission(app, client):
    _login_admin(client, app)
    _add_complaint(app)

    data = client.get("/admin/api/analytics").get_json()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert today in data["timeline"]["labels"]
    idx = data["timeline"]["labels"].index(today)
    assert data["timeline"]["values"][idx] >= 1
    # 30-day window, oldest first.
    assert len(data["timeline"]["labels"]) == 30


def test_analytics_api_filters_by_category(app, client):
    _login_admin(client, app)
    _add_complaint(app, damage_category="Pothole")
    _add_complaint(app, damage_category="Waterlogging")

    data = client.get("/admin/api/analytics?category=Pothole").get_json()
    assert data["total"] == 1
    assert data["by_category"]["labels"] == ["Pothole"]


def test_analytics_api_filters_by_date_range(app, client):
    _login_admin(client, app)
    with app.app_context():
        user_id = _make_citizen(app)
        old = Complaint(
            user_id=user_id, damage_category="Pothole", description="Old one.",
            location_name="Old Road", status="Submitted",
            created_at=datetime.utcnow() - timedelta(days=40),
        )
        recent = Complaint(
            user_id=user_id, damage_category="Pothole", description="Recent one.",
            location_name="Recent Road", status="Submitted",
            created_at=datetime.utcnow(),
        )
        db.session.add_all([old, recent])
        db.session.commit()

    today = datetime.utcnow().strftime("%Y-%m-%d")
    data = client.get(f"/admin/api/analytics?date_from={today}").get_json()
    assert data["total"] == 1


def test_analytics_api_empty_database_returns_zero_total(app, client):
    _login_admin(client, app)
    data = client.get("/admin/api/analytics").get_json()
    assert data["total"] == 0
    assert data["resolved_vs_unresolved"] == {"resolved": 0, "unresolved": 0}
    assert len(data["timeline"]["labels"]) == 30
    assert all(v == 0 for v in data["timeline"]["values"])


def test_analytics_api_invalid_category_filter_is_ignored(app, client):
    _login_admin(client, app)
    _add_complaint(app, damage_category="Pothole")

    data = client.get("/admin/api/analytics?category=NotARealCategory").get_json()
    assert data["total"] == 1