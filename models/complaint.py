import uuid
from datetime import datetime, timezone
from models import db


def generate_complaint_id() -> str:
    """Generate a short, human-shareable complaint ID, e.g. RR-3F9A21B4."""
    return f"RR-{uuid.uuid4().hex[:8].upper()}"


class Complaint(db.Model):
    __tablename__ = "complaints"

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(
        db.String(20), unique=True, nullable=False, default=generate_complaint_id, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    damage_category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location_name = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)

    ai_prediction = db.Column(db.String(255), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)

    status = db.Column(db.String(30), nullable=False, default="Submitted")
    assigned_team = db.Column(db.String(120), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    updates = db.relationship(
        "ComplaintUpdate", backref="complaint", lazy=True, cascade="all, delete-orphan",
        order_by="ComplaintUpdate.created_at",
    )
    repair_evidence = db.relationship(
        "RepairEvidence", backref="complaint", lazy=True, cascade="all, delete-orphan",
        order_by="RepairEvidence.created_at",
    )

    @property
    def ai_admin_reviewed(self) -> bool:
        """True when an administrator set the classification themselves.

        A genuine model result always has a confidence score; once an admin
        corrects it, the score no longer applies and is cleared, so a
        prediction with no confidence means "set by a human reviewer".
        """
        return self.ai_prediction is not None and self.ai_confidence is None

    def __repr__(self):
        return f"<Complaint {self.complaint_id} [{self.status}]>"