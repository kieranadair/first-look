"""One preparation path for preflight and execution, without fitting a model."""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd
import numpy as np

from firstlook.analytical_tasks import TaskDefinition, resolved_task, availability_decision
from firstlook.contracts import clean
from firstlook.semantic.model import get_model


@dataclass
class PreparedModel:
    data: pd.DataFrame
    predictors: list[str]
    excluded: dict[str, str]
    train_ids: list[int]
    test_ids: list[int]
    task: TaskDefinition
    report: dict


def prepare_model(dataset, ctx, target, split="random", split_field=None, requested=None, fixed_split=None):
    from firstlook.modeling import eligible_targets, predictor_policy, make_split

    if ctx.id != dataset.context(ctx.row_ids, ctx.focus, ctx.assumption).id:
        raise ValueError("The predictive protocol has a stale semantic context.")
    semantic = get_model(dataset)
    if semantic.model_group and (split != "group" or split_field != semantic.model_group):
        raise ValueError(
            "The semantic contract requires a group holdout on "
            + dataset.label(semantic.model_group)
            + ". Change the contract explicitly to use a different predictive task."
        )
    if target not in eligible_targets(dataset):
        raise ValueError("Choose an eligible measure or supported categorical focus with 200 labeled rows.")
    task = resolved_task(dataset, target)
    kind = "regression" if dataset.field(target).role.value == "measure" else "classification"
    metric = (
        task.primary_metric
        if task.primary_metric != "auto"
        else ("MAE" if kind == "regression" else "Balanced accuracy")
    )
    if metric not in (
        {"MAE", "RMSE"} if kind == "regression" else {"Balanced accuracy", "Macro F1", "Log loss"}
    ):
        raise ValueError("The task's primary metric does not match the chosen target type.")
    data = dataset.frame.loc[ctx.row_ids].dropna(subset=[target])
    labeled, censored = len(data), 0
    if task.horizon_days:
        if split != "time" or split_field != task.anchor_field:
            raise ValueError("A forward-horizon task requires a chronological split on its declared anchor.")
        anchors = pd.to_datetime(data[task.anchor_field], utc=True, errors="coerce")
        mature = anchors + pd.Timedelta(task.horizon_days, unit="D") <= pd.to_datetime(
            task.complete_through, utc=True
        )
        censored = int((~mature).sum())
        data = data.loc[mature]
    before_budget = len(data)
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
            data = data.sample(10_000, random_state=20261120).sort_index()
    if len(data) < 200:
        raise ValueError("The selected context needs 200 labeled rows after window and budget checks.")
    if data[target].nunique() < 2:
        raise ValueError("The selected target is constant in this analytical context.")
    if fixed_split is None:
        train_ids, test_ids = make_split(data, target, kind, split, split_field)
    else:
        train_ids, test_ids = [list(ids) for ids in fixed_split]
        if split != "time" or not split_field or not set(train_ids + test_ids) <= set(data.index):
            raise ValueError("Fixed memberships require a valid chronological protocol.")
        if data.loc[train_ids, split_field].max() >= data.loc[test_ids, split_field].min():
            raise ValueError("Fixed chronological memberships overlap in time.")
    if (
        len(train_ids) != len(set(train_ids))
        or len(test_ids) != len(set(test_ids))
        or set(train_ids) & set(test_ids)
    ):
        raise ValueError("Train and test membership overlap or repeat.")
    purged = 0
    if split == "time" and train_ids and test_ids:
        boundary = pd.to_datetime(data.loc[test_ids, split_field], utc=True).min()
        if task.horizon_days:
            known = pd.to_datetime(data.loc[train_ids, task.anchor_field], utc=True) + pd.Timedelta(
                task.horizon_days, unit="D"
            )
        else:
            known = pd.to_datetime(data.loc[train_ids, split_field], utc=True)
        if task.outcome_known_field:
            observed = pd.to_datetime(
                data.loc[train_ids, task.outcome_known_field], utc=True, errors="coerce"
            )
            known = pd.concat([known, observed], axis=1).max(axis=1).where(observed.notna())
        retained = known[known <= boundary].index.tolist()
        purged, train_ids = len(train_ids) - len(retained), retained
    if min(len(train_ids), len(test_ids)) < 20:
        raise ValueError("Both sides of the split require 20 observations after temporal purging.")
    if kind == "classification":
        train_counts, test_counts = (
            data.loc[train_ids, target].astype(str).value_counts(),
            data.loc[test_ids, target].astype(str).value_counts(),
        )
        if set(train_counts.index) != set(test_counts.index):
            raise ValueError("Every evaluated class must be represented on both sides of the split.")
        if min(train_counts.min(), test_counts.min()) < 5:
            raise ValueError("Every evaluated class requires at least five train and test observations.")
    predictors, excluded = predictor_policy(dataset, target, data.loc[train_ids], task, data)
    if split_field in predictors:
        predictors.remove(split_field)
        excluded[split_field] = "Split field excluded from predictors"
    if requested is not None:
        if not set(requested) <= set(predictors) or len(set(requested)) != len(requested):
            raise ValueError(
                "The requested predictors include a forbidden, constant, repeated or unknown field."
            )
        predictors = list(requested)
    predictors = predictors[:40]
    if not predictors:
        raise ValueError("No eligible predictors remain. Review timing and availability in Meaning.")
    assumptions = [
        {"field": f, "reason": availability_decision(dataset, f, data, task)[1]}
        for f in predictors
        if availability_decision(dataset, f, data, task)[0] == "assumption"
    ]
    if (
        task.purpose == "prediction"
        and split == "time"
        and not task.outcome_known_field
        and not semantic.search.get("event_protocol")
    ):
        assumptions.append(
            {
                "field": target,
                "reason": "Training label availability is assumed at the declared horizon end; no outcome-knowledge timestamp or attested event-reporting protocol was supplied.",
            }
        )
    partitions = []
    for name, ids in [("Training", train_ids), ("Held out", test_ids)]:
        part = data.loc[ids]
        row = {
            "Partition": name,
            "Rows": len(ids),
            "Target support": clean(part[target].astype(str).value_counts().to_dict())
            if kind == "classification"
            else {"min": float(part[target].min()), "max": float(part[target].max())},
        }
        if split_field:
            row["Distinct split values"] = int(part[split_field].nunique())
        if task.anchor_field:
            row["First anchor"], row["Last anchor"] = (
                str(part[task.anchor_field].min()),
                str(part[task.anchor_field].max()),
            )
        partitions.append(row)
    report = clean(
        {
            "status": "diagnostic_with_assumptions"
            if assumptions or task.purpose != "prediction"
            else "ready_for_declared_protocol",
            "context": ctx.id,
            "task": task.model_dump(mode="json"),
            "task_id": task.id,
            "active_rows": len(ctx.row_ids),
            "labeled_rows": labeled,
            "incomplete_window_rows": censored,
            "budget_omitted_rows": before_budget - len(data),
            "purged_training_rows": purged,
            "protocol_omitted_rows": len(data) - len(set(train_ids + test_ids)),
            "modeled_rows": len(train_ids) + len(test_ids),
            "train_ids": train_ids,
            "test_ids": test_ids,
            "partitions": partitions,
            "predictors": predictors,
            "excluded": excluded,
            "assumptions": assumptions,
            "primary_metric": metric,
            "boundary": "Readiness validates the declared protocol, not business truth or future performance. Target-dependent predictor screens use training rows only.",
        }
    )
    return PreparedModel(data, predictors, excluded, train_ids, test_ids, task, report)


