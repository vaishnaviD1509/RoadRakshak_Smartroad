import os
from datetime import datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                    render_template, request, send_file, session, url_for)
from sqlalchemy import func

from models import db
from models.complaint import Complaint
from routes.decorators import admin_required
from services.complaint_service import (EVIDENCE_KINDS, UpdateError,
                                          add_repair_evidence,
                                          apply_status_update,
                                          record_classification_review)
from services.image_processing import ImageValidationError, validate_and_save_image
from services.pdf_report import build_summary_pdf

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 15
MAP_POINT_LIMIT = 500


@admin_bp.route("/")
@admin_required
def dashboard():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    category_filter = request.args.get("category", "")

    query = Complaint.query
    if status_filter in current_app.config["COMPLAINT_STATUSES"]:
        query = query.filter_by(status=status_filter)
    if category_filter in current_app.config["DAMAGE_CATEGORIES"]:
        query = query.filter_by(damage_category=category_filter)

    pagination = query.order_by(Complaint.created_at.desc()).paginate(
        page=page, per_page=PAGE_SIZE, error_out=False
    )

    summary = {
        "total": Complaint.query.count(),
        "submitted": Complaint.query.filter_by(status="Submitted").count(),
        "in_progress": Complaint.query.filter(
            Complaint.status.in_(["Under Review", "Verified", "Assigned for Repair", "Repair in Progress"])
        ).count(),
        "resolved": Complaint.query.filter_by(status="Resolved").count(),
    }

    return render_template(
        "admin_dashboard.html",
        pagination=pagination,
        complaints=pagination.items,
        summary=summary,
        statuses=current_app.config["COMPLAINT_STATUSES"],
        categories=current_app.config["DAMAGE_CATEGORIES"],
        status_filter=status_filter,
        category_filter=category_filter,
    )


@admin_bp.route("/complaints/<complaint_id>")
@admin_required
def complaint_detail(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)
    return render_template(
        "admin_complaint.html",
        complaint=complaint,
        statuses=current_app.config["COMPLAINT_STATUSES"],
        categories=current_app.config["DAMAGE_CATEGORIES"],
        evidence_kinds=EVIDENCE_KINDS,
    )


@admin_bp.route("/complaints/<complaint_id>/status", methods=["POST"])
@admin_required
def update_status(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    try:
        apply_status_update(
            complaint,
            new_status=request.form.get("status", ""),
            remarks=request.form.get("remarks", ""),
            assigned_team=request.form.get("assigned_team", ""),
            updated_by=session.get("name", "Admin"),
        )
        flash("Status updated.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


@admin_bp.route("/complaints/<complaint_id>/review", methods=["POST"])
@admin_required
def review_classification(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    confirmed = request.form.get("decision") == "confirm"
    corrected_label = request.form.get("corrected_label", "")

    record_classification_review(
        complaint, confirmed=confirmed, corrected_label=corrected_label,
        updated_by=session.get("name", "Admin"),
    )
    flash("Classification reviewed.", "success")
    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


@admin_bp.route("/complaints/<complaint_id>/evidence", methods=["POST"])
@admin_required
def upload_evidence(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    kind = request.form.get("kind", "")
    notes = request.form.get("notes", "")
    image = request.files.get("image")

    try:
        saved_path = validate_and_save_image(
            image, current_app.config["UPLOAD_FOLDER"], current_app.config["ALLOWED_EXTENSIONS"]
        )
        add_repair_evidence(
            complaint, kind=kind, image_path=os.path.basename(saved_path),
            notes=notes, uploaded_by=session.get("name", "Admin"),
        )
        flash("Evidence uploaded.", "success")
    except (ImageValidationError, UpdateError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


# --- Stage 9: analytics dashboard -----------------------------------

@admin_bp.route("/analytics")
@admin_required
def analytics():
    return render_template(
        "admin_analytics.html",
        categories=current_app.config["DAMAGE_CATEGORIES"],
    )


@admin_bp.route("/api/analytics")
@admin_required
def analytics_data():
    """Aggregated counts for the analytics charts, as real database
    queries (not hardcoded numbers), optionally filtered by date range
    and/or damage category from the query string."""
    category_filter = request.args.get("category", "")
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    return jsonify(_compute_analytics(category_filter, date_from, date_to))


def _compute_analytics(category_filter: str, date_from, date_to) -> dict:
    """Shared aggregation behind both the analytics JSON endpoint (Stage 9)
    and the PDF summary report (Stage 10), so the two never disagree."""
    base_query = Complaint.query
    if category_filter in current_app.config["DAMAGE_CATEGORIES"]:
        base_query = base_query.filter_by(damage_category=category_filter)
    if date_from:
        base_query = base_query.filter(Complaint.created_at >= date_from)
    if date_to:
        base_query = base_query.filter(
            Complaint.created_at < date_to.replace(hour=23, minute=59, second=59)
        )

    # Complaints by damage category
    by_category_rows = (
        base_query.with_entities(Complaint.damage_category, func.count(Complaint.id))
        .group_by(Complaint.damage_category)
        .all()
    )
    by_category = {category: count for category, count in by_category_rows}

    # Complaints by status
    by_status_rows = (
        base_query.with_entities(Complaint.status, func.count(Complaint.id))
        .group_by(Complaint.status)
        .all()
    )
    by_status = {status: count for status, count in by_status_rows}

    # Complaints submitted over time (daily counts for the last 30 days
    # within the filtered set, oldest first)
    window_start = datetime.utcnow() - timedelta(days=29)
    timeline_query = base_query
    daily_rows = (
        timeline_query.with_entities(
            func.strftime("%Y-%m-%d", Complaint.created_at).label("day"),
            func.count(Complaint.id),
        )
        .filter(Complaint.created_at >= window_start)
        .group_by("day")
        .order_by("day")
        .all()
    )
    daily_counts = {day: count for day, count in daily_rows}
    timeline_labels = []
    timeline_values = []
    for offset in range(29, -1, -1):
        day = (datetime.utcnow() - timedelta(days=offset)).strftime("%Y-%m-%d")
        timeline_labels.append(day)
        timeline_values.append(daily_counts.get(day, 0))

    # Resolved vs unresolved
    resolved_count = by_status.get("Resolved", 0)
    total_count = sum(by_status.values())
    unresolved_count = total_count - resolved_count

    return {
        "by_category": {
            "labels": list(by_category.keys()),
            "values": list(by_category.values()),
        },
        "by_status": {
            "labels": list(by_status.keys()),
            "values": list(by_status.values()),
        },
        "timeline": {
            "labels": timeline_labels,
            "values": timeline_values,
        },
        "resolved_vs_unresolved": {
            "resolved": resolved_count,
            "unresolved": unresolved_count,
        },
        "total": total_count,
    }


# --- Stage 10: PDF reports -------------------------------------------

@admin_bp.route("/reports/summary")
@admin_required
def download_summary_pdf():
    """An admin-facing PDF summary report, built from the exact same
    aggregates as the analytics dashboard, for the same optional
    category/date-range filters."""
    category_filter = request.args.get("category", "")
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    stats = _compute_analytics(category_filter, date_from, date_to)
    pdf_buffer = build_summary_pdf(
        stats, date_from=date_from, date_to=date_to, category_filter=category_filter
    )

    filename = "road-rakshak-summary"
    if date_from:
        filename += f"-{date_from.strftime('%Y%m%d')}"
    if date_to:
        filename += f"-to-{date_to.strftime('%Y%m%d')}"
    filename += ".pdf"

    return send_file(
        pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename,
    )


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None