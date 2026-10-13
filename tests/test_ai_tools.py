"""The AI helper scripts: evaluation maths and the one-photo predictor."""
import pytest
from PIL import Image

from scripts.evaluate_model import collect_test_images, compute_metrics, format_report
from scripts import evaluate_model, predict_image


def test_compute_metrics_known_example():
    y_true = ["a", "a", "a", "b", "b", "c"]
    y_pred = ["a", "a", "b", "b", "b", "a"]
    m = compute_metrics(y_true, y_pred)

    assert m["total"] == 6 and m["correct"] == 4
    assert m["accuracy"] == pytest.approx(4 / 6)
    assert m["confusion"]["a"] == {"a": 2, "b": 1, "c": 0}
    assert m["confusion"]["c"]["a"] == 1
    assert m["per_class"]["a"]["precision"] == pytest.approx(2 / 3)
    assert m["per_class"]["a"]["recall"] == pytest.approx(2 / 3)
    assert m["per_class"]["b"]["precision"] == pytest.approx(2 / 3)
    assert m["per_class"]["b"]["recall"] == pytest.approx(1.0)
    # class c was never predicted correctly: scores must be 0, not a crash
    assert m["per_class"]["c"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 1}


def test_compute_metrics_includes_labels_the_model_invented():
    m = compute_metrics(["a", "a"], ["a", "zzz"])
    assert "zzz" in m["classes"]
    assert m["per_class"]["zzz"]["support"] == 0
    assert m["accuracy"] == pytest.approx(0.5)


def test_compute_metrics_empty_and_mismatched():
    assert compute_metrics([], [])["accuracy"] == 0.0
    with pytest.raises(ValueError):
        compute_metrics(["a"], [])


def test_format_report_shows_accuracy_and_every_class():
    m = compute_metrics(["pothole", "crack"], ["pothole", "pothole"])
    text = format_report(m)
    assert "Accuracy      : 50.0%" in text
    assert "pothole" in text and "crack" in text
    assert "Confusion matrix" in text


def test_collect_test_images_reads_class_folders(tmp_path):
    for cls, names in {"pothole_issues": ["1.jpg", "2.png"], "mixed_issues": ["3.jpeg"]}.items():
        (tmp_path / cls).mkdir()
        for n in names:
            Image.new("RGB", (8, 8)).save(tmp_path / cls / n)
    (tmp_path / "pothole_issues" / "notes.txt").write_text("ignore me")

    items = collect_test_images(tmp_path)
    assert sorted((p.name, c) for p, c in items) == [
        ("1.jpg", "pothole_issues"), ("2.png", "pothole_issues"), ("3.jpeg", "mixed_issues"),
    ]


def test_evaluate_main_explains_missing_pieces(tmp_path, capsys):
    assert evaluate_model.main(["--data", str(tmp_path), "--model", str(tmp_path / "m.pt")]) == 1
    assert "split_dataset" in capsys.readouterr().out

    (tmp_path / "test").mkdir()
    assert evaluate_model.main(["--data", str(tmp_path), "--model", str(tmp_path / "m.pt")]) == 1
    assert "train_classifier" in capsys.readouterr().out


def test_predict_image_without_a_model_says_unavailable(tmp_path, capsys):
    photo = tmp_path / "road.jpg"
    Image.new("RGB", (40, 40), color=(100, 120, 90)).save(photo)

    code = predict_image.main([str(photo), "--model", str(tmp_path / "missing.pt")])
    out = capsys.readouterr().out
    assert code == 0
    assert "Prediction : -" in out
    assert "unavailable" in out.lower()


def test_predict_image_missing_file(tmp_path, capsys):
    assert predict_image.main([str(tmp_path / "nope.jpg")]) == 2
    assert "not found" in capsys.readouterr().out.lower()


def test_predict_labels_reads_the_top_class_name(tmp_path):
    """predict_labels only needs result.names and result.probs.top1, so a
    small stand-in model is enough to check it picks the right class name."""
    class FakeProbs:
        top1 = 1

    class FakeResult:
        names = {0: "mixed_issues", 1: "pothole_issues"}
        probs = FakeProbs()

    class FakeModel:
        def predict(self, source, verbose=False):
            return [FakeResult()]

    images = [(tmp_path / "a.jpg", "pothole_issues"), (tmp_path / "b.jpg", "mixed_issues")]
    assert evaluate_model.predict_labels(FakeModel(), images) == ["pothole_issues", "pothole_issues"]