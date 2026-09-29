from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request

from models.complaint import Complaint

map_bp = Blueprint("map", __name__)

# Fields shown on the public map are deliberately limited: no reporter
# identity, description, or photo - those stay behind login on the
# tracking page. Only what's needed to plot and label a marker.


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


@map_bp.route("/map")
def view():
    return render_template(
        "map.html",
        categories=current_app.config["DAMAGE_CATEGORIES"],
        statuses=current_app.config["COMPLAINT_STATUSES"],
    )


@map_bp.route("/map/api/points")
def points():
    """JSON marker data for the map, filtered by the query string.
    Complaints with no coordinates are left out rather than guessed at."""
    query = Complaint.query.filter(
        Complaint.latitude.isnot(None), Complaint.longitude.isnot(None)
    )

    complaint_id = request.args.get("complaint_id", "").strip().upper()
    if complaint_id:
        query = query.filter(Complaint.complaint_id.like(f"%{complaint_id}%"))

    category = request.args.get("category", "")
    if category in current_app.config["DAMAGE_CATEGORIES"]:
        query = query.filter_by(damage_category=category)

    status = request.args.get("status", "")
    if status in current_app.config["COMPLAINT_STATUSES"]:
        query = query.filter_by(status=status)

    date_from = _parse_date(request.args.get("date_from"))
    if date_from:
        query = query.filter(Complaint.created_at >= date_from)

    date_to = _parse_date(request.args.get("date_to"))
    if date_to:
        query = query.filter(Complaint.created_at < date_to.replace(hour=23, minute=59, second=59))

    complaints = query.order_by(Complaint.created_at.desc()).limit(1000).all()

    return jsonify([
        {
            "id": c.complaint_id,
            "category": c.damage_category,
            "status": c.status,
            "date": c.created_at.strftime("%d %b %Y"),
            "lat": c.latitude,
            "lng": c.longitude,
        }
        for c in complaints
    ])