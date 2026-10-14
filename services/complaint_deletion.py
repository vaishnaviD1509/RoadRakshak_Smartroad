"""Lets a citizen delete their own complaint (only before staff act on it)."""
import os

from models import db
from models.complaint import CITIZEN_DELETABLE_STATUSES


class DeleteError(Exception):
    """Raised with a user-facing message when a complaint cannot be deleted."""


def delete_own_complaint(complaint, user_id, upload_folder):
    """Delete a complaint, its status history and its photos.

    Allowed only for the complaint's owner and only while its status is in
    CITIZEN_DELETABLE_STATUSES (Submitted or Rejected).
    """
    if complaint.user_id != user_id:
        raise DeleteError("You can only delete your own complaints.")
    if not complaint.citizen_can_delete:
        raise DeleteError(
            f"This complaint is already \"{complaint.status}\", so it can no longer be deleted. "
            "Staff are working on it."
        )

    filenames = [complaint.image_path] + [e.image_path for e in complaint.repair_evidence]

    # updates and repair evidence rows go too (cascade on the relationships)
    db.session.delete(complaint)
    db.session.commit()

    # Remove the photo files only after the database change succeeded.
    for name in filenames:
        if not name:
            continue
        try:
            os.remove(os.path.join(upload_folder, os.path.basename(name)))
        except OSError:
            pass  # already gone - nothing to clean up