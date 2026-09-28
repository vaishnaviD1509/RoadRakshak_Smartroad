import os
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, current_app, send_from_directory, abort,
)
from routes.decorators import login_required
from routes.csrf import get_form_token, consume_form_token
from services.image_processing import validate_and_save_image, ImageValidationError
from services.complaint_service import create_complaint
from services.damage_detection import detect_damage, looks_like_document
from models.complaint import Complaint
from models.repair_evidence import RepairEvidence

citizen_bp = Blueprint("citizen", __name__)


@citizen_bp.route("/report", methods=["GET", "POST"])
@login_required
def report_damage():
    damage_categories = current_app.config["DAMAGE_CATEGORIES"]

    if request.method == "POST":
        form_token = request.form.get("form_token", "")
        if not consume_form_token("report_damage", form_token):
            flash("This form has already been submitted or has expired. Please try again.", "warning")
            return redirect(url_for("citizen.report_damage"))

        damage_category = request.form.get("damage_category", "")
        description = (request.form.get("description") or "").strip()
        location_name = (request.form.get("location_name") or "").strip()
        latitude = request.form.get("latitude") or None
        longitude = request.form.get("longitude") or None
        image_file = request.files.get("photo")

        errors = []
        if damage_category not in damage_categories:
            errors.append("Please select a valid damage category.")
        if not description or len(description) < 10:
            errors.append("Please describe the problem in at least 10 characters.")
        if not location_name:
            errors.append("Please enter the road or area name.")
        if not latitude or not longitude:
            errors.append("Please select the damage location on the map.")

        stored_filename = None
        if not errors:
            try:
                stored_filename = validate_and_save_image(
                    image_file,
                    current_app.config["UPLOAD_FOLDER"],
                    current_app.config["ALLOWED_EXTENSIONS"],
                )
            except ImageValidationError as e:
                errors.append(str(e))

        # Reject document/receipt/screenshot-style photos outright rather
        # than accepting them with just a warning - see
        # services/damage_detection.py:looks_like_document() for what this
        # heuristic does and doesn't catch.
        if not errors and stored_filename:
            saved_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_filename)
            if looks_like_document(saved_path):
                os.remove(saved_path)
                stored_filename = None
                errors.append(
                    "This photo doesn't look like a photo of a road (it looks like a "
                    "document, receipt, or screenshot). Please upload a clear photo of "
                    "the actual road damage."
                )

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "report.html",
                damage_categories=damage_categories,
                form_token=get_form_token("report_damage"),
                form_data=request.form,
            ), 400

        try:
            lat_val = float(latitude)
            lng_val = float(longitude)
        except (TypeError, ValueError):
            lat_val = lng_val = None

        ai_result = detect_damage(
            os.path.join(current_app.config["UPLOAD_FOLDER"], stored_filename),
            current_app.config["AI_MODEL_PATH"],
            current_app.config["AI_CONFIDENCE_THRESHOLD"],
        )

        complaint = create_complaint(
            user_id=session["user_id"],
            damage_category=damage_category,
            description=description,
            location_name=location_name,
            latitude=lat_val,
            longitude=lng_val,
            image_filename=stored_filename,
            ai_prediction=ai_result["prediction"],
            ai_confidence=ai_result["confidence"],
        )

        flash("Your complaint has been submitted.", "success")
        flash(ai_result["message"], "info")
        return redirect(url_for("citizen.report_confirmation", complaint_id=complaint.complaint_id))

    return render_template(
        "report.html",
        damage_categories=damage_categories,
        form_token=get_form_token("report_damage"),
        form_data={},
    )


@citizen_bp.route("/report/confirmation/<complaint_id>")
@login_required
def report_confirmation(complaint_id):
    complaint = Complaint.query.filter_by(complaint_id=complaint_id).first_or_404()

    if complaint.user_id != session["user_id"] and session.get("role") != "admin":
        abort(403)

    return render_template("report_confirmation.html", complaint=complaint)


@citizen_bp.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    """Serve a complaint or repair-evidence photo, but only to the
    complaint's owner or an admin.

    Uploaded photos are not stored under static/ specifically so they
    can't be fetched by guessing a URL - this route is the only way to
    reach them, and it enforces ownership on every request.
    """
    complaint = Complaint.query.filter_by(image_path=filename).first()

    if complaint is None:
        evidence = RepairEvidence.query.filter_by(image_path=filename).first_or_404()
        complaint = evidence.complaint

    if complaint.user_id != session["user_id"] and session.get("role") != "admin":
        abort(403)

    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


# Status groupings for the dashboard summary cards. These match the
# landing page's definitions so the same word means the same thing in
# both places. "Verified" and "Rejected" count toward the total only.
UNDER_REVIEW_STATUSES = {"Submitted", "Under Review"}
BEING_REPAIRED_STATUSES = {"Assigned for Repair", "Repair in Progress"}


@citizen_bp.route("/dashboard")
@login_required
def dashboard():
    """A citizen's own complaints, newest first, with summary counts."""
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