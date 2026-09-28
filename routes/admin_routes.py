from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, current_app,
)
from sqlalchemy import func

from models import db
from models.complaint import Complaint
from models.user import User
from routes.decorators import admin_required
from services.complaint_service import (
    EVIDENCE_KINDS, TEAM_REQUIRED_STATUSES, UpdateError,
    add_repair_evidence, apply_status_update, record_classification_review,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 15
MAP_POINT_LIMIT = 500


def _map_point(complaint, link=True):
    return {
        "id": complaint.complaint_id,
        "category": complaint.damage_category,
        "status": complaint.status,
        "location": complaint.location_name,
        "lat": complaint.latitude,
        "lng": complaint.longitude,
        "url": url_for("admin.complaint_detail", complaint_id=complaint.complaint_id) if link else None,
    }


@admin_bp.route("/")
@admin_required
def dashboard():
    statuses = current_app.config["COMPLAINT_STATUSES"]
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    query = Complaint.query
    if status_filter in statuses:
        query = query.filter_by(status=status_filter)
    else:
        status_filter = ""

    pagination = query.order_by(Complaint.created_at.desc()).paginate(
        page=page, per_page=PAGE_SIZE, error_out=False
    )

    counts = dict(db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all())
    summary = {
        "total": sum(counts.values()),
        "new": counts.get("Submitted", 0),
        "awaiting_verification": counts.get("Under Review", 0),
        "assigned": sum(counts.get(s, 0) for s in TEAM_REQUIRED_STATUSES),
        "resolved": counts.get("Resolved", 0),
    }

    located = (
        Complaint.query
        .filter(Complaint.latitude.isnot(None), Complaint.longitude.isnot(None))
        .order_by(Complaint.created_at.desc())
        .limit(MAP_POINT_LIMIT)
        .all()
    )

    return render_template(
        "admin_dashboard.html",
        pagination=pagination,
        complaints=pagination.items,
        summary=summary,
        statuses=statuses,
        status_filter=status_filter,
        map_points=[_map_point(c) for c in located],
    )


@admin_bp.route("/complaints/<complaint_id>")
@admin_required
def complaint_detail(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first_or_404()

    updates = sorted(complaint.updates, key=lambda u: (u.created_at, u.id))
    user_ids = {u.updated_by for u in updates if u.updated_by} | {
        e.uploaded_by for e in complaint.repair_evidence if e.uploaded_by
    }
    names = {u.id: u.name for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    map_points = []
    if complaint.latitude is not None and complaint.longitude is not None:
        map_points = [_map_point(complaint, link=False)]

    return render_template(
        "admin_complaint.html",
        complaint=complaint,
        updates=updates,
        names=names,
        statuses=current_app.config["COMPLAINT_STATUSES"],
        categories=current_app.config["DAMAGE_CATEGORIES"],
        evidence_kinds=EVIDENCE_KINDS,
        map_points=map_points,
    )


def _back_to(complaint):
    return redirect(url_for("admin.complaint_detail", complaint_id=complaint.complaint_id))


@admin_bp.route("/complaints/<complaint_id>/status", methods=["POST"])
@admin_required
def update_status(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first_or_404()
    try:
        apply_status_update(
            complaint,
            admin_id=session["user_id"],
            new_status=request.form.get("status", ""),
            assigned_team=request.form.get("assigned_team"),
            remarks=request.form.get("remarks"),
            valid_statuses=current_app.config["COMPLAINT_STATUSES"],
        )
        flash("Complaint updated.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")
    return _back_to(complaint)


@admin_bp.route("/complaints/<complaint_id>/classification", methods=["POST"])
@admin_required
def review_classification(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first_or_404()
    try:
        record_classification_review(
            complaint,
            admin_id=session["user_id"],
            label=request.form.get("classification", ""),
            valid_labels=current_app.config["DAMAGE_CATEGORIES"],
        )
        flash("Classification review saved.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")
    return _back_to(complaint)


@admin_bp.route("/complaints/<complaint_id>/evidence", methods=["POST"])
@admin_required
def upload_evidence(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first_or_404()
    try:
        add_repair_evidence(
            complaint,
            admin_id=session["user_id"],
            file_storage=request.files.get("photo"),
            kind=request.form.get("kind", ""),
            note=request.form.get("note"),
            upload_folder=current_app.config["UPLOAD_FOLDER"],
            allowed_extensions=current_app.config["ALLOWED_EXTENSIONS"],
        )
        flash("Repair photo uploaded.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")
    return _back_to(complaint)