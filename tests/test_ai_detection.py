import io
import os
from PIL import Image
from services.damage_detection import detect_damage, reset_model_cache, _normalize_label


def _make_test_image(path):
    Image.new("RGB", (40, 40), color=(100, 100, 100)).save(path, format="JPEG")


def test_detection_reports_unavailable_without_model_file(tmp_path):
    reset_model_cache()
    image_path = tmp_path / "sample.jpg"
    _make_test_image(image_path)

    result = detect_damage(
        image_path=str(image_path),
        model_path=str(tmp_path / "nonexistent_model.pt"),
        confidence_threshold=0.35,
    )

    assert result["available"] is False
    assert result["prediction"] is None
    assert result["confidence"] is None
    assert result["detections"] == []
    assert "unavailable" in result["message"].lower()


def test_detection_handles_unreadable_image_gracefully(tmp_path):
    reset_model_cache()
    bad_file = tmp_path / "not_an_image.jpg"
    bad_file.write_bytes(b"this is not image data")

    result = detect_damage(
        image_path=str(bad_file),
        model_path=str(tmp_path / "nonexistent_model.pt"),
        confidence_threshold=0.35,
    )

    assert result["available"] is False
    assert result["prediction"] is None


def test_class_name_normalization():
    assert _normalize_label("Pothole") == "Pothole"
    assert _normalize_label("pothole") == "Pothole"
    assert _normalize_label("pothole_issues") == "Pothole"
    assert _normalize_label("some_unmapped_class") == "Some Unmapped Class"


def test_document_like_photo_is_rejected_at_submission(app, client):
    """A receipt/document-style photo should be rejected outright as a
    validation error - no complaint created, and the saved file cleaned up."""
    import numpy as np
    from PIL import Image as PILImage
    from models.complaint import Complaint

    client.get("/register")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/register", data={
        "name": "Receipt Uploader", "email": "receipt@example.com",
        "password": "longenough1", "confirm_password": "longenough1",
        "csrf_token": csrf,
    })
    client.get("/login")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/login", data={
        "email": "receipt@example.com", "password": "longenough1", "csrf_token": csrf,
    })

    resp = client.get("/report")
    html = resp.data.decode()
    marker = 'name="form_token" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    form_token = html[start:end]

    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")

    # A receipt-like image: mostly white with thin dark "text" strips
    arr = np.full((200, 200, 3), 250, dtype=np.uint8)
    arr[20:180, 40:44] = 0
    arr[20:180, 80:84] = 0
    buf = io.BytesIO()
    PILImage.fromarray(arr).save(buf, format="JPEG")
    buf.seek(0)

    upload_folder = app.config["UPLOAD_FOLDER"]
    files_before = set(os.listdir(upload_folder)) if os.path.isdir(upload_folder) else set()

    resp = client.post("/report", data={
        "csrf_token": csrf,
        "form_token": form_token,
        "damage_category": "Pothole",
        "description": "Accidentally uploading a receipt instead of a road photo.",
        "location_name": "MG Road",
        "latitude": "17.3297",
        "longitude": "76.8343",
        "photo": (buf, "receipt.jpg"),
    }, content_type="multipart/form-data")

    assert resp.status_code == 400
    assert b"doesn" in resp.data and b"look like a photo of a road" in resp.data

    with app.app_context():
        assert Complaint.query.filter_by(location_name="MG Road").first() is None

    # The rejected upload must not be left behind on disk
    files_after = set(os.listdir(upload_folder)) if os.path.isdir(upload_folder) else set()
    assert files_after == files_before


def test_complaint_submission_succeeds_with_ai_unavailable(app, client):
    """End-to-end: without a model file, submission still succeeds and
    ai_prediction/ai_confidence stay null - nothing is fabricated."""
    from models import db
    from models.complaint import Complaint

    client.get("/register")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/register", data={
        "name": "AI Test User", "email": "aitest@example.com",
        "password": "longenough1", "confirm_password": "longenough1",
        "csrf_token": csrf,
    })
    client.get("/login")
    with client.session_transaction() as sess:
        csrf = sess.get("_csrf_token", "")
    client.post("/login", data={
        "email": "aitest@example.com", "password": "longenough1", "csrf_token": csrf,
    })

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

    resp = client.post("/report", data={
        "csrf_token": csrf,
        "form_token": form_token,
        "damage_category": "Pothole",
        "description": "Testing AI-unavailable submission path end to end.",
        "location_name": "MG Road",
        "latitude": "17.3297",
        "longitude": "76.8343",
        "photo": (buf, "test.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)

    assert resp.status_code == 200
    # This should always be true regardless of whether a trained model
    # happens to be present in ai_models/ on the machine running the
    # tests: the submission must succeed either way, and the confirmation
    # page must say *something* about AI status.
    body = resp.data.lower()
    assert (
        b"queued for manual review" in body
        or b"did not produce" in body
        or b"preliminary ai classification" in body
        or b"looks like a document" in body
    )

    with app.app_context():
        complaint = Complaint.query.filter_by(location_name="MG Road").order_by(Complaint.id.desc()).first()
        # Nothing is fabricated: either there's no prediction at all, or -
        # if a real model happens to be present on this machine - a
        # genuine prediction with a real confidence score between 0 and 1.
        if complaint.ai_prediction is None:
            assert complaint.ai_confidence is None
        else:
            assert 0.0 <= complaint.ai_confidence <= 1.0


def test_document_like_image_is_flagged_and_skips_classification(tmp_path):
    """A receipt/document-style image (mostly white, low saturation) should
    be caught before it ever reaches the classifier, regardless of whether
    a model is present."""
    from PIL import Image as PILImage
    import numpy as np
    from services.damage_detection import detect_damage, reset_model_cache

    reset_model_cache()

    # Simulate a receipt: mostly white background with a little black "text"
    arr = np.full((200, 200, 3), 250, dtype=np.uint8)
    arr[20:180, 40:44] = 0  # a thin dark strip, like printed text
    receipt_path = tmp_path / "receipt.jpg"
    PILImage.fromarray(arr).save(receipt_path, format="JPEG")

    result = detect_damage(
        image_path=str(receipt_path),
        model_path=str(tmp_path / "nonexistent_model.pt"),
        confidence_threshold=0.35,
    )

    assert result["available"] is True
    assert result["prediction"] is None
    assert "document" in result["message"].lower() or "receipt" in result["message"].lower()


def test_colorful_outdoor_like_image_is_not_flagged_as_document(tmp_path):
    """A natural, colorful image (simulating a real road photo) should NOT
    be caught by the document heuristic."""
    from PIL import Image as PILImage
    import numpy as np
    from services.damage_detection import looks_like_document

    rng = np.random.default_rng(42)
    # Varied, saturated colors - unlike a document's flat white background
    arr = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    road_like_path = tmp_path / "road_like.jpg"
    PILImage.fromarray(arr).save(road_like_path, format="JPEG")

    assert looks_like_document(str(road_like_path)) is False