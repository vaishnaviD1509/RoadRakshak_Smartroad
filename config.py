import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Central app configuration, read from environment variables."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    _default_db_path = os.path.join(BASE_DIR, "database", "road_rakshak.db")
    _raw_db_url = os.environ.get("DATABASE_URL", f"sqlite:///{_default_db_path}")

    # A relative "sqlite:///path" is ambiguous (resolved against Flask's
    # instance path, not the process cwd), so normalize it to an absolute
    # path anchored at this project's root.
    if _raw_db_url.startswith("sqlite:///") and not _raw_db_url.startswith("sqlite:////"):
        _relative_part = _raw_db_url[len("sqlite:///"):]
        if not os.path.isabs(_relative_part):
            _raw_db_url = "sqlite:///" + os.path.join(BASE_DIR, _relative_part)

    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.environ.get("UPLOAD_FOLDER", "uploads"))
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 5)) * 1024 * 1024

    # Status values a complaint can move through (used in later stages too)
    COMPLAINT_STATUSES = [
        "Submitted",
        "Under Review",
        "Verified",
        "Assigned for Repair",
        "Repair in Progress",
        "Resolved",
        "Rejected",
    ]

    DAMAGE_CATEGORIES = [
        "Pothole",
        "Road Cracks",
        "Broken Road Surface",
        "Waterlogging",
        "Damaged Shoulder",
        "Open Manhole",
        "Other",
    ]

    # --- AI road damage detection (Stage 4) ---
    # Drop a trained YOLO model file at this path (or point AI_MODEL_PATH at
    # it via .env) to enable AI detection. Without it, the app stays fully
    # functional and simply marks AI analysis as unavailable on every
    # complaint - see services/damage_detection.py and ai_models/README.md.
    AI_MODEL_PATH = os.environ.get(
        "AI_MODEL_PATH", os.path.join(BASE_DIR, "ai_models", "road_damage_model.pt")
    )
    AI_CONFIDENCE_THRESHOLD = float(os.environ.get("AI_CONFIDENCE_THRESHOLD", 0.35))