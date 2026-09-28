"""Business logic for creating a complaint and its first status entry."""
from models import db
from models.complaint import Complaint
from models.complaint_update import ComplaintUpdate
from models.repair_evidence import RepairEvidence


def create_complaint(
    user_id: int,
    damage_category: str,
    description: str,
    location_name: str,
    latitude,
    longitude,
    image_filename: str,
    ai_prediction: str = None,
    ai_confidence: float = None,
) -> Complaint:
    complaint = Complaint(
        user_id=user_id,
        damage_category=damage_category,
        description=description,
        location_name=location_name,
        latitude=latitude,
        longitude=longitude,
        image_path=image_filename,
        status="Submitted",
        ai_prediction=ai_prediction,
        ai_confidence=ai_confidence,
    )
    db.session.add(complaint)
    db.session.flush()  # get complaint.id before committing, for the update row

    first_update = ComplaintUpdate(
        complaint_id=complaint.id,
        previous_status=None,
        new_status="Submitted",
        remarks="Complaint submitted by citizen.",
        updated_by=user_id,
    )
    db.session.add(first_update)
    db.session.commit()

    return complaint


# --- Administrator actions --------------------------------------------

class UpdateError(Exception):
    """Raised with a user-facing message when an admin action is invalid."""


TEAM_REQUIRED_STATUSES = {"Assigned for Repair", "Repair in Progress"}
# A complaint has to have passed review before it can be closed as resolved.
RESOLVABLE_FROM = {"Verified", "Assigned for Repair", "Repair in Progress", "Resolved"}
EVIDENCE_KINDS = ["Before repair", "Repair progress", "After repair"]

MAX_REMARKS_LENGTH = 2000
MAX_TEAM_LENGTH = 120
MAX_EVIDENCE_NOTE_LENGTH = 200


def apply_status_update(complaint, admin_id, new_status, assigned_team, remarks, valid_statuses):
    """Change a complaint's status / team and/or add a remark, with a log row.

    Every change is recorded as a ComplaintUpdate (previous status, new
    status, remarks, who, when). A remark added without changing the
    status is recorded with the same status on both sides.
    """
    if new_status not in valid_statuses:
        raise UpdateError("Choose a valid status.")

    assigned_team = (assigned_team or "").strip() or None
    remarks = (remarks or "").strip() or None

    if assigned_team and len(assigned_team) > MAX_TEAM_LENGTH:
        raise UpdateError(f"Team name must be {MAX_TEAM_LENGTH} characters or fewer.")
    if remarks and len(remarks) > MAX_REMARKS_LENGTH:
        raise UpdateError(f"Remarks must be {MAX_REMARKS_LENGTH} characters or fewer.")

    previous_status = complaint.status

    if new_status == "Rejected" and not remarks:
        raise UpdateError("Please give a reason when rejecting a complaint.")
    if new_status in TEAM_REQUIRED_STATUSES and not assigned_team:
        raise UpdateError("Assign a responsible team before moving a complaint to repair.")
    if new_status == "Resolved" and previous_status not in RESOLVABLE_FROM:
        raise UpdateError("A complaint must be verified before it can be marked resolved.")

    status_changed = new_status != previous_status
    team_changed = assigned_team != complaint.assigned_team

    if not (status_changed or team_changed or remarks):
        raise UpdateError("Nothing to update - change the status or team, or add a remark.")

    parts = []
    if remarks:
        parts.append(remarks)
    if team_changed:
        parts.append(
            f"(Assigned team: {assigned_team}.)" if assigned_team else "(Assigned team cleared.)"
        )

    complaint.status = new_status
    complaint.assigned_team = assigned_team
    db.session.add(ComplaintUpdate(
        complaint_id=complaint.id,
        previous_status=previous_status,
        new_status=new_status,
        remarks=" ".join(parts) or None,
        updated_by=admin_id,
    ))
    db.session.commit()


def record_classification_review(complaint, admin_id, label, valid_labels):
    """Confirm or correct the AI classification and log the review.

    If the admin picks the label the model already predicted, the model's
    confidence is kept (it's a confirmation). Otherwise the label is
    replaced and the confidence cleared, since the model's score no longer
    describes the label - Complaint.ai_admin_reviewed then reports True.
    """
    if label not in valid_labels:
        raise UpdateError("Choose a valid damage category.")

    if complaint.ai_prediction == label and complaint.ai_confidence is not None:
        remark = f"Administrator confirmed the AI classification: {label}."
    else:
        if complaint.ai_prediction is None:
            before = "no AI result was available"
        elif complaint.ai_confidence is None:
            before = f"previously set to {complaint.ai_prediction} by an administrator"
        else:
            before = f"AI predicted {complaint.ai_prediction} at {complaint.ai_confidence * 100:.1f}% confidence"
        remark = f"Administrator set the classification to {label} ({before})."
        complaint.ai_prediction = label
        complaint.ai_confidence = None

    db.session.add(ComplaintUpdate(
        complaint_id=complaint.id,
        previous_status=complaint.status,
        new_status=complaint.status,
        remarks=remark,
        updated_by=admin_id,
    ))
    db.session.commit()


def add_repair_evidence(complaint, admin_id, file_storage, kind, note, upload_folder, allowed_extensions):
    """Validate and store a repair photo, attaching it to the complaint."""
    from services.image_processing import validate_and_save_image, ImageValidationError

    if kind not in EVIDENCE_KINDS:
        raise UpdateError("Choose whether this is a before, progress, or after photo.")
    note = (note or "").strip()
    if len(note) > MAX_EVIDENCE_NOTE_LENGTH:
        raise UpdateError(f"The photo note must be {MAX_EVIDENCE_NOTE_LENGTH} characters or fewer.")

    try:
        stored_filename = validate_and_save_image(file_storage, upload_folder, allowed_extensions)
    except ImageValidationError as exc:
        raise UpdateError(str(exc))

    db.session.add(RepairEvidence(
        complaint_id=complaint.id,
        image_path=stored_filename,
        description=f"{kind}: {note}" if note else kind,
        uploaded_by=admin_id,
    ))
    db.session.commit()