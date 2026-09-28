from datetime import datetime, timezone
from models import db


class RepairEvidence(db.Model):
    __tablename__ = "repair_evidence"

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False)

    image_path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<RepairEvidence for complaint_id={self.complaint_id}>"