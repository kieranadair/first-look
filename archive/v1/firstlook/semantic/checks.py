"""Counterfactual definitions are explicit sensitivity checks, never corrections to facts."""

from __future__ import annotations
import numpy as np
from firstlook.contracts import ChallengeResult, digest
from firstlook.semantic.model import get_model
from firstlook.semantic.planner import metric_plan

LABELS = {
    "semantic_reconciliation": "Reconcile groups with the population",
    "semantic_unit": "Compare row and entity averaging",
    "semantic_denominator": "Change the denominator scope",
    "semantic_gaps": "Compare with unfilled scheduled gaps",
    "semantic_time_aggregation": "Compare semantic time aggregation",
}


def eligible(dataset, result):
    metric = get_model(dataset).metric(str(result.plan.params["metric"]))
    out = []
    if result.plan.params.get("group_by"):
        out.append("semantic_reconciliation")
    if metric.aggregation == "average_per_entity":
        out.append("semantic_unit")
    if metric.aggregation == "ratio" and metric.denominator_scope == "active_population":
        out.append("semantic_denominator")
    if result.plan.params.get("time_field"):
        out.append("semantic_time_aggregation")
        policy = next(
            (
                t
                for t in get_model(dataset).time_policies
                if t.id == metric.time_policy or t.field == result.plan.params["time_field"]
            ),
            None,
        )
        if policy and policy.gap_policy != "preserve":
            out.append("semantic_gaps")
    return out


def check(dataset, inv, finding, operation, group_field=None):
    from firstlook.discovery import analyze

    original = inv.results[finding.result_id]
    plan = original.plan
    metric = get_model(dataset).metric(str(plan.params["metric"]))
    cid = digest([finding.id, operation, group_field])
    result = chart = None
    try:
        groups = list(plan.params.get("group_by", []))
        time = plan.params.get("time_field")
        period = plan.params.get("period", "MS")
        if operation == "semantic_time_aggregation":
            alternate_period = "W" if period != "W" else "MS"
            result, other = analyze(
                dataset,
                inv.context,
                metric_plan(
                    dataset,
                    inv.context,
                    metric.id,
                    groups,
                    time,
                    alternate_period,
                    question=LABELS[operation],
                ),
            )
            return ChallengeResult(
                id=cid,
                parent_id=finding.id,
                operation=operation,
                status="not_checked",
                summary=f"The approved metric is recomputed from source components at {period} and {alternate_period} resolution. Different periods answer different questions; no change verdict is inferred from aligned list positions.",
                result=result,
                chart=other.chart,
            )
        if operation == "semantic_reconciliation":
            base = (
                get_model(dataset).metric(metric.denominator or "")
                if metric.aggregation == "ratio"
                else metric
            )
            total, _ = analyze(
                dataset,
                inv.context,
                metric_plan(dataset, inv.context, base.id, question="Population denominator"),
            )
            population = total.records[0]["value"]
            displayed = float(sum(r["value"] for r in original.records if r["value"] is not None))
            reference = (
                1.0
                if metric.aggregation == "ratio" and metric.numerator == metric.denominator
                else population
            )
            comparable = metric.aggregation in {"sum", "count_rows", "count_distinct"} or (
                metric.aggregation == "ratio" and metric.numerator == metric.denominator
            )
            if not comparable:
                return ChallengeResult(
                    id=cid,
                    parent_id=finding.id,
                    operation=operation,
                    status="not_checked",
                    summary="This statistic is not additive. Group means, medians and arbitrary rates are not reconciled by summing them; use their source components.",
                )
            same = bool(np.isclose(displayed, reference))
            return ChallengeResult(
                id=cid,
                parent_id=finding.id,
                operation=operation,
                status="similar" if same else "changed",
                result=total,
                summary=f"Displayed groups sum to {displayed:,.6g}; population reference is {reference:,.6g}. "
                + (
                    "The displayed arithmetic reconciles in this context; this does not establish a domain hierarchy."
                    if same
                    else "Inspect overlapping membership, missing group labels and attribution. Group incidence need not partition the population."
                ),
            )
        variant = {
            "semantic_unit": "recorded_mean",
            "semantic_denominator": "group_denominator",
            "semantic_gaps": "preserve_gaps",
        }[operation]
        alternative = metric_plan(
            dataset,
            inv.context,
            metric.id,
            groups,
            time,
            period,
            question=LABELS[operation],
            variant=variant,
            **{
                k: v
                for k, v in plan.params.items()
                if k in {"anchor", "fixed_groups", "denominator", "ranking"}
            },
            **(
                {
                    "fixed_groups": [
                        {
                            "key": r["key"],
                            "label": r["label"],
                            "values": r.get("group_values", []),
                            "other": r.get("other", False),
                        }
                        for r in original.records
                    ]
                }
                if not time
                and "fixed_groups" not in plan.params
                and all("key" in r for r in original.records)
                else {}
            ),
        )
        result, other = analyze(dataset, inv.context, alternative)
        chart = other.chart

        def values_by_key(rows):
            return {r.get("key", str(r.get("x", r.get("label")))): r["value"] for r in rows}

        before_map, after_map = values_by_key(original.records), values_by_key(result.records)
        before = [before_map[k] for k in sorted(before_map)]
        after = [after_map[k] for k in sorted(after_map)]
        same = before_map.keys() == after_map.keys() and all(
            (a is None and b is None) or (a is not None and b is not None and bool(np.isclose(a, b)))
            for a, b in zip(before, after)
        )
        explanations = {
            "semantic_unit": "Equal row weighting and total amount per distinct entity answer different questions.",
            "semantic_denominator": "The alternative uses a denominator inside each displayed group rather than the active population.",
            "semantic_gaps": "The alternative preserves absent scheduled observations as unknown. Original recorded values remain unchanged.",
        }
        return ChallengeResult(
            id=cid,
            parent_id=finding.id,
            operation=operation,
            status="similar" if same else "changed",
            summary=(
                "Values agree in this context. "
                if same
                else "Values or availability change under this definition. "
            )
            + explanations[operation],
            result=result,
            chart=chart,
        )
    except (ValueError, KeyError, TypeError) as exc:
        return ChallengeResult(
            id=cid, parent_id=finding.id, operation=operation, status="insufficient", summary=str(exc)
        )
