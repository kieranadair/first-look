"""A bounded, typed analytical catalog. No generated code is executed."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, cast

import numpy as np
import pandas as pd

from firstlook.contracts import (
    AnalysisContext,
    AnalysisPlan,
    ChartSpec,
    Finding,
    ResultArtifact,
    Role,
    clean,
    digest,
)
from firstlook.ingest import Dataset
from firstlook.semantics import dimensions, measures

SEED = 20261120
OPERATIONS = {
    "recording_process",
    "metric",
    "distribution",
    "ecdf",
    "frequency",
    "relationship",
    "group_distribution",
    "category_relationship",
    "time",
    "missingness",
    "quantile_bin_summary",
    "exploration",
}


def number(value: Any) -> str:
    return "unavailable" if value is None else f"{float(value):,.3g}"


def paired(frame: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    return frame[fields].replace([np.inf, -np.inf], np.nan).dropna()


def correlations(frame: pd.DataFrame, x: str, y: str) -> dict:
    valid = paired(frame, [x, y])
    if len(valid) < 3 or valid[x].nunique() < 2 or valid[y].nunique() < 2:
        return {"pearson": None, "spearman": None, "n": len(valid)}
    # Normalize before squaring: valid finite inputs can still overflow or underflow
    # the covariance calculation. Scaling leaves both correlation measures unchanged.
    normalized = valid.astype(float) / valid.abs().max()
    return clean(
        {
            "pearson": normalized[x].corr(normalized[y]),
            "spearman": normalized[x].corr(normalized[y], method="spearman"),
            "n": len(valid),
        }
    )


def plan_for(
    ctx: AnalysisContext, operation: str, fields: list[str], question: str, params: dict | None = None
) -> AnalysisPlan:
    params = {"recipe_version": 2, **(params or {})}
    return AnalysisPlan(
        id=digest([ctx.id, operation, fields, params or {}]),
        operation=operation,
        fields=fields,
        context=ctx.id,
        question=question,
        params=params or {},
    )


def validate_plan(dataset: Dataset, ctx: AnalysisContext, plan: AnalysisPlan) -> None:
    if plan.context != ctx.id or ctx.dataset != dataset.record.fingerprint:
        raise ValueError("This plan belongs to an earlier analytical context.")
    if ctx.semantics != dataset.context([], ctx.focus, ctx.assumption).semantics:
        raise ValueError("Field meanings or semantic contract changed; recompute this plan.")
    if plan.operation not in OPERATIONS:
        raise ValueError("Unsupported analytical operation.")
    if plan.operation == "recording_process":
        from firstlook.recording_process import report

        if not plan.fields or plan.fields[0] != plan.params.get("time_field"):
            raise ValueError("Coverage timestamp does not match the declared fields.")
        report(dataset, ctx, time_field=plan.fields[0], fields=plan.fields[1:])
        return
    version = plan.params.get("recipe_version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version not in {1, 2}:
        raise ValueError("Unsupported calculation recipe version; inspect or migrate the recorded evidence.")
    if plan.operation == "exploration":
        from firstlook.exploration import validate_task

        validate_task(dataset, ctx, plan)
        return
    if plan.operation == "metric":
        from firstlook.semantic.model import get_model
        from firstlook.semantic.planner import metric_fields

        metric = get_model(dataset).metric(str(plan.params.get("metric", "")))
        groups = plan.params.get("group_by", [])
        if not isinstance(groups, list) or not all(isinstance(v, str) for v in groups):
            raise ValueError("Grouping fields must be recorded field identities.")
        expected: set[str] = set(metric_fields(dataset, metric)) | set(cast(list[str], groups))
        if plan.params.get("time_field"):
            expected.add(str(plan.params["time_field"]))
        if not expected <= set(dataset.frame) or any(dataset.field(fid).excluded for fid in expected):
            raise ValueError("A metric dependency is unknown or excluded.")
        if set(plan.fields) != expected or len(plan.fields) != len(set(plan.fields)):
            raise ValueError("Metric field dependencies do not match the recorded definition.")
        return
    sizes = {
        "distribution": 1,
        "ecdf": 1,
        "frequency": 1,
        "relationship": 2,
        "quantile_bin_summary": 2,
        "group_distribution": 2,
        "category_relationship": 2,
        "time": 2,
        "missingness": 0,
    }
    if len(plan.fields) != sizes[plan.operation] or len(set(plan.fields)) != len(plan.fields):
        raise ValueError("The operation requires the declared number of distinct fields.")
    if not set(plan.fields).issubset(dataset.frame.columns):
        raise ValueError("Unknown field identity.")
    for fid in plan.fields:
        if dataset.field(fid).excluded:
            raise ValueError("An excluded field cannot enter an analysis.")
    if dataset.record.semantic_model and plan.operation in {
        "relationship",
        "quantile_bin_summary",
        "group_distribution",
        "time",
    }:
        if any(
            dataset.record.semantic_model.meaning(fid).kind in {"circular", "coordinate"}
            for fid in plan.fields
            if dataset.field(fid).role == Role.MEASURE
        ):
            raise ValueError(
                "This operation assumes linear quantities. Circular and coordinate geometry require a supported domain summary in Meaning."
            )
    numeric_ops = {"relationship", "distribution", "ecdf", "quantile_bin_summary"}
    if plan.operation in numeric_ops and any(dataset.field(f).role != Role.MEASURE for f in plan.fields):
        raise ValueError("This operation requires measures, not identifiers or codes.")
    if plan.operation == "group_distribution":
        if plan.fields[0] not in dimensions(dataset) or plan.fields[1] not in measures(dataset):
            raise ValueError("A group comparison requires a dimension and a measure.")
    if plan.operation == "category_relationship" and any(f not in dimensions(dataset) for f in plan.fields):
        raise ValueError("A category relationship requires dimensions.")
    if plan.operation == "time":
        if dataset.field(plan.fields[0]).role != Role.TIME or plan.fields[1] not in measures(dataset):
            raise ValueError("A time summary requires a timestamp and measure.")
    if plan.operation == "frequency" and plan.fields[0] not in dimensions(dataset):
        raise ValueError("Frequency views require a categorical or ordered dimension.")


def analyze(dataset: Dataset, ctx: AnalysisContext, plan: AnalysisPlan) -> tuple[ResultArtifact, Finding]:
    validate_plan(dataset, ctx, plan)
    if plan.operation == "recording_process":
        from firstlook.recording_process import analyze_recording

        return analyze_recording(dataset, ctx, plan)
    if plan.operation == "exploration":
        from firstlook.exploration import execute

        return execute(dataset, ctx, plan)
    if plan.operation == "metric":
        from firstlook.semantic.engine import evaluate

        return evaluate(dataset, ctx, plan)
    if (
        not ctx.row_ids
        or len(ctx.row_ids) != len(set(ctx.row_ids))
        or not set(ctx.row_ids).issubset(dataset.frame.index)
    ):
        raise ValueError("Choose a nonempty valid subset of rows.")
    frame = dataset.frame.loc[ctx.row_ids]
    fields, op = plan.fields, plan.operation
    labels = [
        dataset.label(f) + (" (" + dataset.field(f).unit + ")" if dataset.field(f).unit else "")
        for f in fields
    ]
    records: list[dict] = []
    metrics: dict = {}
    warnings: list[str] = []
    modern = int(cast(Any, plan.params.get("recipe_version", 1))) >= 2
    meta: dict = {"method_version": "2" if modern else "1", "sampled": False}
    if dataset.record.semantic_model:
        meta["semantic_revision"] = dataset.record.semantic_model.revision
    units = [
        dataset.field(f).unit
        for f in fields
        if dataset.field(f).role == Role.MEASURE and dataset.field(f).unit
    ]
    if len(units) == 1:
        meta["units"] = units[0]
    n, missing = len(frame), 0
    template, x_label, y_label = "bar", "", "Count"
    observation = ""
    family = op
    score = 0.3

    if op == "distribution":
        s = frame[fields[0]].dropna().astype(float)
        n, missing = len(s), len(frame) - len(s)
        if not n:
            raise ValueError("This field has no finite values.")
        bins = max(5, min(50, int(cast(Any, plan.params.get("bins", min(30, max(5, int(np.sqrt(n)))))))))
        if "edges" in plan.params:
            edges = np.asarray(plan.params["edges"], dtype=float)
            if (
                len(edges) < 3
                or len(edges) > 102
                or not np.isfinite(edges).all()
                or not np.all(np.diff(edges) > 0)
                or edges[0] > s.min()
                or edges[-1] < s.max()
            ):
                raise ValueError("Histogram edges must be finite, increasing and cover all values.")
            counts, edges = np.histogram(s, bins=edges)
        else:
            counts, edges = np.histogram(s, bins=bins)
        normalization = str(plan.params.get("normalization", "count"))
        if normalization not in {"count", "proportion", "density"} or not np.allclose(
            np.diff(edges), np.diff(edges)[0]
        ):
            raise ValueError(
                "Use count, proportion or density with the supported equal-width histogram bins."
            )
        for i, count in enumerate(counts):
            mask = (s >= edges[i]) & ((s <= edges[i + 1]) if i == len(counts) - 1 else (s < edges[i + 1]))
            records.append(
                {
                    "label": f"{edges[i]:.3g}–{edges[i + 1]:.3g}",
                    "x": float((edges[i] + edges[i + 1]) / 2),
                    "value": int(count)
                    if normalization == "count"
                    else float(count / n)
                    if normalization == "proportion"
                    else float(count / (n * (edges[i + 1] - edges[i]))),
                    **({"count": int(count)} if modern else {}),
                    "left": float(edges[i]),
                    "right": float(edges[i + 1]),
                    "row_ids": s.index[mask].tolist(),
                }
            )
        metrics = clean(
            {
                "mean": s.mean(),
                "median": s.median(),
                "std": s.std(ddof=1),
                "q1": s.quantile(0.25),
                "q3": s.quantile(0.75),
                "min": s.min(),
                "max": s.max(),
            }
        )
        template, x_label, y_label = "histogram", labels[0], "Recorded values"
        if modern:
            meta["normalization"] = normalization
            y_label = {
                "count": "Recorded row count",
                "proportion": "Proportion per bin",
                "density": "Density (area sums to one)",
            }[normalization]
        observation = f"The median {labels[0]} is {number(metrics['median'])}; the middle half spans {number(metrics['q1'])} to {number(metrics['q3'])}."
        score = 0.38 + min(missing / max(len(frame), 1), 0.2)
    elif op == "ecdf":
        s = frame[fields[0]].dropna().astype(float).sort_values(kind="stable")
        n, missing = len(s), len(frame) - len(s)
        if not n:
            raise ValueError("This field has no finite values.")
        unique = s.drop_duplicates()
        values = s.to_numpy()
        if modern:
            from firstlook.numerics import compressed_ecdf

            locations, probabilities, error, _ = compressed_ecdf(values, cap=1198)
            plotted = locations
            meta.update(
                ecdf_error=error,
                ecdf_method="observed-value rank compression",
                step="post",
                endpoint_extension="0 below min; 1 at/above max",
                selection_semantics="Recorded observations exactly at selected vertices; not cumulative membership",
            )
        else:
            plotted = unique.iloc[
                np.unique(np.linspace(0, len(unique) - 1, min(1200, len(unique))).astype(int))
            ]
        records = [
            {
                "x": float(value),
                "value": float(np.searchsorted(values, value, side="right") / n),
                "row_ids": s.index[s.eq(value)].tolist(),
            }
            for value in plotted
        ]
        template, x_label, y_label = "ecdf", labels[0], "Cumulative proportion"
        meta["sampled"] = len(plotted) < len(unique)
        if meta["sampled"]:
            warnings.append(
                f"Display compressed to {len(plotted):,} observed locations. Maximum vertical CDF error is {error:.6g}; omitted values are not selectable. Statistics use all source values."
                if modern
                else "The staircase uses at most 1,200 exact quantile locations; source rows between these locations are not selectable."
            )
        metrics = {"median": float(s.median()), "distinct": len(unique)}
        observation = (
            f"The cumulative view shows the proportion at or below each recorded value of {labels[0]}."
        )
    elif op == "frequency":
        s = frame[fields[0]].dropna().astype(str)
        counts = s.value_counts()
        order = dataset.field(fields[0]).order
        levels = (
            list(cast(Any, plan.params["fixed_levels"]))
            if plan.params.get("fixed_levels")
            else [v for v in order if v in counts]
            if order
            else counts.head(12).index.tolist()
        )
        if not len(counts):
            raise ValueError("No recorded categories.")
        for label in levels:
            records.append(
                {
                    "label": label,
                    "value": int(counts.get(label, 0)),
                    "row_ids": s.index[s == label].tolist(),
                    **({"key": digest([fields, label]), "other": False} if modern else {}),
                }
            )
        if (~s.isin(levels)).any() or plan.params.get("fixed_remainder"):
            other = ~s.isin(levels)
            records.append(
                {
                    "label": "Other recorded levels",
                    "value": int(other.sum()),
                    "row_ids": s.index[other].tolist(),
                    **({"key": digest([fields, "synthetic-remainder"]), "other": True} if modern else {}),
                }
            )
            warnings.append(f"The largest 12 levels cover {s.isin(levels).mean():.1%} of nonmissing values.")
        n, missing = len(s), len(frame) - len(s)
        metrics = {"distinct": len(counts), "largest_count": int(counts.iloc[0])}
        x_label, y_label = "Recorded rows", labels[0]
        observation = f"{counts.index[0]} is the most frequent recorded level: {counts.iloc[0]:,} of {n:,} nonmissing rows."
    elif op in {"relationship", "quantile_bin_summary"}:
        valid = paired(frame, fields)
        if len(valid) > 20_000:
            valid = valid.sample(20_000, random_state=SEED).sort_index()
            meta["sampled"] = True
            warnings.append("Association calculations use a seeded sample of 20,000 rows.")
        metrics = correlations(valid, *fields)
        n, missing = len(valid), len(frame) - len(paired(frame, fields))
        if n < 30 or metrics["pearson"] is None:
            raise ValueError("An association needs 30 paired rows and variation in both fields.")
        if op == "relationship":
            plotted = valid.sample(min(5000, n), random_state=SEED).sort_index()
            records = [
                {"x": float(row[fields[0]]), "y": float(row[fields[1]]), "row_id": int(cast(Any, i))}
                for i, row in plotted.iterrows()
            ]
            meta["plotted_rows"] = len(plotted)
            if modern:
                from firstlook.exploration_contracts import AnalysisScope

                eligible = paired(frame, fields)
                meta["analysis_scope"] = AnalysisScope(
                    context=ctx.id,
                    eligible_rows=len(eligible),
                    statistical_rows=n,
                    displayed_marks=len(plotted),
                    missing_rows=missing,
                    statistical_sample=len(valid) < len(eligible),
                    display_sample=len(plotted) < len(eligible),
                    seed=SEED,
                    statistical_membership_hash=digest(valid.index.tolist()),
                    display_membership_hash=digest(plotted.index.tolist()),
                ).model_dump(mode="json")
                meta["sampled"] = len(plotted) < len(eligible)
                meta["full_pair_domains"] = {
                    "x": [float(eligible[fields[0]].min()), float(eligible[fields[0]].max())],
                    "y": [float(eligible[fields[1]].min()), float(eligible[fields[1]].max())],
                }
                if len(plotted) < len(eligible):
                    warnings.append(
                        f"Display uses {len(plotted):,} seeded points of {len(eligible):,} eligible pairs; statistics use {n:,}. Selecting points selects only their recorded rows."
                    )
            template, x_label, y_label = "scatter", labels[0], labels[1]
            observation = f"Across {n:,} paired rows, Pearson r = {number(metrics['pearson'])} and Spearman ρ = {number(metrics['spearman'])}."
            score = 0.5 + 0.35 * abs(metrics["spearman"])
        else:
            bins = pd.qcut(
                valid[fields[0]],
                q=max(3, min(6, int(cast(Any, plan.params.get("bins", 5))))),
                duplicates="drop",
            )
            for interval, group in valid.groupby(bins, observed=True):
                if len(group) < 20:
                    if modern:
                        records.append(
                            {
                                "x": float(group[fields[0]].median())
                                if len(group)
                                else float(cast(Any, interval).mid),
                                "value": None,
                                "q1": None,
                                "q3": None,
                                "n": len(group),
                                "left": float(cast(Any, interval).left),
                                "right": float(cast(Any, interval).right),
                                "row_ids": [],
                            }
                        )
                    continue
                records.append(
                    {
                        "x": float(group[fields[0]].median()),
                        "value": float(group[fields[1]].median()),
                        "q1": float(group[fields[1]].quantile(0.25)),
                        "q3": float(group[fields[1]].quantile(0.75)),
                        "n": len(group),
                        **(
                            {
                                "left": float(cast(Any, interval).left),
                                "right": float(cast(Any, interval).right),
                            }
                            if modern
                            else {}
                        ),
                        "row_ids": group.index.tolist(),
                    }
                )
            if sum(r["value"] is not None for r in records) < 2:
                raise ValueError("Not enough supported quantile bins.")
            template, x_label, y_label = "line", labels[0] + " (bin median)", labels[1] + " (median)"
            if modern:
                meta["conditional_spread"] = True
                meta["selection_semantics"] = (
                    "Retained statistical-sample members of a supported quantile bin; not every source record in the horizontal range"
                )
                y_label = labels[1] + " (median and middle half)"
                meta["bin_policy"] = (
                    "Quantile bins; linear quartile estimator; bins with fewer than 20 paired observations omitted; no connecting unsupported bins"
                )
            observation = f"{len(records)} supported quantile bins show conditional medians; each bin retains its count and quartiles."
    elif op == "group_distribution":
        group_field, value_field = fields
        valid = frame[fields].dropna().copy()
        valid[group_field] = valid[group_field].astype(str)
        counts = valid[group_field].value_counts()
        levels = counts[counts >= 20].head(8).index.tolist()
        order = dataset.field(group_field).order
        if order:
            levels = [v for v in order if v in levels]
        for level in levels:
            v = valid.loc[valid[group_field] == level, value_field].astype(float)
            records.append(
                clean(
                    {
                        "label": level,
                        "value": v.median(),
                        "mean": v.mean(),
                        "min": v.min(),
                        "q1": v.quantile(0.25),
                        "median": v.median(),
                        "q3": v.quantile(0.75),
                        "max": v.max(),
                        "n": len(v),
                        "row_ids": v.index.tolist(),
                    }
                )
            )
        if len(records) < 2:
            raise ValueError("At least two groups with 20 observations are needed.")
        n, missing = sum(r["n"] for r in records), len(frame) - len(valid)
        omitted = len(valid) - n
        if omitted:
            warnings.append(f"{omitted:,} paired rows belong to small or undisplayed groups.")
        variance = float(valid[value_field].var())
        between = sum(r["n"] * (r["mean"] - valid[value_field].mean()) ** 2 for r in records)
        eta = between / max(float(((valid[value_field] - valid[value_field].mean()) ** 2).sum()), 1e-12)
        metrics = {
            "groups": len(records),
            "variance_share": eta,
            "variance": variance,
            "omitted_rows": omitted,
        }
        template, x_label, y_label = "box", labels[0], labels[1]
        meta["whisker_convention"] = "Observed minimum and maximum; boxes show quartiles, not 1.5-IQR fences"
        observation = f"Recorded group medians range from {number(min(r['value'] for r in records))} to {number(max(r['value'] for r in records))}; inspect the spread and group sizes."
        score = 0.45 + min(float(eta), 0.5)
    elif op == "category_relationship":
        valid = frame[fields].dropna().astype(str)
        if len(valid) < (1 if modern else 30) or any(valid[f].nunique() > 8 for f in fields):
            raise ValueError("Use two dimensions with at most eight levels and 30 paired rows.")
        table = pd.crosstab(valid[fields[0]], valid[fields[1]])
        meta["category_order"] = {
            axis: dataset.field(fid).order
            for axis, fid in zip(("x", "y"), fields)
            if dataset.field(fid).order
        }
        for x in table.index:
            for y in table.columns:
                ids = valid.index[(valid[fields[0]] == x) & (valid[fields[1]] == y)].tolist()
                count = int(table.loc[x, y])
                mode = str(plan.params.get("normalization", "count"))
                if mode not in {"count", "whole", "within_x", "within_y", "residual"}:
                    raise ValueError("Choose count, whole-table, within-X, within-Y or descriptive residual.")
                denominator = (
                    len(valid)
                    if mode == "whole"
                    else int(table.loc[x].sum())
                    if mode == "within_x"
                    else int(table[y].sum())
                    if mode == "within_y"
                    else 1
                )
                expected = float(table.loc[x].sum() * table[y].sum() / len(valid))
                value = (
                    (count - expected) / np.sqrt(expected)
                    if mode == "residual" and expected > 0
                    else count / denominator
                )
                records.append(
                    {
                        "x": x,
                        "y": y,
                        "value": value if modern else count,
                        "row_ids": ids,
                        **(
                            {
                                "count": count,
                                "denominator": denominator,
                                "expected": expected,
                                "key": digest([fields, x, y]),
                            }
                            if modern
                            else {}
                        ),
                    }
                )
        n, missing = len(valid), len(frame) - len(valid)
        template, x_label, y_label = "heatmap", labels[0], labels[1]
        observation = (
            f"{n:,} paired rows are shown as joint counts; a dark cell is a count, not a conditional rate."
        )
        metrics = {"cells": table.size}
        if modern:
            meta.update(
                normalization=mode,
                denominator_population="Complete recorded category pairs only; missing pairs excluded",
                descriptive_only=True,
            )
            observation = f"{n:,} complete category pairs; mode {mode}. Within-X conditions on {labels[0]}; within-Y conditions on {labels[1]}. Missing pairs are reported separately."
            if mode == "residual":
                warnings.append(
                    "Descriptive standardized independence residuals, not significance tests. Repeated entities and sparse cells can invalidate inferential interpretations."
                )
    elif op == "missingness":
        for f in dataset.record.fields:
            ids = frame.index[frame[f.id].isna()].tolist()
            if ids:
                records.append({"label": f.name, "value": len(ids), "field": f.id, "row_ids": ids})
        if not records:
            raise ValueError("No missing values under the declared policy.")
        records.sort(key=lambda r: -r["value"])
        metrics = {"missing_cells": sum(r["value"] for r in records), "rows": len(frame)}
        x_label, y_label = "Missing values", "Field"
        observation = f"{metrics['missing_cells']:,} cells are missing under the declared policy; fields can overlap on the same rows."
        score = 0.65
    elif op == "time":
        valid = frame[fields].dropna()
        if len(valid) < 5:
            raise ValueError("At least five timestamped values are needed.")
        period = str(
            plan.params.get(
                "period", "MS" if (valid[fields[0]].max() - valid[fields[0]].min()).days > 90 else "D"
            )
        )
        if period not in {"D", "W", "MS"}:
            raise ValueError("Unsupported period.")
        grouped = valid.groupby(pd.Grouper(key=fields[0], freq=period))
        for stamp, group in grouped:
            if len(records) >= 1200:
                raise ValueError("This time aggregation exceeds the 1,200-period view budget.")
            records.append(
                clean(
                    {
                        "x": stamp,
                        "value": group[fields[1]].mean() if len(group) else None,
                        "n": len(group),
                        "row_ids": group.index.tolist(),
                    }
                )
            )
        n, missing = len(valid), len(frame) - len(valid)
        template, x_label, y_label = "line", labels[0], labels[1] + " (mean)"
        metrics = {"period": period, "observed_periods": sum(r["n"] > 0 for r in records)}
        meta["time_axis"] = True
        observation = f"Mean {labels[1]} is summarized by {period}; empty periods remain missing."
        score = 0.55
    else:
        raise ValueError("Unsupported operation.")

    result = ResultArtifact(
        id=plan.id,
        plan=plan,
        records=clean(records),
        metrics=clean(metrics),
        support=n,
        missing=missing,
        warnings=warnings,
        metadata=clean(meta),
    )
    chart = ChartSpec(
        id=digest([result.id, template]),
        result_id=result.id,
        context=ctx.id,
        template=template,
        x_label=x_label,
        y_label=y_label,
        zero_baseline=template in {"bar", "histogram"},
        alt=observation,
        rules=["VALID-01", "SOURCE-01", "SUPPORT-01", "SCALE-01"]
        + (["EXP-SCOPE"] if modern and op in {"ecdf", "relationship"} else [])
        + (["EXP-SHAPE"] if modern and op == "quantile_bin_summary" else [])
        + (["ORDER-01"] if op == "frequency" else [])
        + (["AGG-01"] if op in {"group_distribution", "time", "quantile_bin_summary"} else []),
    )
    finding = Finding(
        id=plan.id,
        title=plan.question,
        observation=observation,
        result_id=result.id,
        chart=chart,
        family=family,
        score=score,
        limitations=["Descriptive evidence from the recorded rows; no causal conclusion."] + warnings,
    )
    if modern:
        from firstlook.exploration_contracts import ExplorationTask

        result.metadata["task"] = ExplorationTask(
            family=family, question=plan.question, fields=fields, base_context=ctx.id, operation=op
        ).model_dump(mode="json")
    return result, finding


@dataclass
class Investigation:
    context: AnalysisContext
    findings: list[Finding] = field(default_factory=list)
    results: dict[str, ResultArtifact] = field(default_factory=dict)
    candidate_log: list[dict] = field(default_factory=list)
    challenges: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    terra: dict = field(default_factory=dict)
    model_runs: list = field(default_factory=list)
    semantic_decisions: list = field(default_factory=list)
    coverage: list[dict] = field(default_factory=list)
    related_views: dict[str, dict] = field(default_factory=dict)
    goal: str = ""
    judgments: list = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    question_history: list[dict] = field(default_factory=list)

    def add_view(self, result: ResultArtifact, finding: Finding) -> None:
        """Bound interactive working views; pins carry their own immutable snapshots."""
        self.findings = ([finding] + [f for f in self.findings if f.id != finding.id])[:18]
        self.results[result.id] = result
        retained = {f.result_id for f in self.findings}
        self.results = {rid: r for rid, r in self.results.items() if rid in retained}
        retained_findings = {f.id for f in self.findings}
        self.challenges = [c for c in self.challenges if c.parent_id in retained_findings]
        self.related_views = {
            k: v
            for k, v in self.related_views.items()
            if k in self.results and v["companion"] in self.results
        }


def discover(dataset: Dataset, context: AnalysisContext | None = None) -> Investigation:
    ctx = context or dataset.context()
    inv = Investigation(ctx)
    if dataset.record.semantic_model and dataset.record.semantic_model.search.get("analytical_task"):
        from firstlook.analytical_tasks import current_task

        inv.goal = current_task(dataset).question
    frame = dataset.frame.loc[ctx.row_ids]
    nums = sorted(measures(dataset), key=lambda f: f != ctx.focus)[:40]
    cats = sorted(dimensions(dataset), key=lambda f: f != ctx.focus)[:10]
    proposed: list[tuple[float, AnalysisPlan]] = []

    def add(op: str, fields: list[str], title: str, priority: float, params=None) -> None:
        plan = plan_for(ctx, op, fields, title, params)
        proposed.append((priority + (0.15 if ctx.focus in fields else 0), plan))
        inv.candidate_log.append(
            {"operation": op, "fields": fields, "plan": plan.id, "stage": "candidate", "priority": priority}
        )

    pairs = list(combinations(nums, 2))
    pairs.sort(key=lambda fs: ctx.focus not in fs)
    for pair_index, (x, y) in enumerate(pairs[:300]):
        sample = frame if len(frame) <= 20_000 else frame.sample(20_000, random_state=SEED)
        stats = correlations(sample, x, y)
        inv.candidate_log.append(
            {
                "operation": "relationship",
                "fields": [x, y],
                **stats,
                "eligible": stats["n"] >= 30 and stats["pearson"] is not None,
            }
        )
        if stats["n"] >= 30 and stats["spearman"] is not None:
            magnitude = max(abs(stats["pearson"]), abs(stats["spearman"]))
            if magnitude >= 0.30:
                add(
                    "relationship",
                    [x, y],
                    f"How do {dataset.label(x)} and {dataset.label(y)} relate?",
                    0.65 + magnitude * 0.35,
                )
            # A bounded conditional-shape screen can recover a curved relationship
            # whose signed linear/rank summaries cancel. This is descriptive search.
            if pair_index < 24:
                bx, by = (y, x) if ctx.focus == x else (x, y)
                valid = paired(sample, [bx, by])
                bins = pd.qcut(valid[bx], q=5, duplicates="drop")
                medians = valid.groupby(bins, observed=True)[by].agg(["median", "count"])
                medians = medians[medians["count"] >= 20]
                quartiles = valid.groupby(bins, observed=True)[by].quantile(np.array([0.25, 0.75])).unstack()
                widths = (quartiles[0.75] - quartiles[0.25]).loc[medians.index]
                spread_change = float(widths.max() - widths.min()) / max(
                    float(valid[by].quantile(0.75) - valid[by].quantile(0.25)), 1e-12
                )
                iqr = float(valid[by].quantile(0.75) - valid[by].quantile(0.25))
                spread = float(medians["median"].max() - medians["median"].min()) / max(iqr, 1e-12)
                if len(medians) >= 3 and ((spread >= 0.5 and magnitude < 0.5) or spread_change >= 0.5):
                    add(
                        "quantile_bin_summary",
                        [bx, by],
                        f"How do center and spread of {dataset.label(by)} vary with {dataset.label(bx)}?",
                        0.72,
                    )
                    add(
                        "relationship",
                        [bx, by],
                        f"What shape connects {dataset.label(bx)} and {dataset.label(by)}?",
                        0.68,
                    )
    for f in nums[:12]:
        if frame[f].notna().any():
            add("distribution", [f], f"What does {dataset.label(f)} look like?", 0.35)
    for f in cats:
        if frame[f].notna().any():
            add("frequency", [f], f"Which {dataset.label(f)} levels are represented?", 0.30)
        for value in nums[:8]:
            valid = frame[[f, value]].dropna()
            if valid[f].nunique() < 2 or valid[f].nunique() > 30:
                continue
            counts = valid.groupby(f)[value].count()
            if sum(counts >= 20) < 2:
                continue
            grand = valid[value].mean()
            sums = valid.groupby(f)[value].agg(["mean", "count"])
            total = float(((valid[value] - grand) ** 2).sum())
            eta = float(((sums["mean"] - grand) ** 2 * sums["count"]).sum()) / max(total, 1e-12)
            add(
                "group_distribution",
                [f, value],
                f"Does {dataset.label(value)} differ by {dataset.label(f)}?",
                0.45 + min(eta, 0.5),
            )
            if cats.index(f) < 3 and nums.index(value) < 4:
                spread_by_group = valid.groupby(f)[value].std().dropna()
                spread_by_group = spread_by_group.loc[
                    counts[counts >= 20].index.intersection(spread_by_group.index)
                ]
                if len(spread_by_group) >= 2 and spread_by_group.max() > 2 * max(
                    float(spread_by_group.min()), 1e-12
                ):
                    add(
                        "exploration",
                        [f, value],
                        f"How do the distributions of {dataset.label(value)} differ by {dataset.label(f)}?",
                        0.74,
                        {
                            "recipe": "group_shape",
                            "levels": [str(spread_by_group.idxmin()), str(spread_by_group.idxmax())],
                        },
                    )
    for x, y in list(combinations(cats, 2))[:20]:
        if frame[x].nunique() <= 8 and frame[y].nunique() <= 8:
            add(
                "category_relationship",
                [x, y],
                f"How are {dataset.label(x)} and {dataset.label(y)} distributed together?",
                0.28,
            )
    for f in dataset.record.fields:
        if f.role == Role.TIME and not f.excluded:
            for value in nums[:2]:
                add("time", [f.id, value], f"How does recorded {dataset.label(value)} vary over time?", 0.7)
    if frame.isna().any().any():
        add("missingness", [], "Where is information missing?", 0.62)
    if any(f.role == Role.TIME and not f.excluded for f in dataset.record.fields):
        from firstlook.recording_process import recording_plan

        try:
            coverage_plan = recording_plan(dataset, ctx)
            proposed.append((0.65, coverage_plan))
        except ValueError:
            pass
    from firstlook.semantic.planner import candidates

    semantic_candidates, semantic_log = candidates(dataset, ctx)
    proposed.extend(semantic_candidates)
    inv.candidate_log.extend(semantic_log)
    inv.semantic_decisions = semantic_log
    # Greedy redundancy penalty keeps the shortlist from becoming one family of repeated views.
    remaining = sorted(proposed, key=lambda v: -v[0])
    chosen_fields: list[str] = []
    family_count: dict[str, int] = {}
    while remaining and len(inv.findings) < 12:
        remaining.sort(
            key=lambda v: (
                -(
                    v[0]
                    - (0.03 if v[1].operation == "metric" else 0.09)
                    * sum(f in chosen_fields for f in v[1].fields)
                    - 0.16 * family_count.get(v[1].operation, 0)
                )
            )
        )
        priority, plan = remaining.pop(0)
        if plan.operation == "metric" and family_count.get("metric", 0) >= 3:
            continue
        try:
            result, finding = analyze(dataset, ctx, plan)
        except ValueError as exc:
            inv.candidate_log.append(
                {"operation": plan.operation, "fields": plan.fields, "eligible": False, "reason": str(exc)}
            )
            continue
        finding.score = priority
        inv.findings.append(finding)
        inv.results[result.id] = result
        chosen_fields.extend(plan.fields)
        family_count[plan.operation] = family_count.get(plan.operation, 0) + 1
    from firstlook.exploration import perspective_coverage

    inv.coverage = perspective_coverage(dataset, inv)
    return inv
