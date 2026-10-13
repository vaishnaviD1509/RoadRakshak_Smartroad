from datetime import datetime, timezone
from models import db


class Team(db.Model):
    """A municipal repair team that complaints can be assigned to.

    Teams are never deleted, only switched off, so older complaints keep a
    meaningful team name in their history.
    """
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Team {self.name} ({'active' if self.is_active else 'off'})>"