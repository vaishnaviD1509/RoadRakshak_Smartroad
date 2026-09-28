"""Tests for scripts/split_dataset.py using a small synthetic dataset,
so this doesn't depend on the real (large, external) road-issue dataset
being present."""
import sys
import os
from pathlib import Path
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.split_dataset import split_dataset, slugify


def _make_fake_source(base: Path):
    categories = {"Pothole Issues": 10, "Damaged Road issues": 4}
    for category, count in categories.items():
        cat_dir = base / category
        cat_dir.mkdir(parents=True)
        for i in range(count):
            Image.new("RGB", (10, 10), color=(i, i, i)).save(cat_dir / f"img_{i}.jpg")
    return categories


def test_slugify():
    assert slugify("Pothole Issues") == "pothole_issues"
    assert slugify("Damaged Road issues") == "damaged_road_issues"


def test_split_counts_add_up_and_folders_are_created(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    categories = _make_fake_source(source)

    summary = split_dataset(source, output, train_ratio=0.8, val_ratio=0.1, test_ratio=0.1)

    for category, total in categories.items():
        counts = summary[category]
        assert counts["train"] + counts["val"] + counts["test"] == total

    # Output folders exist for each split/class combination that has images
    assert (output / "train" / "pothole_issues").is_dir()
    assert len(list((output / "train" / "pothole_issues").glob("*.jpg"))) == summary["Pothole Issues"]["train"]