def model_preflight(dataset, ctx, target, split="random", split_field=None, requested=None, fixed_split=None):
    try:
        return prepare_model(dataset, ctx, target, split, split_field, requested, fixed_split).report
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return {
            "status": "blocked",
            "context": ctx.id,
            "errors": [str(exc)],
            "boundary": "Descriptive exploration remains available.",
        }


def comparison_verdict(run):
    metric = run.parameters.get("readiness", {}).get(
        "primary_metric", "MAE" if run.task == "regression" else "Balanced accuracy"
    )
    active = run.provider
    observed = run.metrics.get(active, {}).get(metric)
    baseline = {
        name: values[metric] for name, values in run.metrics.items() if name != active and metric in values
    }
    if not baseline:
        return "No comparable local baseline was recorded."
    lower = metric in {"MAE", "RMSE", "Log loss"}
    reference = (min if lower else max)(baseline, key=lambda name: baseline[name])
    if observed is None:
        return f"Local comparison on {metric}; hosted TabPFN was not evaluated. No final-holdout winner was selected for deployment."
    difference = observed - baseline[reference]
    outcome = "equal to" if abs(difference) < 1e-12 else "lower than" if difference < 0 else "higher than"
    return f"{active} {metric} is {outcome} the strongest observed alternative ({reference}) on these held-out rows. {'Lower' if lower else 'Higher'} is better. Diagnostics retain the named model; this comparison selects no deployment winner and is not a significance test or evidence of no remaining signal."


def validate_recorded_protocol(run):
    """Validate recorded identities without fitting or treating model answers as facts."""
    if (
        len(set(run.train_ids)) != len(run.train_ids)
        or len(set(run.test_ids)) != len(run.test_ids)
        or set(run.train_ids) & set(run.test_ids)
    ):
        raise ValueError("Recorded model split memberships overlap or repeat.")
    if [r["row_id"] for r in run.predictions] != run.test_ids:
        raise ValueError("Recorded model predictions do not align to held-out membership.")
    readiness = run.parameters.get("readiness")
    if readiness:
        if (
            not isinstance(readiness, dict)
            or readiness.get("context") != run.context
            or readiness.get("train_ids") != run.train_ids
            or readiness.get("test_ids") != run.test_ids
            or readiness.get("predictors") != run.predictors
        ):
            raise ValueError("Recorded preflight and executed model protocol disagree.")
        task = TaskDefinition.model_validate(readiness["task"])
        if (
            task.id != readiness.get("task_id")
            or task.target != run.target
            or run.parameters.get("task_definition") != task.model_dump(mode="json")
        ):
            raise ValueError("Recorded model task definition changed.")
    ledger = run.parameters.get("predictions_by_model")
    if ledger:
        if (
            not isinstance(ledger, dict)
            or set(ledger) != set(run.metrics)
            or ledger.get(run.provider) != run.predictions
        ):
            raise ValueError("Recorded comparator predictions disagree with the active model.")
        actual = [r["actual"] for r in run.predictions]
        for records in ledger.values():
            if (
                not isinstance(records, list)
                or [r["row_id"] for r in records] != run.test_ids
                or [r["actual"] for r in records] != actual
            ):
                raise ValueError("Recorded comparators do not share exact held-out rows and labels.")
    return True
