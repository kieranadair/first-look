"""Executable challenges; a changed result is evidence, never a failed user."""

from __future__ import annotations

import numpy as np
from typing import Any

from firstlook.contracts import ChallengeResult, ChartSpec, Finding, ResultArtifact, clean, digest
from firstlook.discovery import (
    SEED,
    Investigation,
    analyze,
    correlations,
    number,
    paired,
    plan_for,
)
from firstlook.ingest import Dataset
from firstlook.semantics import dimensions
from firstlook.semantic.checks import LABELS as SEMANTIC_LABELS

LABELS = {
    **SEMANTIC_LABELS,
    "subgroup": "Compare recorded groups",
    "extremes": "Check extreme-value sensitivity",
    "rank": "Compare rank and linear association",
    "distribution": "Look behind the averages",
    "missingness": "Check missing-value composition",
    "quantile_bin_summary": "Inspect conditional shape",
    "resampling": "Check resampling stability",
    "aggregation": "Compare time aggregation",
    "binning": "Compare histogram bins",
    "residual_spread_by_bin": "Inspect held-out error spread",
    "group_shape": "Compare group shape and quantiles",
    "density": "Count every pair in a numeric grid",
    "influence": "Inspect linear-fit influence",
}


def eligible(dataset: Dataset, inv: Investigation, finding: Finding) -> list[str]:
    result = inv.results[finding.result_id]
    op = result.plan.operation
    choices = []
    if op == "metric":
        from firstlook.semantic.checks import eligible as semantic_eligible

        return semantic_eligible(dataset, result)
    if op == "relationship":
        if dimensions(dataset):
            choices.append("subgroup")
        choices.extend(["extremes", "rank", "quantile_bin_summary", "density", "influence"])
        if inv.context.assumption == "exchangeable":
            choices.append("resampling")
    if op == "group_distribution":
        choices.extend(["distribution", "group_shape"])
    if op == "quantile_bin_summary":
        choices.extend(["density", "influence"])
    if op == "time":
        choices.append("aggregation")
    if op in {"distribution", "ecdf"}:
        choices.append("binning")
    if op == "model_diagnostic" and inv.model_runs and inv.model_runs[-1].task == "regression":
        choices.append("residual_spread_by_bin")
    if result.missing and dimensions(dataset) and result.plan.fields:
        choices.append("missingness")
    return choices


