"""Try the AI model on one photo from the command line.

It uses exactly the same code as the website (services/damage_detection.py),
so what you see here is what a citizen's complaint would get.

Usage:
    python scripts/predict_image.py path/to/photo.jpg
    python scripts/predict_image.py photo.jpg --model ai_models/road_damage_model.pt --threshold 0.35
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config  # noqa: E402
from services.damage_detection import detect_damage  # noqa: E402


def run(image_path: str, model_path: str, threshold: float) -> dict:
    return detect_damage(image_path, model_path, threshold)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", help="Path to a JPG or PNG photo")
    parser.add_argument("--model", default=Config.AI_MODEL_PATH)
    parser.add_argument("--threshold", type=float, default=Config.AI_CONFIDENCE_THRESHOLD)
    args = parser.parse_args(argv)

    if not os.path.isfile(args.image):
        print(f"Image not found: {args.image}")
        return 2

    result = run(args.image, args.model, args.threshold)
    print(f"Prediction : {result['prediction'] or '-'}")
    confidence = result["confidence"]
    print(f"Confidence : {f'{confidence * 100:.1f}%' if confidence is not None else '-'}")
    print(f"Message    : {result['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())