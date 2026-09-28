from flask import Blueprint, render_template, request, session
from routes.decorators import login_required
from models.complaint import Complaint

tracking_bp = Blueprint("tracking", __name__)

# The normal forward progression of a complaint. "Rejected" is a separate
# terminal outcome, shown differently rather than as a step in this line.
STATUS_ORDER = [
    "Submitted",
    "Under Review",
    "Verified",
    "Assigned for Repair",
    "Repair in Progress",
    "Resolved",
]


@tracking_bp.route("/track", methods=["GET"])
@login_required
def track():
    """Search-and-view complaint tracking page.

    Requires login even to search, and deliberately returns the exact
    same "no permission" message whether a complaint ID doesn't exist at
    all or it exists but belongs to someone else - so a visitor guessing
    at IDs can't use the response to tell which complaint IDs are real.
    """
    searched_id = (request.args.get("complaint_id") or "").strip().upper()
    complaint = None
    updates = []
    rejection_remarks = None
    error = None

    if searched_id:
        found = Complaint.query.filter_by(complaint_id=searched_id).first()
        is_owner_or_admin = found is not None and (
            found.user_id == session["user_id"] or session.get("role") == "admin"
        )

        if not is_owner_or_admin:
            error = "No matching complaint was found, or you don't have permission to view it."
        else:
            complaint = found
            updates = complaint.updates
            if complaint.status == "Rejected":
                rejected_update = next(
                    (u for u in reversed(updates) if u.new_status == "Rejected"), None
                )
                rejection_remarks = rejected_update.remarks if rejected_update else None

    return render_template(
        "track.html",
        complaint=complaint,
        updates=updates,
        status_order=STATUS_ORDER,
        rejection_remarks=rejection_remarks,
        error=error,
        searched_id=searched_id,
    )