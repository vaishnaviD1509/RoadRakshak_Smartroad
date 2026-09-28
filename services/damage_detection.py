"""AI road damage detection (Stage 4) — image classification mode.

Design goal: the app must stay fully functional whether or not a trained
model is present. Nothing here fabricates a prediction or a confidence
score - if a model file isn't supplied, or a required library isn't
installed, detection is reported as unavailable and the complaint is
still submitted for manual review, per the project spec.

This module runs a YOLOv8 *classification* model rather than a bounding-box
detector, because the dataset available for this project (road-rakshak-
dataset.zip) is organized as one folder per category, not annotated with
bounding boxes. See scripts/split_dataset.py and scripts/train_classifier.py
to prepare and train a compatible model, and ai_models/README.md for the
full walkthrough.

To enable real detection:
  1. pip install ultralytics
  2. python scripts/split_dataset.py --source "path/to/Road Issues"
  3. python scripts/train_classifier.py --data dataset
     (this copies the trained weights to ai_models/road_damage_model.pt)
  4. Restart the app.
"""
import os

try:
    import cv2
except ImportError:  # pragma: no cover - opencv is in requirements.txt
    cv2 = None
import numpy as np


def looks_like_document(image_path: str) -> bool:
    """Heuristic check for document/receipt/screenshot-style images.

    A classifier trained only on road-damage categories has no way to say
    "this isn't a road at all" - it is forced to pick its closest known
    category even for something completely unrelated (a receipt, a
    screenshot, a selfie), often with deceptively high confidence. This
    catches the most common and visually distinctive case - documents -
    before the image ever reaches the model.

    This is a heuristic, not a general "is this a road?" classifier: it
    will not catch every irrelevant photo (e.g. a photo of a cat won't be
    flagged), only ones with a document's dominant look - a large
    proportion of near-white background and low color saturation
    throughout, which real outdoor road photos essentially never have.
    """
    if cv2 is None:
        return False

    img = cv2.imread(image_path)
    if img is None:
        return False

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    near_white_ratio = float(np.mean((value > 230) & (saturation < 30)))
    mean_saturation = float(np.mean(saturation))

    return near_white_ratio > 0.55 and mean_saturation < 40

# Map a trained model's raw class names (as produced by
# scripts/split_dataset.py's slugify()) to this app's fixed damage
# categories. Anything not listed here is passed through as-is (with
# underscores turned back into spaces and title-cased), shown to the
# reviewer as a preliminary label rather than forced into one of the
# seven categories.
CLASS_NAME_MAP = {
    "pothole_issues": "Pothole",
    "damaged_road_issues": "Broken Road Surface",
    "mixed_issues": "Other",
    "illegal_parking_issues": "Other",
    "broken_road_sign_issues": "Other",
    # Generic aliases, in case a differently-trained model uses these:
    "pothole": "Pothole",
    "crack": "Road Cracks",
    "cracks": "Road Cracks",
    "waterlogging": "Waterlogging",
    "manhole": "Open Manhole",
    "open_manhole": "Open Manhole",
}

_model_cache = {"loaded": False, "model": None, "error": None}


def _load_model(model_path: str):
    """Load and cache the YOLO model. Returns None (without raising) if
    the model file is missing or the ultralytics library isn't installed."""
    if _model_cache["loaded"]:
        return _model_cache["model"]

    _model_cache["loaded"] = True

    if not model_path or not os.path.exists(model_path):
        _model_cache["error"] = "no_model_file"
        return None

    try:
        from ultralytics import YOLO
    except ImportError:
        _model_cache["error"] = "ultralytics_not_installed"
        return None

    try:
        _model_cache["model"] = YOLO(model_path)
    except Exception as exc:  # noqa: BLE001 - any load failure should degrade gracefully
        _model_cache["error"] = f"model_load_failed: {exc}"
        _model_cache["model"] = None

    return _model_cache["model"]


def reset_model_cache():
    """Used by tests to force a fresh load attempt."""
    _model_cache["loaded"] = False
    _model_cache["model"] = None
    _model_cache["error"] = None


def _normalize_label(raw_label: str) -> str:
    key = raw_label.strip().lower()
    if key in CLASS_NAME_MAP:
        return CLASS_NAME_MAP[key]
    return raw_label.replace("_", " ").title()


def detect_damage(image_path: str, model_path: str, confidence_threshold: float = 0.35) -> dict:
    """Run AI damage classification on a saved complaint photo.

    Always returns a dict with these keys:
      available   - bool, whether a real AI result was produced
      prediction  - str or None, the predicted category label
      confidence  - float or None, 0-1 confidence of that prediction
      detections  - list with a single {"label", "confidence"} entry when
                    available, kept as a list for compatibility with
                    templates/future bounding-box detectors
      message     - a human-readable status for display to the citizen/admin
    """
    result = {
        "available": False,
        "prediction": None,
        "confidence": None,
        "detections": [],
        "message": (
            "AI analysis is unavailable in this build - no trained detection "
            "model has been connected yet. This complaint has been queued "
            "for manual review."
        ),
    }

    if cv2 is not None:
        readable = cv2.imread(image_path)
        if readable is None:
            result["message"] = (
                "AI analysis could not run because the image could not be "
                "read for processing. This complaint has been queued for "
                "manual review."
            )
            return result

        if looks_like_document(image_path):
            result["available"] = True
            result["message"] = (
                "This photo looks like a document, receipt, or screenshot "
                "rather than a photo of a road, so AI analysis was skipped "
                "to avoid an unreliable result. Your complaint has still "
                "been submitted and is queued for manual review - please "
                "make sure the uploaded photo actually shows the road "
                "damage if this wasn't intentional."
            )
            return result

    model = _load_model(model_path)
    if model is None:
        return result

    try:
        predictions = model.predict(source=image_path, verbose=False)
    except Exception:  # noqa: BLE001 - a runtime failure must not break submission
        result["message"] = (
            "AI analysis failed unexpectedly while processing this photo. "
            "This complaint has been queued for manual review."
        )
        return result

    if not predictions or getattr(predictions[0], "probs", None) is None:
        result["message"] = (
            "AI analysis did not return a usable result for this photo. "
            "This complaint has been queued for manual review."
        )
        return result

    r = predictions[0]
    probs = r.probs
    names = getattr(r, "names", {}) or {}

    top1_idx = int(probs.top1)
    top1_conf = float(probs.top1conf)
    raw_label = names.get(top1_idx, str(top1_idx))
    label = _normalize_label(raw_label)

    result["available"] = True

    if top1_conf < confidence_threshold:
        result["message"] = (
            "The AI model did not classify this photo with enough confidence "
            "to report a preliminary category. This complaint is still "
            "queued for manual review."
        )
        return result

    result["prediction"] = label
    result["confidence"] = round(top1_conf, 4)
    result["detections"] = [{"label": label, "confidence": round(top1_conf, 4)}]
    result["message"] = (
        f"Preliminary AI classification: {label} "
        f"({top1_conf * 100:.1f}% confidence). This is not a confirmed "
        "finding - an administrator will review it."
    )
    return result