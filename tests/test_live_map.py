from datetime import datetime, timedelta

from models import db
from models.complaint import Complaint
from models.user import User


def _make_user(app, email="reporter@example.com"):
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            return existing.id
        u = User(name="Reporter", email=email, role="citizen")
        u.set_password("longenough1")
        db.session.add(u)
        db.session.commit()
        return u.id


def _add_complaint(app, **kwargs):
    with app.app_context():
        user_id = _make_user(app)
        defaults = dict(
            user_id=user_id, damage_category="Pothole",
            description="Seeded for map tests.", location_name="MG Road",
            status="Submitted", latitude=17.33, longitude=76.83,
        )
        defaults.update(kwargs)
        c = Complaint(**defaults)
        db.session.add(c)
        db.session.commit()
        return c.complaint_id


def test_map_page_loads_without_login(client):
    resp = client.get("/map")
    assert resp.status_code == 200
    assert b"Live road damage map" in resp.data


def test_points_api_excludes_complaints_without_coordinates(app, client):
    with_coords = _add_complaint(app, location_name="Has Coords")
    _add_complaint(app, location_name="No Coords", latitude=None, longitude=None)

    data = client.get("/map/api/points").get_json()
    ids = {p["id"] for p in data}
    assert with_coords in ids
    assert len(data) == 1


def test_points_api_excludes_private_fields(app, client):
    _add_complaint(app, description="This description must never appear on the public map.")
    data = client.get("/map/api/points").get_json()

    body_text = str(data)
    assert "must never appear" not in body_text
    assert set(data[0].keys()) == {"id", "category", "status", "date", "lat", "lng"}


def test_points_api_filters_by_category_and_status(app, client):
    pothole_id = _add_complaint(app, damage_category="Pothole", status="Submitted")
    crack_id = _add_complaint(app, damage_category="Road Cracks", status="Resolved")

    only_potholes = client.get("/map/api/points?category=Pothole").get_json()
    assert {p["id"] for p in only_potholes} == {pothole_id}

    only_resolved = client.get("/map/api/points?status=Resolved").get_json()
    assert {p["id"] for p in only_resolved} == {crack_id}


def test_points_api_filters_by_date_range(app, client):
    with app.app_context():
        user_id = _make_user(app)
        old = Complaint(
            user_id=user_id, damage_category="Pothole", description="Old one.",
            location_name="Old Road", status="Submitted", latitude=1, longitude=1,
            created_at=datetime.utcnow() - timedelta(days=30),
        )
        recent = Complaint(
            user_id=user_id, damage_category="Pothole", description="Recent one.",
            location_name="Recent Road", status="Submitted", latitude=2, longitude=2,
            created_at=datetime.utcnow(),
        )
        db.session.add_all([old, recent])
        db.session.commit()
        old_id, recent_id = old.complaint_id, recent.complaint_id

    today = datetime.utcnow().strftime("%Y-%m-%d")
    data = client.get(f"/map/api/points?date_from={today}").get_json()
    ids = {p["id"] for p in data}
    assert recent_id in ids
    assert old_id not in ids


def test_points_api_filters_by_complaint_id(app, client):
    target_id = _add_complaint(app, location_name="Findable Road")
    _add_complaint(app, location_name="Other Road")

    data = client.get(f"/map/api/points?complaint_id={target_id}").get_json()
    assert {p["id"] for p in data} == {target_id}


def test_points_api_complaint_id_search_is_case_insensitive_and_partial(app, client):
    target_id = _add_complaint(app, location_name="Case Test Road")
    partial = target_id[3:8]  # a middle chunk, skipping the "RR-" prefix

    data = client.get(f"/map/api/points?complaint_id={partial.lower()}").get_json()
    assert target_id in {p["id"] for p in data}


def test_invalid_filter_values_are_ignored_not_errored(app, client):
    _add_complaint(app)
    resp = client.get("/map/api/points?category=NotARealCategory&status=NotARealStatus")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1