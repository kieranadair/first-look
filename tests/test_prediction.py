"""Fixed source memberships and training-only model preparation, without live services."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from firstlook.prediction import predict_structure
from firstlook.providers import Settings
from firstlook.types import Dataset, Field, Meaning


def dataset():
    rng = np.random.default_rng(43)
    x = rng.normal(size=800)
    y = 2 * x + rng.normal(size=800)
    frame = pd.DataFrame(
        {
            "x": x,
            "copy": y,
            "target": y,
            "category": np.where(x > 0, "A", "B"),
            "group": np.arange(800) // 10,
            "time": pd.Timestamp("2025-01-01") + pd.to_timedelta(np.arange(800) // 2, unit="D"),
        }
    )
    fields = [
        Field("x", "Quantity", "number"),
        Field("copy", "Target copy", "number"),
        Field("target", "Outcome", "number"),
        Field("category", "Segment", "category"),
        Field("group", "Customer ID", "identifier"),
        Field("time", "Date", "time"),
    ]
    return Dataset("numbers.csv", "source", frame, fields)


def test_training_only_screens_fixed_protocols_and_local_references():
    ds = dataset()
    first = predict_structure(ds, "target", ["x", "copy", "category"])
    assert "copy" in first["excluded"] and len(first["models"]) == 2
    assert not set(first["train_ids"]) & set(first["test_ids"])
    assert set(first["train_ids"] + first["test_ids"]) == set(range(800))
    altered = deepcopy(ds)
    altered.frame.loc[first["test_ids"], "target"] += 500
    altered.frame.loc[first["test_ids"], "x"] = 1000
    second = predict_structure(altered, "target", ["x", "copy", "category"])
    assert first["train_ids"] == second["train_ids"] and first["test_ids"] == second["test_ids"]
    assert first["preprocessing"] == second["preprocessing"] and first["excluded"] == second["excluded"]
    group = predict_structure(ds, "target", ["x", "category"], "group", "group")
    assert not set(ds.frame.loc[group["train_ids"], "group"]) & set(ds.frame.loc[group["test_ids"], "group"])
    temporal = predict_structure(ds, "target", ["x", "category"], "time", "time")
    assert (
        ds.frame.loc[temporal["train_ids"], "time"].max() < ds.frame.loc[temporal["test_ids"], "time"].min()
    )
    with pytest.raises(ValueError, match="declared target entity"):
        predict_structure(ds, "target", ["x"], meanings={"target": Meaning(entity="group")})
    classification = predict_structure(ds, "category", ["x"])
    assert classification["task"] == "classification" and all(
        m["metric"] == "Balanced accuracy" for m in classification["models"]
    )
    with pytest.raises(ValueError, match="No predictors"):
        predict_structure(ds, "target", ["copy"])


def test_hosted_boundary_has_only_training_labels_and_rejects_misaligned_outputs():
    ds = dataset()
    calls = []

    class Model:
        def __init__(self, **_):
            self.value = None

        def submit_fit(self, x, y):
            calls.append(("fit", x.copy(), y.copy()))
            self.value = float(np.mean(y))

        def wait_for_fit(self):
            pass

        def submit_predict(self, x, **_):
            calls.append(("predict", x.copy()))
            self.count = len(x)

        def wait_for_predict(self):
            return np.repeat(self.value, self.count)

    settings = Settings(tabpfn_token="controlled-key")
    result = predict_structure(
        ds, "target", ["x", "category"], settings=settings, hosted=True, hosted_factory=Model
    )
    assert len(result["models"]) == 3 and [c[0] for c in calls] == ["fit", "predict"]
    assert np.array_equal(calls[0][2], ds.frame.loc[result["train_ids"], "target"].to_numpy())
    assert len(calls[1]) == 2 and len(calls[1][1]) == len(result["test_ids"])
    assert [r["row"] for r in result["models"][-1]["predictions"]] == result["test_ids"]

    class Misaligned(Model):
        def wait_for_predict(self):
            return np.array([1.0])

    rejected = predict_structure(
        ds, "target", ["x"], settings=settings, hosted=True, hosted_factory=Misaligned
    )
    assert len(rejected["models"]) == 2 and any("align" in w for w in rejected["warnings"])

    class Failed(Model):
        def wait_for_predict(self):
            raise ValueError("controlled-key raw private payload")

    failed = predict_structure(ds, "target", ["x"], settings=settings, hosted=True, hosted_factory=Failed)
    assert len(failed["models"]) == 2 and "controlled-key" not in str(failed)
