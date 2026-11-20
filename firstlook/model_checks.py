"""Descriptive shape/error checks; no unrequested models or inferential claims."""

from typing import Any
import numpy as np
import pandas as pd

from firstlook.contracts import ChartSpec, ResultArtifact, digest
from firstlook.discovery import plan_for


def residual_spread(dataset, inv):
    if not inv.model_runs or inv.model_runs[-1].task != "regression":
        raise ValueError("This check needs a held-out regression run.")
    run = inv.model_runs[-1]
    predictor = next((f for f in run.predictors if dataset.field(f).role.value == "measure"), None)
    if predictor is None:
        raise ValueError("This check needs a numerical predictor.")
    train = dataset.frame.loc[run.train_ids, predictor].dropna()
    edges = sorted(set(train.quantile([0, 0.2, 0.4, 0.6, 0.8, 1]).tolist()))
    if len(edges) < 3:
        raise ValueError("Too few distinct training values.")
    edges[0], edges[-1] = -np.inf, np.inf
    predictions = pd.DataFrame(run.predictions).set_index("row_id")
    predictions["bin"] = pd.cut(dataset.frame.loc[predictions.index, predictor], bins=edges)
    records: list[dict[str, Any]] = []
    for label, group in predictions.groupby("bin", observed=True):
        if len(group) >= 20:
            records.append(
                {
                    "label": str(label),
                    "value": float(group.error.mean()),
                    "median": float(group.error.median()),
                    "n": len(group),
                    "row_ids": group.index.tolist(),
                }
            )
    if len(records) < 2:
        raise ValueError("Two training-defined bins need at least 20 held-out observations each.")
    plan = plan_for(
        inv.context,
        "model_diagnostic",
        [predictor, run.target],
        "Held-out error by predictor bin",
        {"model_run": run.id},
    )
    result = ResultArtifact(
        id=plan.id,
        plan=plan,
        records=records,
        support=sum(r["n"] for r in records),
        metadata={"bin_boundaries": [str(e) for e in edges], "model_run": run.id},
    )
    summary = "Mean absolute errors vary across training-defined predictor bins on held-out rows. This is an observed diagnostic, not a calibrated uncertainty guarantee."
    chart = ChartSpec(
        id=digest([result.id, "bar"]),
        result_id=result.id,
        context=inv.context.id,
        template="bar",
        x_label="Mean absolute error",
        y_label=dataset.label(predictor) + " bin",
        zero_baseline=True,
        alt=summary,
        rules=["MODEL-01", "SOURCE-01"],
    )
    return result, chart, summary
