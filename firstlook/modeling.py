"""Shared held-out evaluation, train-only preprocessing and actual hosted inference."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    balanced_accuracy_score,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from firstlook.contracts import AnalysisContext, ModelRun, Role, clean, digest
from firstlook.discovery import SEED, Investigation, plan_for
from firstlook.ingest import Dataset
from firstlook.providers.base import ProviderError


def eligible_targets(dataset: Dataset) -> list[str]:
    found = []
    for f in dataset.record.fields:
        s = dataset.frame[f.id].dropna()
        if f.excluded or len(s) < 200 or s.nunique() < 2:
            continue
        if f.role == Role.MEASURE or (
            f.role in {Role.CATEGORY, Role.BOOL, Role.ORDINAL}
            and 2 <= s.nunique() <= 20
            and s.value_counts().min() >= 20
        ):
            found.append(f.id)
    return found


def suggested_model_plan(dataset: Dataset, ctx: AnalysisContext) -> tuple[str, str, str | None] | None:
    """A visible, deterministic starting protocol; this is not an inferred scientific aim."""
    targets = eligible_targets(dataset)
    if not targets:
        return None
    preferred = {"y", "response", "outcome", "target", "cnt", "body_mass_g"}
    target = (
        ctx.focus
        if ctx.focus in targets
        else next((f for f in targets if dataset.label(f).lower() in preferred), targets[-1])
    )
    times = [
        f.id
        for f in dataset.record.fields
        if f.role == Role.TIME and not f.excluded and dataset.frame.loc[ctx.row_ids, f.id].nunique() >= 5
    ]
    return target, "time" if times else "random", times[0] if times else None


def predictor_policy(dataset: Dataset, target: str, frame: pd.DataFrame) -> tuple[list[str], dict]:
    allowed, excluded = [], {}
    for f in dataset.record.fields:
        if f.id == target:
            continue
        if f.excluded or f.role in {Role.ID, Role.TIME, Role.TEXT, Role.UNKNOWN}:
            excluded[f.id] = "Excluded role or user exclusion"
        elif frame[f.id].nunique() < 2:
            excluded[f.id] = "Constant or empty"
        elif frame[f.id].equals(frame[target]) or frame[f.id].astype(str).equals(frame[target].astype(str)):
            excluded[f.id] = "Exact target copy"
        else:
            allowed.append(f.id)
    numeric = [f for f in allowed if pd.api.types.is_numeric_dtype(frame[f])][:20]
    if pd.api.types.is_numeric_dtype(frame[target]):
        for a, b in combinations(numeric, 2):
            valid = frame[[a, b, target]].dropna()
            if len(valid) >= 30 and np.allclose(valid[a] + valid[b], valid[target], rtol=1e-9, atol=1e-9):
                excluded[a] = excluded[b] = "These recorded fields sum exactly to the target"
    return [f for f in allowed if f not in excluded], excluded


def make_split(
    frame: pd.DataFrame, target: str, task: str, split: str, split_field: str | None = None
) -> tuple[list[int], list[int]]:
    if split == "group":
        if split_field not in frame.columns:
            raise ValueError("Choose a grouping field.")
        if frame[split_field].isna().any():
            raise ValueError("Group holdout requires recorded groups on every modeled row.")
        if frame[split_field].nunique() < 3:
            raise ValueError("Group holdout requires at least three recorded groups.")
        train, test = next(
            GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED).split(
                frame, groups=frame[split_field]
            )
        )
        return frame.index[train].tolist(), frame.index[test].tolist()
    if split == "time":
        if split_field not in frame.columns or not pd.api.types.is_datetime64_any_dtype(frame[split_field]):
            raise ValueError("Time holdout requires a parsed timestamp.")
        ordered = frame.dropna(subset=[split_field]).sort_values(split_field)
        boundary = ordered[split_field].iloc[int(len(ordered) * 0.7)]
        return (
            ordered.index[ordered[split_field] < boundary].tolist(),
            ordered.index[ordered[split_field] >= boundary].tolist(),
        )
    if split != "random":
        raise ValueError("Unknown split policy.")
    train, test = train_test_split(
        frame.index,
        test_size=0.3,
        random_state=SEED,
        stratify=frame[target].astype(str) if task == "classification" else None,
    )
    return sorted(train.tolist()), sorted(test.tolist())


def _preprocessor(x: pd.DataFrame) -> ColumnTransformer:
    num = list(x.select_dtypes(include="number").columns)
    cat = [f for f in x.columns if f not in num]
    return ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                num,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                        (
                            "encode",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                max_categories=20,
                                sparse_output=False,
                                dtype=np.float32,
                            ),
                        ),
                    ]
                ),
                cat,
            ),
        ]
    )


def metrics_for(task: str, actual, predicted, probabilities=None) -> dict[str, float]:
    if task == "regression":
        return {
            "MAE": float(mean_absolute_error(actual, predicted)),
            "RMSE": float(np.sqrt(mean_squared_error(actual, predicted))),
            "R²": float(r2_score(actual, predicted)),
        }
    result = {
        "Balanced accuracy": float(balanced_accuracy_score(actual, predicted)),
        "Macro F1": float(f1_score(actual, predicted, average="macro", zero_division=0)),
    }
    if probabilities is not None:
        result["Log loss"] = float(
            log_loss(actual, probabilities, labels=list(range(probabilities.shape[1])))
        )
    return result


def run_model(
    dataset: Dataset,
    ctx: AnalysisContext,
    target: str,
    split: str = "random",
    split_field: str | None = None,
    requested: list[str] | None = None,
    provider=None,
    progress: Callable[[str], None] = lambda _: None,
    cancelled: Callable[[], bool] = lambda: False,
) -> ModelRun:
    if target not in eligible_targets(dataset):
        raise ValueError("Choose an eligible measure or supported categorical focus with 200 labeled rows.")
    data = dataset.frame.loc[ctx.row_ids].dropna(subset=[target])
    task = "regression" if dataset.field(target).role == Role.MEASURE else "classification"
    if len(data) > 10_000:
        if split == "time":
            data = data.sort_values(split_field).iloc[np.linspace(0, len(data) - 1, 10_000).astype(int)]
        elif split == "group":
            parts, total = [], 0
            for _, part in data.groupby(split_field, sort=True):
                if total + len(part) <= 10_000:
                    parts.append(part)
                    total += len(part)
            if not parts:
                raise ValueError("No whole group fits the model budget.")
            data = pd.concat(parts)
        else:
            data = data.sample(10_000, random_state=SEED).sort_index()
    if len(data) < 200:
        raise ValueError("The selected context needs 200 labeled rows.")
    if data[target].nunique() < 2:
        raise ValueError("The selected target is constant in this analytical context.")
    predictors, excluded = predictor_policy(dataset, target, data)
    if split_field in predictors:
        predictors.remove(split_field)
        excluded[split_field] = "Split field excluded from predictors"
    if requested is not None:
        if not set(requested).issubset(predictors):
            raise ValueError("The requested predictors include a forbidden or unknown field.")
        predictors = list(requested)
    predictors = predictors[:40]
    if not predictors:
        raise ValueError("No eligible predictors remain.")
    train_ids, test_ids = make_split(data, target, task, split, split_field)
    if min(len(train_ids), len(test_ids)) < 20:
        raise ValueError("Both sides of the split require 20 observations.")
    if set(train_ids) & set(test_ids):
        raise ValueError("Train and test membership overlap.")
    xtrain, xtest = data.loc[train_ids, predictors].copy(), data.loc[test_ids, predictors].copy()
    for f in predictors:
        if dataset.field(f).role != Role.MEASURE:
            xtrain[f] = xtrain[f].astype(str).astype(object).where(xtrain[f].notna(), np.nan)
            xtest[f] = xtest[f].astype(str).astype(object).where(xtest[f].notna(), np.nan)
    ytrain, ytest = data.loc[train_ids, target], data.loc[test_ids, target]
    encoder = LabelEncoder()
    if task == "classification":
        if set(ytrain.astype(str)) != set(ytest.astype(str)):
            raise ValueError("Every evaluated class must be represented on both sides of the split.")
        if ytrain.astype(str).value_counts().min() < 5 or ytest.astype(str).value_counts().min() < 5:
            raise ValueError("Every evaluated class requires at least five train and test observations.")
        encoder = LabelEncoder().fit(ytrain.astype(str))
        if set(ytest.astype(str)) - set(encoder.classes_):
            raise ValueError("The test set contains a class absent from training.")
        ytrain, ytest = encoder.transform(ytrain.astype(str)), encoder.transform(ytest.astype(str))
    constructors = (
        [
            ("Dummy", DummyRegressor()),
            ("Linear", Ridge(alpha=1)),
            (
                "Gradient boosting",
                HistGradientBoostingRegressor(max_iter=80, max_leaf_nodes=15, random_state=SEED),
            ),
        ]
        if task == "regression"
        else [
            ("Dummy", DummyClassifier(strategy="prior")),
            ("Linear", LogisticRegression(max_iter=500)),
            (
                "Gradient boosting",
                HistGradientBoostingClassifier(max_iter=80, max_leaf_nodes=15, random_state=SEED),
            ),
        ]
    )
    scores, outputs = {}, {}
    with threadpool_limits(limits=1):
        for name, estimator in constructors:
            if cancelled():
                raise ValueError("The model run was cancelled.")
            progress("Evaluating " + name.lower() + " baseline")
            model = Pipeline([("preprocess", _preprocessor(xtrain)), ("estimator", estimator)])
            model.fit(xtrain, ytrain)
            pred = model.predict(xtest)
            probs = model.predict_proba(xtest) if task == "classification" else None
            scores[name], outputs[name] = metrics_for(task, ytest, pred, probs), (pred, probs)
    warnings = [f"{len(data):,} labeled rows; fixed 70/30 protocol. Predictability is not causality."]
    if split == "random" and ctx.assumption != "exchangeable":
        warnings.append("Row holdout is diagnostic: independence and future generalization are unverified.")
    record, accepted_record, active = {}, {}, "Gradient boosting"
    if provider is not None and not cancelled():
        try:
            pred, record, accepted_record = provider.predict(task, xtrain, ytrain, xtest, progress)
            pred = np.asarray(pred)
            if task == "classification":
                if not isinstance(record, dict) or record.get("classes") != list(
                    range(len(encoder.classes_))
                ):
                    raise ValueError("Hosted class order does not match the recorded training label order.")
                if pred.shape != (len(test_ids), len(encoder.classes_)) or not np.isfinite(pred).all():
                    raise ValueError("Hosted class probabilities have the wrong shape or nonfinite values.")
                if (pred < 0).any() or not np.allclose(pred.sum(axis=1), 1, atol=0.01):
                    raise ValueError("Hosted probabilities are invalid.")
                outputs["TabPFN"] = (np.argmax(pred, axis=1), pred)
            else:
                pred = pred.reshape(-1)
                if len(pred) != len(test_ids) or not np.isfinite(pred).all():
                    raise ValueError("Hosted predictions do not align to held-out rows.")
                outputs["TabPFN"] = (pred, None)
            scores["TabPFN"] = metrics_for(task, ytest, *outputs["TabPFN"])
            active = "TabPFN"
        except (ProviderError, ValueError, TypeError) as exc:
            warnings.append(str(exc))
    elif provider is None:
        warnings.append("TabPFN was not run. Displayed diagnostics use the named local baseline.")
    pred, probs = outputs[active]
    rows = []
    for i, rowid in enumerate(test_ids):
        actual = (
            float(np.asarray(ytest)[i])
            if task == "regression"
            else str(encoder.inverse_transform([np.asarray(ytest)[i]])[0])
        )
        prediction = float(pred[i]) if task == "regression" else str(encoder.inverse_transform([pred[i]])[0])
        row = {
            "row_id": int(rowid),
            "actual": actual,
            "predicted": prediction,
            "error": float(abs(float(actual) - float(prediction)))
            if task == "regression"
            else float(actual != prediction),
        }
        if task == "regression":
            row["residual"] = float(actual) - float(prediction)
        elif probs is not None:
            row["true_class_probability"] = float(probs[i, np.asarray(ytest)[i]])
        rows.append(clean(row))
    return ModelRun(
        id=digest([ctx.id, target, predictors, split, split_field, active, record]),
        context=ctx.id,
        target=target,
        predictors=predictors,
        task=task,
        split=split,
        train_ids=train_ids,
        test_ids=test_ids,
        metrics=clean(scores),
        predictions=rows,
        warnings=warnings,
        excluded=excluded,
        provider=active,
        model_record=clean(record),
        parameters={
            "seed": SEED,
            "split_field": split_field,
            "preprocessing": "train-only",
            "baseline_max_iter": 80,
            "encoded_max_categories": 20,
            "class_order": clean(encoder.classes_) if task == "classification" else [],
            "accepted_hosted_fit": clean(accepted_record),
        },
    )


def diagnostic_findings(dataset: Dataset, inv: Investigation, run: ModelRun) -> None:
    from firstlook.contracts import ChartSpec, Finding, ResultArtifact

    inv.findings = [f for f in inv.findings if f.family != "model"]
    diagnostics = []
    specs: list[Any] = []
    if run.task == "regression":
        specs.append(
            (
                "Observed versus predicted",
                "scatter",
                [{"x": r["actual"], "y": r["predicted"], "row_id": r["row_id"]} for r in run.predictions],
                "Observed " + dataset.label(run.target),
                "Predicted " + dataset.label(run.target),
            )
        )
        specs.append(
            (
                "Where do held-out errors concentrate?",
                "scatter",
                [{"x": r["predicted"], "y": r["residual"], "row_id": r["row_id"]} for r in run.predictions],
                "Predicted value",
                "Observed − predicted",
            )
        )
    else:
        table = pd.DataFrame(run.predictions)
        records = []
        labels = sorted(set(table.actual) | set(table.predicted))
        for actual in labels:
            for predicted in labels:
                group = table[(table.actual == actual) & (table.predicted == predicted)]
                records.append(
                    {"x": actual, "y": predicted, "value": len(group), "row_ids": group["row_id"].tolist()}
                )
        specs.append(("Which classes are confused?", "heatmap", records, "Observed class", "Predicted class"))
    from firstlook.semantics import dimensions

    table = pd.DataFrame(run.predictions).set_index("row_id")
    for group_field in dimensions(dataset):
        if group_field == run.target or not 2 <= dataset.frame.loc[run.test_ids, group_field].nunique() <= 8:
            continue
        table["group"] = dataset.frame.loc[table.index, group_field].astype(str)
        groups = [
            {
                "label": str(label),
                "value": float(group.error.mean()),
                "n": len(group),
                "row_ids": group.index.tolist(),
            }
            for label, group in table.groupby("group")
            if len(group) >= 20
        ]
        if len(groups) >= 2:
            specs.append(
                (
                    "How do held-out errors differ by " + dataset.label(group_field) + "?",
                    "bar",
                    groups,
                    "Mean absolute error" if run.task == "regression" else "Error proportion",
                    dataset.label(group_field),
                )
            )
            break
    for title, template, rows, x, y in specs:
        plan = plan_for(
            inv.context, "model_diagnostic", [run.target], title, {"model_run": run.id, "diagnostic": title}
        )
        result = ResultArtifact(
            id=plan.id,
            plan=plan,
            records=rows,
            support=len(run.test_ids),
            metrics=run.metrics[run.provider],
            metadata={"model_run": run.id, "proportion": template == "bar" and run.task == "classification"},
        )
        finding = Finding(
            id=plan.id,
            title=title,
            observation=f"{run.provider} diagnostics on {len(run.test_ids):,} held-out rows.",
            result_id=result.id,
            family="model",
            score=1,
            claim_type="model-derived",
            chart=ChartSpec(
                id=digest([result.id, template]),
                result_id=result.id,
                context=inv.context.id,
                template=template,
                x_label=x,
                y_label=y,
                alt=f"{run.provider}: {title}",
                rules=["MODEL-01", "SOURCE-01"],
                zero_baseline=template == "bar",
            ),
            limitations=run.warnings,
        )
        inv.results[result.id] = result
        diagnostics.append(finding)
    inv.findings = diagnostics + inv.findings[: max(0, 12 - len(diagnostics))]
