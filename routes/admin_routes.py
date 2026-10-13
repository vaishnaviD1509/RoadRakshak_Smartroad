import csv
import io
import os
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, jsonify,
                    redirect, render_template, request, send_file, session,
                    url_for)
from sqlalchemy import func

from models import db
from models.complaint import PRIORITIES, Complaint
from models.user import User
from routes.decorators import admin_required
from services.complaint_search import (CSV_COLUMNS, NO_TEAM, SORTS,
                                         active_filters, csv_row,
                                         filtered_query, team_filter_options)
from services.complaint_service import (EVIDENCE_KINDS, UpdateError,
                                          add_repair_evidence,
                                          apply_status_update, mark_duplicate,
                                          record_classification_review,
                                          set_priority)
from services.damage_detection import ai_available
from services.duplicate_service import (DUPLICATE_RADIUS_METERS,
                                          find_possible_duplicates)
from services.pdf_report import build_summary_pdf
from services.team_service import (active_team_names, create_team,
                                     set_team_active, team_summaries,
                                     unlisted_team_names)
from services.user_service import (create_or_promote_admin, list_staff,
                                     remove_admin_access)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 15
MAP_POINT_LIMIT = 500
EXPORT_LIMIT = 5000

NEW_STATUSES = {"Submitted"}
AWAITING_VERIFICATION_STATUSES = {"Under Review"}
ASSIGNED_STATUSES = {"Assigned for Repair", "Repair in Progress"}
RESOLVED_STATUSES = {"Resolved"}


def _map_point(c):
    return {
        "id": c.complaint_id,
        "category": c.damage_category,
        "status": c.status,
        "location": c.location_name,
        "lat": c.latitude,
        "lng": c.longitude,
        "url": url_for("admin.complaint_detail", complaint_id=c.complaint_id),
    }


def _ai_status():
    """What the AI detection panel on the dashboard shows: whether the model
    can run right now, why not if it can't, and how complaints were classified."""
    model_path = current_app.config["AI_MODEL_PATH"]
    model_exists = os.path.isfile(model_path)
    active = ai_available(model_path)

    if active:
        reason = "A trained model is loaded. New photos get a preliminary category and confidence score."
    elif model_exists:
        reason = ("A model file was found, but the ultralytics library is not installed. "
                  "Run: python -m pip install -r requirements-ai.txt")
    else:
        reason = ("No trained model was found, so new complaints go straight to manual review. "
                  "See ai_models/README.md to train one.")

    model_updated = None
    if model_exists:
        model_updated = datetime.utcfromtimestamp(os.path.getmtime(model_path))

    return {
        "active": active,
        "reason": reason,
        "model_file": os.path.basename(model_path) if model_exists else None,
        "model_updated": model_updated,
        "threshold": current_app.config["AI_CONFIDENCE_THRESHOLD"],
        # AI result with a confidence score = a genuine model prediction
        "classified_by_ai": Complaint.query.filter(
            Complaint.ai_prediction.isnot(None), Complaint.ai_confidence.isnot(None)
        ).count(),
        # a label with no score = set or corrected by an administrator
        "set_by_admin": Complaint.query.filter(
            Complaint.ai_prediction.isnot(None), Complaint.ai_confidence.is_(None)
        ).count(),
        "no_ai_result": Complaint.query.filter(Complaint.ai_prediction.is_(None)).count(),
    }


@admin_bp.route("/")
@admin_required
def dashboard():
    page = request.args.get("page", 1, type=int)
    filters = active_filters(
        request.args, current_app.config["COMPLAINT_STATUSES"], current_app.config["DAMAGE_CATEGORIES"]
    )
    status_filter = filters.get("status", "")

    pagination = filtered_query(filters).paginate(
        page=page, per_page=PAGE_SIZE, error_out=False
    )

    summary = {
        "total": Complaint.query.count(),
        "new": Complaint.query.filter(Complaint.status.in_(NEW_STATUSES)).count(),
        "awaiting_verification": Complaint.query.filter(
            Complaint.status.in_(AWAITING_VERIFICATION_STATUSES)
        ).count(),
        "assigned": Complaint.query.filter(Complaint.status.in_(ASSIGNED_STATUSES)).count(),
        "resolved": Complaint.query.filter(Complaint.status.in_(RESOLVED_STATUSES)).count(),
        "urgent_open": Complaint.query.filter(
            Complaint.priority.in_(("High", "Urgent")),
            Complaint.status.notin_(("Resolved", "Rejected")),
        ).count(),
    }

    map_complaints = (
        Complaint.query.filter(Complaint.latitude.isnot(None), Complaint.longitude.isnot(None))
        .order_by(Complaint.created_at.desc())
        .limit(MAP_POINT_LIMIT)
        .all()
    )
    map_points = [_map_point(c) for c in map_complaints]

    return render_template(
        "admin_dashboard.html",
        pagination=pagination,
        complaints=pagination.items,
        summary=summary,
        statuses=current_app.config["COMPLAINT_STATUSES"],
        categories=current_app.config["DAMAGE_CATEGORIES"],
        status_filter=status_filter,
        filters=filters,
        priorities=PRIORITIES,
        sorts=SORTS,
        team_options=team_filter_options(),
        no_team=NO_TEAM,
        map_points=map_points,
        ai_status=_ai_status(),
    )


