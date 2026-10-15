import uuid
from datetime import datetime, timezone
from models import db


# How urgent a complaint is, set by municipal staff (never by the citizen).
PRIORITIES = ["Low", "Normal", "High", "Urgent"]

# A citizen may delete their own complaint only while nobody has started acting
# on it. Once it is under review or being repaired, staff depend on the record.
CITIZEN_DELETABLE_STATUSES = {"Submitted", "Rejected"}


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
    priority = db.Column(db.String(10), nullable=False, default="Normal", server_default="Normal")

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
    def citizen_can_delete(self) -> bool:
        return self.status in CITIZEN_DELETABLE_STATUSES

    @property
    def ai_admin_reviewed(self) -> bool:
        """True when an administrator set the classification themselves.

        A genuine model result always has a confidence score; once an admin
        corrects it, the score no longer applies and is cleared, so a
        prediction with no confidence means "set by a human reviewer".
        """
        return self.ai_prediction is not None and self.ai_confidence is None

    @property
    def severity_assessment(self) -> dict:
        """Rule-based severity estimate (level, suggested priority, reasons).

        Worked out on the fly from stored data, so it needs no database column.
        The import is inside the method to avoid any circular-import problem.
        """
        from services.severity import assess_severity

        return assess_severity(
            damage_category=self.damage_category,
            description=self.description,
            ai_prediction=self.ai_prediction,
            ai_confidence=self.ai_confidence,
        )

    @property
    def severity(self) -> str:
        """Low, Medium or High."""
        return self.severity_assessment["level"]

    @property
    def suggested_priority(self) -> str:
        """The priority the severity estimate suggests (staff decide the real one)."""
        return self.severity_assessment["suggested_priority"]

    def __repr__(self):
        return f"<Complaint {self.complaint_id} [{self.status}]>"