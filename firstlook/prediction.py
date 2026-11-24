"""One explicit retrospective diagnostic, with local references and a fixed holdout."""

from __future__ import annotations

import os
import re
from itertools import combinations
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd

from firstlook.providers import safe_error
from firstlook.types import clean, digest

SEED = 20261124
_AUTH_LOCK = Lock()


class PredictionOutputError(ValueError):
    """A locally detected output-shape problem, safe to explain to the analyst."""


def _memberships(data, split, field):
    rng = np.random.default_rng(SEED)
    if split == "random":
        ids = rng.permutation(data.index.to_numpy())
        boundary = int(0.75 * len(ids))
        return list(map(int, ids[:boundary])), list(map(int, ids[boundary:]))
    if field not in data or data[field].isna().any():
        raise ValueError("Choose a complete recorded field for this holdout.")
    if split == "group":
        groups = data[field].astype(str)
        levels = groups.unique()
        if not 3 <= len(levels) < len(data):
            raise ValueError("An unseen-group holdout needs at least three repeated groups.")
        chosen = set(rng.permutation(levels)[: max(1, int(0.25 * len(levels)))])
        test = groups.isin(chosen)
    elif split == "time":
        timestamps = pd.to_datetime(data[field], utc=True, errors="coerce")
        if timestamps.isna().any() or timestamps.nunique() < 3:
            raise ValueError(
                "A chronological holdout needs complete parsed timestamps and at least three dates."
            )
        boundary = timestamps.sort_values().iloc[int(0.75 * len(data))]
        test = timestamps.ge(boundary)
    else:
        raise ValueError("Choose a row, group or chronological holdout.")
    return list(map(int, data.index[~test])), list(map(int, data.index[test]))


def _leakage(train, target, predictors, regression):
    excluded = {}
    for fid in predictors:
        pair = train[[fid, target]].dropna()
        if len(pair) >= max(20, int(0.8 * len(train))):
            equal = (
                np.allclose(pair[fid].astype(float), pair[target].astype(float), rtol=1e-10, atol=1e-10)
                if regression and pd.api.types.is_numeric_dtype(pair[fid])
                else pair[fid].astype(str).eq(pair[target].astype(str)).all()
            )
            if equal:
                excluded[fid] = "An exact copy of the target on training records"
    numeric = [f for f in predictors if f not in excluded and pd.api.types.is_numeric_dtype(train[f])][:12]
    if regression:
        for left, right in combinations(numeric, 2):
            pair = train[[left, right, target]].dropna()
            if len(pair) < max(20, int(0.8 * len(train))):
                continue
            a, b, actual = (pair[f].to_numpy(dtype=float) for f in [left, right, target])
            with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                alternatives = [a + b, a - b, b - a, a * b, np.divide(a, b), np.divide(b, a)]
            if any(
                np.isfinite(v).all() and np.allclose(v, actual, rtol=1e-10, atol=1e-10) for v in alternatives
            ):
                excluded[left] = excluded[right] = "An exact target component pair on training records"
    return excluded


def hosted_predict(task, train_x, train_y, test_x, settings, factory=None):
    """The hosted boundary deliberately has no held-out-label argument."""
    if settings is None or not settings.available("tabpfn"):
        raise ValueError("Hosted predictions are not configured. Local references remain available.")
    if train_x.shape[1] > 128:
        raise ValueError(
            "This utility limits hosted diagnostics to 128 encoded predictors. Select fewer fields."
        )
    try:
        from tabpfn_client.models import ClientOptions

        os.environ.setdefault("TABPFN_CLIENT_TIMEOUT", "45")
        os.environ.setdefault("TABPFN_CLIENT_ASYNC_POLL_TIMEOUT", "90")
        os.environ.setdefault("TABPFN_DISABLE_TELEMETRY", "1")
        if factory is None:
            import tabpfn_client

            with _AUTH_LOCK:
                tabpfn_client.set_access_token(settings.tabpfn_token)
            factory = (
                tabpfn_client.TabPFNRegressor if task == "regression" else tabpfn_client.TabPFNClassifier
            )
        model: Any = factory(
            model_path=settings.tabpfn_model_path, random_state=SEED, client_options=ClientOptions(timeout=45)
        )
        model.submit_fit(train_x, train_y)
        model.wait_for_fit()
        if task == "classification":
            model.submit_predict(test_x, output_type="probas")
        else:
            model.submit_predict(test_x)
        raw = np.asarray(model.wait_for_predict())
        if not np.issubdtype(raw.dtype, np.number) or not np.isfinite(raw).all():
            raise PredictionOutputError("Hosted predictions must be finite numerical values.")
        if task == "classification":
            classes = np.unique(train_y)
            if (
                raw.shape != (len(test_x), len(classes))
                or (raw < 0).any()
                or (raw > 1).any()
                or not np.allclose(raw.sum(axis=1), 1, atol=0.01)
            ):
                raise PredictionOutputError(
                    "Hosted class probabilities do not align with the holdout and training classes."
                )
            predictions = classes[np.argmax(raw, axis=1)]
        else:
            if raw.shape not in {(len(test_x),), (len(test_x), 1)}:
                raise PredictionOutputError("Hosted predictions do not align with the held-out records.")
            predictions = raw.reshape(-1)
        return predictions
    except PredictionOutputError:
        raise
    except Exception as exc:
        raise RuntimeError(safe_error("TabPFN", exc)) from exc


