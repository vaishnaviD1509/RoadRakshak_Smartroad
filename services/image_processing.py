"""Image upload handling: validation and secure storage.

Stage 3 only saves and validates the image. Stage 4 adds the AI
detection pass that reads the saved file back in.
"""
import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError


class ImageValidationError(Exception):
    """Raised when an uploaded file fails validation."""


def allowed_extension(filename: str, allowed_extensions: set) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def validate_and_save_image(file_storage, upload_folder: str, allowed_extensions: set) -> str:
    """Validate an uploaded FileStorage and save it under upload_folder.

    Returns the stored filename (not the full path) on success.
    Raises ImageValidationError with a user-facing message on failure.
    """
    if file_storage is None or file_storage.filename == "":
        raise ImageValidationError("Please choose a photograph of the road damage.")

    original_name = secure_filename(file_storage.filename)
    if not original_name or not allowed_extension(original_name, allowed_extensions):
        raise ImageValidationError("Only JPG, JPEG, and PNG images are accepted.")

    extension = original_name.rsplit(".", 1)[1].lower()
    stored_filename = f"{uuid.uuid4().hex}.{extension}"
    stored_path = os.path.join(upload_folder, stored_filename)

    file_storage.save(stored_path)

    # Confirm the saved file is actually a valid, openable image (guards
    # against a renamed non-image file slipping past the extension check).
    try:
        with Image.open(stored_path) as img:
            img.verify()
    except (UnidentifiedImageError, OSError):
        os.remove(stored_path)
        raise ImageValidationError("The uploaded file is not a valid image.")

    return stored_filename