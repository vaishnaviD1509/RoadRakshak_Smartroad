"""Evaluate the trained road-damage classifier on the held-out test split.

Run this after scripts/train_classifier.py. It reads only dataset/test/<class>/
images, which the model never saw during training, so the numbers show how it
is likely to behave on new complaint photos.

Usage:
    python scripts/evaluate_model.py
    python scripts/evaluate_model.py --data dataset --model ai_models/road_damage_model.pt

The report is printed and also saved to ai_models/evaluation_report.txt.
"""
import argparse
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def collect_test_images(test_dir: Path):
    """Return [(image_path, true_class_name), ...] from test/<class>/ folders."""
    items = []
    for class_dir in sorted(p for p in test_dir.iterdir() if p.is_dir()):
        for img in sorted(class_dir.iterdir()):
            if img.is_file() and img.suffix.lower() in IMAGE_EXTENSIONS:
                items.append((img, class_dir.name))
    return items


def compute_metrics(y_true, y_pred, classes=None):
    """Accuracy, per-class precision/recall/F1 and a confusion matrix.

    Pure function (no model needed), so it can be tested on its own.
    confusion[true_class][predicted_class] = number of images.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")

    classes = sorted(set(classes or []) | set(y_true) | set(y_pred))
    confusion = {t: {p: 0 for p in classes} for t in classes}
    for true_label, predicted_label in zip(y_true, y_pred):
        confusion[true_label][predicted_label] += 1

    total = len(y_true)
    correct = sum(confusion[c][c] for c in classes)

    per_class = {}
    for c in classes:
        true_positive = confusion[c][c]
        predicted_as_c = sum(confusion[t][c] for t in classes)
        support = sum(confusion[c].values())
        precision = true_positive / predicted_as_c if predicted_as_c else 0.0
        recall = true_positive / support if support else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_class[c] = {
            "precision": precision, "recall": recall, "f1": f1, "support": support,
        }

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "classes": classes,
        "per_class": per_class,
        "confusion": confusion,
    }


def format_report(metrics: dict) -> str:
    classes = metrics["classes"]
    width = max([len(c) for c in classes] + [10])
    lines = [
        "Road Rakshak - model evaluation (test split)",
        "=" * 60,
        f"Images tested : {metrics['total']}",
        f"Correct       : {metrics['correct']}",
        f"Accuracy      : {metrics['accuracy'] * 100:.1f}%",
        "",
        f"{'Class':<{width}}  {'Precision':>9}  {'Recall':>7}  {'F1':>6}  {'Images':>6}",
        "-" * (width + 36),
    ]
    for c in classes:
        m = metrics["per_class"][c]
        lines.append(
            f"{c:<{width}}  {m['precision'] * 100:>8.1f}%  {m['recall'] * 100:>6.1f}%  "
            f"{m['f1'] * 100:>5.1f}%  {m['support']:>6}"
        )
    lines += ["", "Confusion matrix (rows = real class, columns = predicted class)", ""]
    header = " " * (width + 2) + "  ".join(f"{i:>4}" for i in range(len(classes)))
    lines.append(header)
    for i, t in enumerate(classes):
        counts = "  ".join(f"{metrics['confusion'][t][p]:>4}" for p in classes)
        lines.append(f"{i}: {t:<{width - 1}}{counts}")
    lines += ["", "Column numbers match the row numbers above."]
    return "\n".join(lines)


def predict_labels(model, images):
    """Run the model on each image and return the predicted class names."""
    labels = []
    for path, _true in images:
        result = model.predict(source=str(path), verbose=False)[0]
        labels.append(result.names[int(result.probs.top1)])
    return labels


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default="dataset", help="Split dataset folder (needs a test/ subfolder)")
    parser.add_argument("--model", default="ai_models/road_damage_model.pt")
    parser.add_argument("--out", default="ai_models/evaluation_report.txt")
    args = parser.parse_args(argv)

    test_dir = Path(args.data) / "test"
    model_path = Path(args.model)
    if not test_dir.is_dir():
        print(f"No test folder at {test_dir}. Run scripts/split_dataset.py first.")
        return 1
    if not model_path.is_file():
        print(f"No model at {model_path}. Run scripts/train_classifier.py first.")
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics is not installed. Run: python -m pip install -r requirements-ai.txt")
        return 1

    images = collect_test_images(test_dir)
    if not images:
        print(f"No images found under {test_dir}.")
        return 1

    print(f"Testing {len(images)} images...")
    model = YOLO(str(model_path))
    predicted = predict_labels(model, images)
    metrics = compute_metrics([true for _p, true in images], predicted)
    report = format_report(metrics)

    print()
    print(report)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"\nSaved to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())