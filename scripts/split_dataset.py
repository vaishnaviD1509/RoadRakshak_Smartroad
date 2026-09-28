"""Split a folder-per-category image dataset into train/val/test sets
for training a YOLOv8 classification model.

Usage:
    python scripts/split_dataset.py \
        --source "/path/to/Road Issues" \
        --output dataset \
        --train 0.8 --val 0.1 --test 0.1

Input layout expected (what the provided road-rakshak-dataset.zip has):
    Road Issues/
        Pothole Issues/*.jpg
        Damaged Road issues/*.jpg
        Mixed Issues/*.jpg
        Illegal Parking Issues/*.jpg
        Broken Road Sign Issues/*.jpg

Output layout produced (what ultralytics YOLO classification expects):
    dataset/
        train/<class>/*.jpg
        val/<class>/*.jpg
        test/<class>/*.jpg

Class folder names are slugified (lowercase, spaces -> underscores) so
they're safe to use as YOLO class names.
"""
import argparse
import random
import re
import shutil
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def slugify(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def split_dataset(source: Path, output: Path, train_ratio: float, val_ratio: float, test_ratio: float, seed: int = 42):
    assert abs((train_ratio + val_ratio + test_ratio) - 1.0) < 1e-6, "Ratios must sum to 1.0"

    random.seed(seed)
    class_dirs = [d for d in source.iterdir() if d.is_dir()]
    if not class_dirs:
        raise SystemExit(f"No category subfolders found under {source}")

    summary = {}
    for class_dir in sorted(class_dirs):
        class_slug = slugify(class_dir.name)
        images = [
            p for p in class_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ]
        random.shuffle(images)

        n = len(images)
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        # remainder goes to test, so counts always add up to n exactly
        splits = {
            "train": images[:n_train],
            "val": images[n_train:n_train + n_val],
            "test": images[n_train + n_val:],
        }

        for split_name, split_images in splits.items():
            dest_dir = output / split_name / class_slug
            dest_dir.mkdir(parents=True, exist_ok=True)
            for img_path in split_images:
                shutil.copy2(img_path, dest_dir / img_path.name)

        summary[class_dir.name] = {k: len(v) for k, v in splits.items()}

    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="Path to the 'Road Issues' folder (one subfolder per category)")
    parser.add_argument("--output", default="dataset", help="Where to write train/val/test (default: ./dataset)")
    parser.add_argument("--train", type=float, default=0.8)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--test", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)

    if not source.is_dir():
        raise SystemExit(f"Source folder not found: {source}")

    summary = split_dataset(source, output, args.train, args.val, args.test, args.seed)

    print(f"\nDataset split written to: {output.resolve()}\n")
    print(f"{'Category':30s} {'train':>7s} {'val':>7s} {'test':>7s}")
    print("-" * 55)
    totals = {"train": 0, "val": 0, "test": 0}
    for category, counts in summary.items():
        print(f"{category:30s} {counts['train']:>7d} {counts['val']:>7d} {counts['test']:>7d}")
        for k in totals:
            totals[k] += counts[k]
    print("-" * 55)
    print(f"{'TOTAL':30s} {totals['train']:>7d} {totals['val']:>7d} {totals['test']:>7d}")


if __name__ == "__main__":
    main()