def predict_structure(
    ds,
    target,
    predictors,
    split="random",
    split_field=None,
    rows=None,
    settings=None,
    hosted=False,
    hosted_factory=None,
    meanings=None,
):
    """Diagnostic association only. Model performance does not establish a business definition."""
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.metrics import balanced_accuracy_score, mean_absolute_error
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from threadpoolctl import threadpool_limits

    field = ds.field(target)
    if (
        field.kind not in {"number", "category"}
        or re.search(
            r"(^|[ _])(lat|latitude|lon|longitude|angle|bearing|heading|direction)([ _]|$)", field.name, re.I
        )
        or field.unit.casefold() in {"degree", "degrees", "deg", "°"}
    ):
        raise ValueError(
            "Choose a scalar numerical or categorical target; identifiers, text, coordinates and circular quantities need another protocol."
        )
    regression = field.kind == "number"
    task = "regression" if regression else "classification"
    rows = list(ds.frame.index) if rows is None else list(rows)
    if len(rows) != len(set(rows)) or not set(rows) <= set(ds.frame.index):
        raise ValueError("Prediction membership must contain distinct original source records.")
    requested = list(dict.fromkeys(predictors))
    if (
        not requested
        or len(requested) > 40
        or not set(requested) <= {f.id for f in ds.fields}
        or target in requested
    ):
        raise ValueError("Select one to forty recorded predictors, separate from the target.")
    declared = (meanings or {}).get(target)
    entity = getattr(declared, "entity", None) if declared is not None else None
    if isinstance(declared, dict):
        entity = declared.get("entity")
    if entity and (split != "group" or split_field != entity):
        raise ValueError("The declared target entity requires an unseen-group holdout on that identifier.")
    excluded = {
        f: "Identifiers, free text and timestamps are not encoded as scalar predictors"
        for f in requested
        if ds.field(f).kind not in {"number", "category"}
    }
    frame = ds.frame.loc[rows].dropna(subset=[target]).copy()
    warnings = [
        "Retrospective structure diagnostic; this does not establish causality or future deployment performance."
    ]
    if len(frame) > 5000:
        if split == "group":
            if split_field not in frame or frame[split_field].isna().any():
                raise ValueError("Choose a complete group identifier.")
            sizes = frame.groupby(split_field, sort=True).size()
            kept, count = [], 0
            for key, size in sizes.items():
                if count + size <= 5000:
                    kept.append(key)
                    count += size
            frame = frame.loc[frame[split_field].isin(kept)]
        elif split == "time":
            if split_field not in frame:
                raise ValueError("Choose the recorded timestamp for the chronological holdout.")
            frame = frame.sort_values(split_field).tail(5000)
        else:
            frame = frame.sample(5000, random_state=SEED).sort_index()
        warnings.append(
            "The diagnostic is bounded to at most 5,000 labelled records; its memberships are recorded."
        )
    if len(frame) < 200:
        raise ValueError("This diagnostic needs at least 200 labelled records.")
    train_ids, test_ids = _memberships(frame, split, split_field)
    if len(train_ids) < 120 or len(test_ids) < 40 or set(train_ids) & set(test_ids):
        raise ValueError("This holdout needs at least 120 training and 40 distinct test records.")
    if split == "time" and ds.field(split_field).kind != "time":
        raise ValueError("Chronological evaluation requires a parsed timestamp field.")
    if split == "random" and any(
        f.kind == "identifier" and 2 < frame[f.id].nunique() < len(frame) for f in ds.fields
    ):
        warnings.append(
            "This recorded-row holdout may share entities between training and test. Choose a group holdout to assess unseen entities."
        )
    train, test = frame.loc[train_ids], frame.loc[test_ids]
    permitted = [f for f in requested if f not in excluded]
    excluded.update(_leakage(train, target, permitted, regression))
    permitted = [f for f in permitted if f not in excluded and train[f].notna().any()]
    for fid in requested:
        if fid not in permitted and fid not in excluded:
            excluded[fid] = "No recorded training values"
    if not permitted:
        raise ValueError(
            "No predictors remain after training-only identity, missingness and target-copy checks."
        )
    numeric = [f for f in permitted if ds.field(f).kind == "number"]
    categorical = [f for f in permitted if f not in numeric]
    preparation = ColumnTransformer(
        [
            (
                "number",
                Pipeline(
                    [
                        ("fill", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            ),
            (
                "category",
                Pipeline(
                    [
                        ("fill", SimpleImputer(strategy="most_frequent")),
                        (
                            "encode",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False, max_categories=20),
                        ),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
    )
    x_train, x_test = train[permitted].copy(), test[permitted].copy()
    for f in categorical:
        x_train[f] = x_train[f].map(lambda v: str(v) if pd.notna(v) else np.nan)
        x_test[f] = x_test[f].map(lambda v: str(v) if pd.notna(v) else np.nan)
    train_x = np.asarray(preparation.fit_transform(x_train), dtype=float)
    test_x = np.asarray(preparation.transform(x_test), dtype=float)
    train_y = train[target].to_numpy(dtype=float) if regression else train[target].astype(str).to_numpy()
    test_y = test[target].to_numpy(dtype=float) if regression else test[target].astype(str).to_numpy()
    if regression and (not np.isfinite(train_y).all() or np.unique(train_y).size < 2):
        raise ValueError("The numerical training target needs finite varying observations.")
    if not regression:
        counts = pd.Series(train_y).value_counts()
        if not 2 <= len(counts) <= 12 or counts.min() < 5:
            raise ValueError("Use two to twelve training classes with at least five observations each.")
        if set(test_y) - set(train_y):
            warnings.append(
                "The holdout contains a class absent from training; predictions cannot recover that unseen class."
            )
    estimators = (
        [("Mean reference", DummyRegressor(strategy="mean")), ("Linear baseline", Ridge(alpha=1.0))]
        if regression
        else [
            ("Majority reference", DummyClassifier(strategy="most_frequent")),
            ("Logistic baseline", LogisticRegression(max_iter=500, random_state=SEED)),
        ]
    )
    models = []

    def record(name, prediction):
        if len(prediction) != len(test_ids):
            raise ValueError("Predictions have a different source membership.")
        score = (
            mean_absolute_error(test_y, prediction)
            if regression
            else balanced_accuracy_score(test_y, prediction)
        )
        models.append(
            clean(
                {
                    "name": name,
                    "metric": "MAE" if regression else "Balanced accuracy",
                    "score": float(score),
                    "predictions": [
                        {"row": rid, "actual": actual, "predicted": predicted}
                        for rid, actual, predicted in zip(test_ids, test_y, prediction)
                    ],
                }
            )
        )

    with threadpool_limits(limits=1):
        for name, estimator in estimators:
            estimator.fit(train_x, train_y)
            record(name, estimator.predict(test_x))
    if hosted:
        try:
            record("Hosted TabPFN", hosted_predict(task, train_x, train_y, test_x, settings, hosted_factory))
        except Exception as exc:
            warnings.append(str(exc) if isinstance(exc, ValueError) else safe_error("TabPFN", exc))
    scope = digest([ds.fingerprint, rows, target, permitted, split, split_field])
    return clean(
        {
            "id": digest([scope, SEED]),
            "context": scope,
            "task": task,
            "target": target,
            "predictors": permitted,
            "split": split,
            "split_field": split_field,
            "train_ids": train_ids,
            "test_ids": test_ids,
            "excluded": excluded,
            "models": models,
            "warnings": warnings,
            "definition": "A fixed retrospective holdout on the recorded labelled population. All preprocessing and target-copy/component screens use training records only. Test outcomes stay local and are scored after predictions. No estimator is automatically selected as a winner.",
            "preprocessing": {
                "encoded_fields": int(train_x.shape[1]),
                "numeric_training_medians": {f: clean(train[f].median()) for f in numeric},
            },
        }
    )