def challenge(
    dataset: Dataset, inv: Investigation, finding: Finding, operation: str, group_field: str | None = None
) -> ChallengeResult:
    cid = digest([finding.id, operation, group_field])
    if operation not in eligible(dataset, inv, finding):
        return ChallengeResult(
            id=cid,
            parent_id=finding.id,
            operation=operation,
            status="not_checked",
            summary="This check is not applicable to the current view.",
        )
    original = inv.results[finding.result_id]
    if original.plan.operation == "metric":
        from firstlook.semantic.checks import check

        return check(dataset, inv, finding, operation, group_field)
    ctx = inv.context
    frame = dataset.frame.loc[ctx.row_ids]
    fields = original.plan.fields
    result = None
    chart = None
    status = "similar"
    summary = ""
    try:
        if operation in {"group_shape", "density", "influence"}:
            result, other = analyze(
                dataset, ctx, plan_for(ctx, "exploration", fields, LABELS[operation], {"recipe": operation})
            )
            chart, summary, status = other.chart, other.observation, "not_checked"
        elif operation == "subgroup":
            group = group_field or next(
                (f for f in dimensions(dataset) if 2 <= frame[f].nunique() <= 8), None
            )
            if group is None:
                raise ValueError("Choose a dimension with 2–8 recorded levels.")
            if group not in dimensions(dataset) or group in fields:
                raise ValueError("Choose an eligible separate group field.")
            valid = frame[fields + [group]].dropna()
            group_metrics, records = [], []
            for label, part in valid.groupby(group, observed=True):
                stats = correlations(part, *fields)
                if stats["n"] < 30 or stats["pearson"] is None:
                    continue
                group_metrics.append({"group": str(label), **stats})
                sample = part.sample(min(1500, len(part)), random_state=SEED).sort_index()
                records.extend(
                    [
                        {
                            "x": float(r[fields[0]]),
                            "y": float(r[fields[1]]),
                            "group": str(label),
                            "row_id": int(i),
                        }
                        for i, r in sample.iterrows()
                    ]
                )
                if len(group_metrics) == 8:
                    break
            if len(group_metrics) < 2:
                raise ValueError("At least two groups with 30 paired values are required.")
            pooled = original.metrics["pearson"]
            changed = any(
                (m["pearson"] * pooled < 0 and abs(m["pearson"]) >= 0.15) or abs(m["pearson"] - pooled) > 0.35
                for m in group_metrics
            )
            status = "changed" if changed else "similar"
            detail = "; ".join(
                f"{m['group']}: r = {number(m['pearson'])}, n = {m['n']:,}" for m in group_metrics
            )
            summary = f"Pooled r = {number(pooled)}. Within recorded groups: {detail}. This is a conditional comparison, not a causal explanation."
            plan = plan_for(
                ctx, "relationship", fields, "The relationship within recorded groups", {"group": group}
            )
            result = ResultArtifact(
                id=cid,
                plan=plan,
                records=records,
                metrics=clean({"pooled": pooled, "groups": group_metrics, "group_field": group}),
                support=sum(m["n"] for m in group_metrics),
                missing=len(frame) - len(valid),
                metadata={"group_field": group},
            )
            chart = original_chart(finding, result, "scatter", summary)
        elif operation == "extremes":
            valid = paired(frame, fields)
            mask = np.ones(len(valid), dtype=bool)
            for f in fields:
                lo, hi = valid[f].quantile([0.01, 0.99])
                mask &= valid[f].between(lo, hi).to_numpy()
            kept = valid.index[mask].tolist()
            if len(kept) < 30:
                raise ValueError("Too few paired rows remain after the declared exclusion.")
            alternative = dataset.context(kept, ctx.focus, ctx.assumption)
            result, other = analyze(
                dataset,
                alternative,
                plan_for(alternative, "relationship", fields, "Association without the outer 1% tails"),
            )
            old, new = original.metrics["pearson"], result.metrics["pearson"]
            status = "changed" if abs(new - old) > 0.15 or (new * old < 0 and abs(old) > 0.1) else "similar"
            result.metadata["excluded_row_ids"] = valid.index[~mask].tolist()
            summary = f"Pearson r changes from {number(old)} to {number(new)} after excluding {len(valid) - len(kept):,} paired rows outside either field's 1st–99th percentiles. The original data is preserved."
            chart = other.chart
        elif operation == "rank":
            p, s = original.metrics["pearson"], original.metrics["spearman"]
            status = "changed" if abs(p - s) > 0.2 else "similar"
            summary = f"Pearson r = {number(p)}; Spearman ρ = {number(s)} on the same {original.support:,} paired rows."
            result = original.model_copy(
                update={
                    "id": cid,
                    "records": [{"label": "Pearson r", "value": p}, {"label": "Spearman ρ", "value": s}],
                }
            )
            result.metadata = {**result.metadata, "correlation": True}
            chart = original_chart(finding, result, "dot", summary)
            chart.x_label, chart.y_label = "Correlation coefficient", ""
        elif operation == "quantile_bin_summary":
            result, f = analyze(
                dataset, ctx, plan_for(ctx, operation, fields, "What do conditional medians reveal?")
            )
            summary = f.observation + " Compare this view with the original scatter; binning is a summary."
            chart = f.chart
            status = "not_checked"
        elif operation == "distribution":
            records = original.records
            diffs = [abs(r["mean"] - r["median"]) / max((r["q3"] - r["q1"]), 1e-9) for r in records]
            status = "changed" if max(diffs) > 0.3 else "similar"
            summary = "Means, medians, quartiles and counts are shown together. " + (
                "At least one group's mean differs from its median by more than 0.3 IQR."
                if status == "changed"
                else "The largest mean–median difference is no more than 0.3 IQR."
            )
            result = original
            chart = finding.chart
        elif operation == "missingness":
            group = group_field or next((f for f in dimensions(dataset) if frame[f].nunique() <= 8), None)
            if group is None:
                raise ValueError("No supported group field.")
            mask = frame[fields].isna().any(axis=1)
            records = []
            for label, part in frame.groupby(group, observed=True):
                if len(part) < 20:
                    continue
                m = int(mask.loc[part.index].sum())
                records.append(
                    {
                        "label": str(label),
                        "value": m / len(part),
                        "missing": m,
                        "n": len(part),
                        "row_ids": part.index.tolist(),
                    }
                )
            if len(records) < 2:
                raise ValueError("Not enough supported groups.")
            spread = max(float(r["value"]) for r in records) - min(float(r["value"]) for r in records)
            status = "changed" if spread > 0.1 else "similar"
            summary = f"Missing-pair proportions differ by {spread:.1%} across supported recorded groups. This describes composition, not the missingness mechanism."
            result = ResultArtifact(
                id=cid,
                plan=original.plan,
                records=records,
                support=len(frame),
                metrics={"spread": spread},
                metadata={"group_field": group, "proportion": True},
            )
            chart = original_chart(finding, result, "bar", summary)
            chart.x_label, chart.y_label = "Missing-pair proportion", dataset.label(group)
        elif operation == "resampling":
            valid = paired(frame, fields)
            rng = np.random.default_rng(SEED)
            values = []
            for _ in range(100):
                take = valid.iloc[rng.integers(0, len(valid), len(valid))]
                v = correlations(take, *fields)["pearson"]
                if v is not None:
                    values.append(v)
            lo, hi = np.quantile(values, [0.05, 0.95])
            summary = f"The central 90% of 100 seeded row-resampling values spans {lo:.3g} to {hi:.3g}. This is a diagnostic range, not an inferential confidence interval."
            counts, edges = np.histogram(values, bins=12)
            result = ResultArtifact(
                id=cid,
                plan=original.plan,
                records=[
                    {"x": float((a + b) / 2), "value": int(c), "label": f"{a:.2f}–{b:.2f}"}
                    for a, b, c in zip(edges[:-1], edges[1:], counts)
                ],
                support=100,
                metrics={"low": float(lo), "high": float(hi)},
            )
            chart = original_chart(finding, result, "histogram", summary)
        elif operation == "binning":
            result, other = analyze(
                dataset,
                ctx,
                plan_for(
                    ctx,
                    "distribution",
                    fields,
                    "The same values with different histogram bins",
                    {"bins": max(5, len(original.records) // 2)},
                ),
            )
            chart = other.chart
            status = "not_checked"
            summary = "These are the same recorded values with a different declared bin count. Compare the visible shape; no robustness verdict is inferred."
        elif operation == "residual_spread_by_bin":
            from firstlook.model_checks import residual_spread

            result, chart, summary = residual_spread(dataset, inv)
            status = "not_checked"
        elif operation == "aggregation":
            period = "W" if original.metrics["period"] != "W" else "MS"
            result, f = analyze(
                dataset,
                ctx,
                plan_for(ctx, "time", fields, "A different time aggregation", {"period": period}),
            )
            summary = f"Compare observed means using {original.metrics['period']} and {period} periods. The aggregation changes the question and empty periods remain missing."
            chart = f.chart
            status = "not_checked"
        return ChallengeResult(
            id=cid,
            parent_id=finding.id,
            operation=operation,
            status=status,
            summary=summary,
            result=result,
            chart=chart,
        )
    except (ValueError, TypeError) as exc:
        return ChallengeResult(
            id=cid, parent_id=finding.id, operation=operation, status="insufficient", summary=str(exc)
        )


def original_chart(finding: Finding, result: ResultArtifact, template: Any, alt: str) -> ChartSpec:
    return ChartSpec(
        id=digest([result.id, template]),
        result_id=result.id,
        context=result.plan.context,
        template=template,
        x_label=finding.chart.x_label,
        y_label=finding.chart.y_label,
        alt=alt,
        zero_baseline=template in {"bar", "histogram"},
        rules=finding.chart.rules,
    )  # type: ignore[arg-type]


def automatic_challenges(dataset: Dataset, inv: Investigation) -> None:
    selected = list(inv.findings[:3])
    selected += [f for f in inv.findings if f.family == "metric" and f not in selected][:2]
    for f in selected:
        for op in eligible(dataset, inv, f)[:3]:
            inv.challenges.append(challenge(dataset, inv, f, op))
