"""The 'AI detection' panel on the admin dashboard."""
import re

from models import db
from models.complaint import Complaint
from models.user import User


def _make_user(app, email, role):
    with app.app_context():
        u = User(name=role.title(), email=email, role=role)
        u.set_password("longenough1")
        db.session.add(u)
        db.session.commit()


def _sign_in(client, app, email):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        ident = (u.id, u.name, u.role)
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = ident


def _add_complaint(app, owner_email, **fields):
    with app.app_context():
        owner = User.query.filter_by(email=owner_email).first()
        db.session.add(Complaint(
            user_id=owner.id, damage_category="Pothole",
            description="Seeded for the AI panel tests.", location_name="MG Road", **fields,
        ))
        db.session.commit()


def _count(html, element_id):
    return int(re.search(rf'id="{element_id}">(\d+)<', html).group(1))


def _admin_page(app, client):
    _make_user(app, "admin@example.com", "admin")
    _sign_in(client, app, "admin@example.com")
    return client.get("/admin/").data.decode()


def test_panel_says_not_active_when_ai_is_unavailable(app, client, monkeypatch, tmp_path):
    app.config["AI_MODEL_PATH"] = str(tmp_path / "no_model_here.pt")
    monkeypatch.setattr("routes.admin_routes.ai_available", lambda path: False)
    html = _admin_page(app, client)
    assert "AI detection" in html
    assert ">Not active<" in html
    assert "No trained model was found" in html


def test_panel_says_active_when_ai_is_available(app, client, monkeypatch):
    monkeypatch.setattr("routes.admin_routes.ai_available", lambda path: True)
    html = _admin_page(app, client)
    assert 'id="aiState">Active<' in html
    assert "A trained model is loaded" in html


def test_panel_explains_missing_library_when_model_file_exists(app, client, monkeypatch, tmp_path):
    model = tmp_path / "road_damage_model.pt"
    model.write_bytes(b"x")
    app.config["AI_MODEL_PATH"] = str(model)
    monkeypatch.setattr("routes.admin_routes.ai_available", lambda path: False)
    html = _admin_page(app, client)
    assert "ultralytics library is not installed" in html
    assert "road_damage_model.pt" in html


def test_panel_counts_how_complaints_were_classified(app, client):
    _make_user(app, "citizen@example.com", "citizen")
    _add_complaint(app, "citizen@example.com", ai_prediction="Pothole", ai_confidence=0.9)
    _add_complaint(app, "citizen@example.com", ai_prediction="Pothole", ai_confidence=0.6)
    _add_complaint(app, "citizen@example.com", ai_prediction="Road Cracks", ai_confidence=None)
    _add_complaint(app, "citizen@example.com")
    _add_complaint(app, "citizen@example.com")
    _add_complaint(app, "citizen@example.com")

    html = _admin_page(app, client)
    assert _count(html, "aiCountClassified") == 2
    assert _count(html, "aiCountAdmin") == 1
    assert _count(html, "aiCountNone") == 3


def test_panel_shows_confidence_threshold(app, client):
    html = _admin_page(app, client)
    assert "Minimum confidence" in html
    assert "35%" in html


def test_citizens_still_cannot_see_the_admin_dashboard(app, client):
    _make_user(app, "citizen@example.com", "citizen")
    _sign_in(client, app, "citizen@example.com")
    resp = client.get("/admin/")
    assert resp.status_code == 302