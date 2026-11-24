import threading
import time

import numpy as np
import pandas as pd
import pytest

from firstlook.config import Settings, configured
from firstlook.examples import load_example
from firstlook.ingest import from_frame
from firstlook.jobs import JobManager
from firstlook.modeling import make_split, predictor_policy, run_model
from firstlook.providers.tabpfn import TabPFNProvider


def test_target_components_and_copies_excluded():
    rng = np.random.default_rng(3)
    a = rng.uniform(size=300)
    b = rng.uniform(size=300)
    ds = from_frame(
        pd.DataFrame({"target": a + b, "copy": a + b, "a": a, "b": b, "signal": rng.normal(size=300)}),
        "leakage",
    )
    predictors, excluded = predictor_policy(ds, "f000", ds.frame)
    assert "f001" not in predictors and "f002" not in predictors and "f003" not in predictors
    assert set(excluded) >= {"f001", "f002", "f003"}


@pytest.mark.parametrize("split", ["random", "group", "time"])
def test_split_memberships(split):
    df = pd.DataFrame(
        {
            "y": np.arange(300),
            "group": np.repeat(list("ABCDEF"), 50),
            "date": pd.date_range("2024-01-01", periods=300),
        }
    )
    field = {"random": None, "group": "group", "time": "date"}[split]
    a, b = make_split(df, "y", "regression", split, field)
    assert set(a).isdisjoint(b)
    assert len(a) + len(b) == 300
    if split == "group":
        assert set(df.loc[a, "group"]).isdisjoint(df.loc[b, "group"])
    if split == "time":
        assert df.loc[a, "date"].max() < df.loc[b, "date"].min()


def test_baseline_is_real_and_held_out():
    ds = load_example("nonlinear")
    run = run_model(ds, ds.context(), "f003")
    assert run.provider == "Gradient boosting"
    assert "TabPFN" not in run.metrics
    assert run.metrics["Gradient boosting"]["R²"] > 0.8
    assert set(run.train_ids).isdisjoint(run.test_ids)
    assert [r["row_id"] for r in run.predictions] == run.test_ids
    assert run.parameters["preprocessing"] == "train-only"
    assert any("TabPFN was not run" in s for s in run.warnings)


def test_hosted_submission_contract_and_no_repeated_fit():
    calls = []

    class Remote:
        def __init__(self, **kwargs):
            pass

        def submit_fit(self, x, y):
            calls.append("submit_fit")
            self.mean = float(np.mean(y))

        def wait_for_fit(self):
            calls.append("wait_fit")

        def save_model(self):
            return {"model_id": "controlled-test-job"}

        def submit_predict(self, x):
            calls.append("submit_predict")
            self.n = len(x)

        def wait_for_predict(self):
            calls.append("wait_predict")
            return np.full(self.n, self.mean)

    ds = load_example("nonlinear")
    p = TabPFNProvider(Settings(tabpfn_token="controlled-test-token"), factory=Remote)
    run = run_model(ds, ds.context(), "f003", provider=p)
    assert run.provider == "TabPFN" and len(run.predictions) == len(run.test_ids)
    assert calls == ["submit_fit", "wait_fit", "submit_predict", "wait_predict"]


def test_invalid_predictions_preserve_baselines():
    class Bad:
        def predict(self, *args):
            return np.array([np.nan]), {}, {}

    ds = load_example("nonlinear")
    run = run_model(ds, ds.context(), "f003", provider=Bad())
    assert run.provider == "Gradient boosting" and any("align" in w for w in run.warnings)


@pytest.mark.parametrize("value", ["", "REPLACE_WITH_KEY", "<your-key>", "placeholder"])
def test_no_placeholder_is_configured(value):
    assert not configured(value)
    assert not Settings(openai_api_key=value).available("terra")


def test_offline_mode_overrides_credentials():
    assert not Settings(openai_api_key="real-looking-key", provider_mode="offline").available("terra")


def test_owned_jobs_deduplicate_and_cancel():
    manager = JobManager(capacity=1)
    ready = threading.Event()
    calls = []

    def work(progress, cancelled):
        calls.append(1)
        ready.wait(2)
        return "done"

    jid = manager.submit("owner", "context", "task", work)
    assert manager.submit("owner", "context", "task", work) == jid
    assert manager.get("other", jid) is None
    with pytest.raises(ValueError):
        manager.submit("other", "context", "task", work)
    manager.cancel("owner", jid)
    ready.set()
    for _ in range(100):
        if manager.get("owner", jid).state == "cancelled":
            break
        time.sleep(0.01)
    assert manager.get("owner", jid).state == "cancelled"
    assert calls == [1]


def test_classification_metrics_and_heldout_error_diagnostics():
    from firstlook.discovery import discover
    from firstlook.modeling import diagnostic_findings
    from firstlook.visualization.compiler import compile_chart

    ds = load_example("penguins")
    run = run_model(ds, ds.context(), "f000")
    assert run.task == "classification" and "Balanced accuracy" in run.metrics["Gradient boosting"]
    inv = discover(ds)
    inv.model_runs.append(run)
    diagnostic_findings(ds, inv, run)
    diagnostics = [f for f in inv.findings if f.family == "model"]
    assert any(f.chart.template == "heatmap" for f in diagnostics)
    for f in diagnostics:
        compiled = compile_chart(f.chart, inv.results[f.result_id])
        assert set(i for ids in compiled.row_map.values() for i in ids) <= set(run.test_ids)


def test_residual_bins_are_defined_on_training_and_evaluated_on_holdout():
    from firstlook.discovery import discover
    from firstlook.model_checks import residual_spread

    ds = load_example("nonlinear")
    run = run_model(ds, ds.context(), "f003")
    inv = discover(ds)
    inv.model_runs.append(run)
    result, chart, summary = residual_spread(ds, inv)
    assert result.plan.params["model_run"] == run.id
    assert {i for r in result.records for i in r["row_ids"]} <= set(run.test_ids)
    assert all(r["n"] >= 20 for r in result.records)
    assert "not a calibrated uncertainty" in summary


def test_hosted_class_order_mismatch_keeps_local_baselines():
    class WrongOrder:
        def predict(self, task, xtrain, ytrain, xtest, progress):
            return np.full((len(xtest), 3), 1 / 3), {"classes": [2, 1, 0]}, {}

    ds = load_example("penguins")
    run = run_model(ds, ds.context(), "f000", provider=WrongOrder())
    assert run.provider == "Gradient boosting" and "TabPFN" not in run.metrics
    assert any("class order" in warning for warning in run.warnings)
