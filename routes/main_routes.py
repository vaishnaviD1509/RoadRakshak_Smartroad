from flask import Blueprint, render_template, current_app
from models import db
from models.complaint import Complaint

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Landing page. Stats are pulled from the real database -
    they show 0 rather than fabricated numbers when it's empty."""
    total = Complaint.query.count()
    awaiting_review = Complaint.query.filter(
        Complaint.status.in_(["Submitted", "Under Review"])
    ).count()
    under_repair = Complaint.query.filter(
        Complaint.status.in_(["Assigned for Repair", "Repair in Progress"])
    ).count()
    resolved = Complaint.query.filter_by(status="Resolved").count()

    recent_complaints = (
        Complaint.query.order_by(Complaint.created_at.desc()).limit(3).all()
    )

    stats = {
        "total": total,
        "awaiting_review": awaiting_review,
        "under_repair": under_repair,
        "resolved": resolved,
    }

    return render_template(
        "index.html",
        stats=stats,
        recent_complaints=recent_complaints,
        damage_categories=current_app.config["DAMAGE_CATEGORIES"],
    )