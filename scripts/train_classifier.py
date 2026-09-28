"""Train a YOLOv8 image-classification model on the split dataset.

Prerequisite: run scripts/split_dataset.py first to produce dataset/train,
dataset/val, dataset/test.

Usage:
    pip install ultralytics
    python scripts/train_classifier.py --data dataset --epochs 20

This fine-tunes a small pretrained YOLOv8n-cls model (downloaded
automatically by ultralytics on first run) on your road-issue categories.
Training on CPU works but is slow; a GPU will finish this in minutes
instead of hours.

After training, the best weights are copied to:
    ai_models/road_damage_model.pt
so services/damage_detection.py picks them up automatically.
"""
import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default="dataset", help="Path to the split dataset (train/val/test folders)")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--model", default="yolov8n-cls.pt", help="Base pretrained model to fine-tune")
    parser.add_argument("--project", default="ai_models/training_runs")
    parser.add_argument("--name", default="road_damage_classifier")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit(
            "ultralytics is not installed. Run: pip install ultralytics"
        )

    data_path = Path(args.data).resolve()
    if not (data_path / "train").is_dir():
        raise SystemExit(
            f"Expected {data_path}/train to exist. Run scripts/split_dataset.py first."
        )

    model = YOLO(args.model)
    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        project=args.project,
        name=args.name,
    )

    run_dir = Path(results.save_dir)
    best_weights = run_dir / "weights" / "best.pt"

    if not best_weights.exists():
        raise SystemExit(f"Training finished but best.pt wasn't found at {best_weights}")

    target = Path("ai_models") / "road_damage_model.pt"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_weights, target)

    print(f"\nTraining complete. Best weights copied to: {target.resolve()}")
    print("Restart the Flask app to start using this model for AI detection.")


if __name__ == "__main__":
    main()