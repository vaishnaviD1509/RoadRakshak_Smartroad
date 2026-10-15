from flask import url_for

from models import db
from models.complaint import Complaint
from models.user import User
from services.severity import assess_severity


def test_plain_pothole_is_medium_with_normal_priority():
    result = assess_severity("Pothole", "There is a pothole near the market gate.")
    assert result["level"] == "Medium"
    assert result["suggested_priority"] == "Normal"


def test_deep_pothole_is_high_priority():
    result = assess_severity("Pothole", "The hole is very deep.")
    assert result["level"] == "High"
    assert result["suggested_priority"] == "High"


def test_accident_word_makes_it_urgent():
    result = assess_severity("Pothole", "A bike rider had an accident here.")
    assert result["level"] == "High"
    assert result["suggested_priority"] == "Urgent"


def test_open_manhole_is_urgent_even_without_warning_words():
    result = assess_severity("Open Manhole", "Cover is missing.")
    assert result["level"] == "High"
    assert result["suggested_priority"] == "Urgent"


def test_small_cracks_are_low():
    result = assess_severity("Road Cracks", "Small cracks on the road.")
    assert result["level"] == "Low"
    assert result["suggested_priority"] == "Low"


def test_moderate_word_lifts_cracks_to_medium():
    result = assess_severity("Road Cracks", "Large cracks across the lane.")
    assert result["level"] == "Medium"
    assert result["suggested_priority"] == "Normal"


def test_low_confidence_ai_result_falls_back_to_citizen_category():
    result = assess_severity("Open Manhole", "Cover is missing.", "Other", 0.40)
    assert result["category"] == "Open Manhole"
    assert result["level"] == "High"
    assert any("AI" in reason for reason in result["reasons"])


def test_confident_ai_result_is_used_for_the_category():
    result = assess_severity("Other", "Something is wrong here.", "Pothole", 0.90)
    assert result["category"] == "Pothole"
    assert result["level"] == "Medium"
    assert any("AI result" in reason for reason in result["reasons"])


def test_admin_set_label_is_trusted():
    # An administrator's correction is stored with no confidence score.
    result = assess_severity("Other", "Something is wrong here.", "Open Manhole", None)
    assert result["category"] == "Open Manhole"
    assert result["level"] == "High"
    assert any("administrator" in reason for reason in result["reasons"])


def test_empty_or_missing_description_does_not_crash():
    assert assess_severity("Pothole", None)["level"] == "Medium"
    assert assess_severity("Pothole", "")["level"] == "Medium"


def test_description_words_are_capped():
    text = "Deep, dangerous, near a school and hospital after an accident."
    result = assess_severity("Road Cracks", text)
    # 1 point for the category + at most 3 points for the description.
    assert result["score"] == 4
    assert result["level"] == "High"


def test_complaint_model_exposes_severity_properties():
    complaint = Complaint(
        damage_category="Pothole",
        description="Very deep hole",
        location_name="MG Road",
    )
    assert complaint.severity == "High"
    assert complaint.suggested_priority == "High"
    assert complaint.severity_assessment["level"] == "High"


def test_staff_complaint_page_shows_severity_estimate(app, client):
    with app.app_context():
        admin = User(name="Admin Person", email="admin@example.com", role="admin")
        admin.set_password("longenough1")
        citizen = User(name="Citizen Person", email="citizen@example.com", role="citizen")
        citizen.set_password("longenough1")
        db.session.add_all([admin, citizen])
        db.session.commit()

        complaint = Complaint(
            user_id=citizen.id,
            damage_category="Pothole",
            description="The hole is very deep.",
            location_name="MG Road",
            status="Submitted",
            latitude=17.33,
            longitude=76.83,
        )
        db.session.add(complaint)
        db.session.commit()
        complaint_id = complaint.complaint_id
        admin_identity = (admin.id, admin.name, admin.role)

    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = admin_identity

    with app.test_request_context():
        url = url_for("admin.complaint_detail", complaint_id=complaint_id)

    response = client.get(url)

    assert response.status_code == 200
    assert b"Severity estimate" in response.data
    assert b"High severity" in response.data
    assert b"Suggested priority" in response.data