@admin_bp.route("/export.csv")
@admin_required
def export_csv():
    """Download the complaints list (with whatever search and filters are
    applied on the dashboard) as a spreadsheet-friendly CSV file."""
    filters = active_filters(
        request.args, current_app.config["COMPLAINT_STATUSES"], current_app.config["DAMAGE_CATEGORIES"]
    )
    complaints = filtered_query(filters).limit(EXPORT_LIMIT).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for c in complaints:
        writer.writerow(csv_row(c))

    filename = f"road-rakshak-complaints-{datetime.utcnow().strftime('%Y%m%d')}.csv"
    # The leading BOM makes Excel read non-English place names correctly.
    return Response(
        "\ufeff" + buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_bp.route("/complaints/<complaint_id>")
@admin_required
def complaint_detail(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    map_points = [_map_point(complaint)] if complaint.latitude and complaint.longitude else []
    names = {u.id: u.name for u in User.query.all()}

    team_names = active_team_names()
    # Keep a team typed in earlier selectable, so saving other changes
    # doesn't quietly clear it.
    if complaint.assigned_team and complaint.assigned_team not in team_names:
        team_names = team_names + [complaint.assigned_team]

    return render_template(
        "admin_complaint.html",
        complaint=complaint,
        statuses=current_app.config["COMPLAINT_STATUSES"],
        categories=current_app.config["DAMAGE_CATEGORIES"],
        evidence_kinds=EVIDENCE_KINDS,
        map_points=map_points,
        updates=complaint.updates,
        names=names,
        priorities=PRIORITIES,
        team_names=team_names,
        use_team_dropdown=bool(active_team_names()),
        duplicates=find_possible_duplicates(complaint),
        duplicate_radius=DUPLICATE_RADIUS_METERS,
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
            admin_id=session["user_id"],
            new_status=request.form.get("status", ""),
            assigned_team=request.form.get("assigned_team", ""),
            remarks=request.form.get("remarks", ""),
            valid_statuses=current_app.config["COMPLAINT_STATUSES"],
            allowed_teams=active_team_names() or None,
        )
        flash("Status updated.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


@admin_bp.route("/complaints/<complaint_id>/classification", methods=["POST"])
@admin_required
def review_classification(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    try:
        record_classification_review(
            complaint,
            admin_id=session["user_id"],
            label=request.form.get("classification", ""),
            valid_labels=current_app.config["DAMAGE_CATEGORIES"],
        )
        flash("Classification reviewed.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


@admin_bp.route("/complaints/<complaint_id>/evidence", methods=["POST"])
@admin_required
def upload_evidence(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    try:
        add_repair_evidence(
            complaint,
            admin_id=session["user_id"],
            file_storage=request.files.get("photo"),
            kind=request.form.get("kind", ""),
            note=request.form.get("note", ""),
            upload_folder=current_app.config["UPLOAD_FOLDER"],
            allowed_extensions=current_app.config["ALLOWED_EXTENSIONS"],
        )
        flash("Evidence uploaded.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


@admin_bp.route("/complaints/<complaint_id>/priority", methods=["POST"])
@admin_required
def update_priority(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    try:
        set_priority(complaint, admin_id=session["user_id"], priority=request.form.get("priority", ""))
        flash("Priority updated.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


@admin_bp.route("/complaints/<complaint_id>/duplicate", methods=["POST"])
@admin_required
def mark_as_duplicate(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint:
        abort(404)

    original = Complaint.query.filter_by(complaint_id=request.form.get("original_id", "")).first()
    try:
        mark_duplicate(
            complaint, admin_id=session["user_id"], original=original,
            valid_statuses=current_app.config["COMPLAINT_STATUSES"],
        )
        flash(f"Marked as a duplicate of {original.complaint_id}.", "success")
    except UpdateError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.complaint_detail", complaint_id=complaint_id))


# --- Repair teams ----------------------------------------------------

@admin_bp.route("/teams")
@admin_required
def teams():
    return render_template(
        "admin_teams.html", summaries=team_summaries(), unlisted=unlisted_team_names(),
    )


@admin_bp.route("/teams/add", methods=["POST"])
@admin_required
def add_team():
    try:
        team = create_team(request.form.get("name", ""))
        flash(f'Team "{team.name}" is ready to use.', "success")
    except UpdateError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.teams"))


@admin_bp.route("/teams/<int:team_id>/active", methods=["POST"])
@admin_required
def toggle_team(team_id):
    turn_on = request.form.get("active") == "1"
    try:
        team = set_team_active(team_id, turn_on)
        flash(f'Team "{team.name}" is now {"available" if turn_on else "switched off"}.', "success")
    except UpdateError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.teams"))


# --- Staff accounts --------------------------------------------------

@admin_bp.route("/staff")
@admin_required
def staff():
    return render_template("admin_staff.html", staff_members=list_staff(), my_id=session["user_id"])


@admin_bp.route("/staff/add", methods=["POST"])
@admin_required
def add_staff():
    try:
        user, created = create_or_promote_admin(
            request.form.get("email", ""),
            name=request.form.get("name", ""),
            password=request.form.get("password", ""),
        )
        if created:
            flash(f"Staff account created for {user.email}. Share the password with them securely.", "success")
        else:
            flash(f"{user.email} already had an account and now has staff access. Their password is unchanged.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.staff"))


@admin_bp.route("/staff/<int:user_id>/remove", methods=["POST"])
@admin_required
def remove_staff(user_id):
    try:
        user = remove_admin_access(user_id, acting_admin_id=session["user_id"])
        flash(f"{user.email} no longer has staff access.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.staff"))


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