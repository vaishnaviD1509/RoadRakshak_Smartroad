import os

from flask import (Blueprint, abort, current_app, flash, redirect,
                    render_template, request, send_file, send_from_directory,
                    session, url_for)

from models.complaint import Complaint
from routes.csrf import consume_form_token, get_form_token
from routes.decorators import login_required
from services.complaint_service import create_complaint
from services.damage_detection import detect_damage, looks_like_document
from services.image_processing import ImageValidationError, validate_and_save_image
from services.pdf_report import build_complaint_pdf

citizen_bp = Blueprint("citizen", __name__)

UNDER_REVIEW_STATUSES = {"Submitted", "Under Review"}
BEING_REPAIRED_STATUSES = {"Assigned for Repair", "Repair in Progress"}


@citizen_bp.route("/report", methods=["GET", "POST"])
@login_required
def report_damage():
    categories = current_app.config["DAMAGE_CATEGORIES"]

    if request.method == "POST":
        damage_category = request.form.get("damage_category", "")
        description = request.form.get("description", "").strip()
        location_name = request.form.get("location_name", "").strip()
        latitude = request.form.get("latitude") or None
        longitude = request.form.get("longitude") or None
        image = request.files.get("image")

        errors = []
        if damage_category not in categories:
            errors.append("Please choose a valid damage category.")
        if not description:
            errors.append("Please describe the issue.")
        if not location_name:
            errors.append("Please provide a location.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("report.html", categories=categories, form_data=request.form)

        try:
            saved_path = validate_and_save_image(
                image, current_app.config["UPLOAD_FOLDER"], current_app.config["ALLOWED_EXTENSIONS"]
            )
        except ImageValidationError as exc:
            flash(str(exc), "danger")
            return render_template("report.html", categories=categories, form_data=request.form)

        # Reject uploads that look like scanned documents/receipts rather
        # than outdoor road photos, instead of just flagging them.
        if looks_like_document(saved_path):
            os.remove(saved_path)
            flash("That image doesn't look like a road photo. Please upload a clear photo of the damage.", "danger")
            return render_template("report.html", categories=categories, form_data=request.form)

        ai_prediction, ai_confidence = detect_damage(
            saved_path, current_app.config["AI_MODEL_PATH"], current_app.config["AI_CONFIDENCE_THRESHOLD"]
        )

        complaint = create_complaint(
            user_id=session["user_id"],
            damage_category=damage_category,
            description=description,
            location_name=location_name,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            image_path=os.path.basename(saved_path),
            ai_prediction=ai_prediction,
            ai_confidence=ai_confidence,
        )
        return redirect(url_for("citizen.report_confirmation", complaint_id=complaint.complaint_id))

    return render_template("report.html", categories=categories, form_data={})


@citizen_bp.route("/report/confirmation/<complaint_id>")
@login_required
def report_confirmation(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint or complaint.user_id != session["user_id"]:
        abort(404)
    return render_template("report_confirmation.html", complaint=complaint)


@citizen_bp.route("/report/<complaint_id>/pdf")
@login_required
def download_complaint_pdf(complaint_id):
    """Lets a citizen download a PDF record of one of their own
    complaints - full details plus its status history. Same ownership
    check as everywhere else a complaint is looked up by ID."""
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first()
    if not complaint or complaint.user_id != session["user_id"]:
        abort(404)

    pdf_buffer = build_complaint_pdf(complaint)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{complaint.complaint_id}.pdf",
    )


@citizen_bp.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    complaint = Complaint.query.filter_by(image_path=filename).first()
    if not complaint:
        abort(404)
    is_owner = complaint.user_id == session["user_id"]
    is_admin = session.get("role") == "admin"
    if not (is_owner or is_admin):
        abort(403)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@citizen_bp.route("/dashboard")
@login_required
def dashboard():
    complaints = (
        Complaint.query.filter_by(user_id=session["user_id"])
        .order_by(Complaint.created_at.desc())
        .all()
    )
    summary = {
        "total": len(complaints),
        "under_review": sum(1 for c in complaints if c.status in UNDER_REVIEW_STATUSES),
        "being_repaired": sum(1 for c in complaints if c.status in BEING_REPAIRED_STATUSES),
        "resolved": sum(1 for c in complaints if c.status == "Resolved"),
    }
    return render_template("dashboard.html", complaints=complaints, summary=summary)