"""Full-context recording coverage, never inferred observation completeness."""

from __future__ import annotations

import pandas as pd
from collections import Counter

from firstlook.contracts import ResultArtifact, Finding, ChartSpec, Role, clean, digest


def report(dataset, ctx, time_field=None, fields=None, group_field=None):
    if ctx.id != dataset.context(ctx.row_ids, ctx.focus, ctx.assumption).id:
        raise ValueError("Recording-process scope is stale.")
    frame = dataset.frame.loc[ctx.row_ids]
    times = [f.id for f in dataset.record.fields if f.role == Role.TIME and not f.excluded]
    time_field = time_field or next(iter(times), None)
    if time_field and time_field not in times:
        raise ValueError("Choose an included timestamp for recording coverage.")
    included = [f.id for f in dataset.record.fields if not f.excluded and f.id != time_field]
    selected = (
        list(fields)
        if fields
        else sorted(
            included, key=lambda f: (f != ctx.focus, -int(frame[f].isna().sum()), dataset.field(f).position)
        )[:12]
    )
    if len(selected) > 12 or len(set(selected)) != len(selected) or not set(selected) <= set(included):
        raise ValueError("Coverage supports up to twelve included, distinct fields.")
    label_counts = Counter(dataset.label(fid) for fid in selected)
    labels = {
        fid: dataset.label(fid)
        + (f" [column {dataset.field(fid).position + 1}]" if label_counts[dataset.label(fid)] > 1 else "")
        for fid in selected
    }
    result = {
        "context": ctx.id,
        "active_rows": len(frame),
        "fields": selected,
        "time_field": time_field,
        "time": [],
        "groups": [],
        "category_presence": [],
        "undated_rows": 0,
        "warnings": [
            "Coverage describes recorded values. It does not establish that all events or outcomes were captured."
        ],
        "flags": [],
    }
    if time_field:
        dates = pd.to_datetime(frame[time_field], utc=True, errors="coerce")
        result["undated_rows"] = int(dates.isna().sum())
        valid = frame.loc[dates.notna()].copy()
        valid["__date"] = dates.loc[valid.index]
        span = (dates.max() - dates.min()).days if dates.notna().any() else 0
        frequency = "D" if span <= 60 else "MS" if span <= 1830 else "YS" if span <= 21960 else "10YS"
        result["period"] = frequency
        from firstlook.semantic.model import get_model

        policy = next((p for p in get_model(dataset).time_policies if p.field == time_field), None)
        complete = (
            pd.to_datetime(policy.complete_through, utc=True)
            if policy and policy.confirmed and policy.complete_through
            else None
        )
        categories = [
            f
            for f in selected
            if dataset.field(f).role in {Role.CATEGORY, Role.BOOL, Role.ORDINAL} and frame[f].nunique() <= 12
        ][:2]
        for date, part in valid.groupby(pd.Grouper(key="__date", freq=frequency)):
            if not len(part):
                continue
            period = date.isoformat()
            for fid in selected:
                missing = int(part[fid].isna().sum())
                result["time"].append(
                    {
                        "field": fid,
                        "label": labels[fid],
                        "period": period,
                        "rows": len(part),
                        "missing": missing,
                        "nonmissing": len(part) - missing,
                        "missing_share": missing / len(part),
                        "distinct": int(part[fid].nunique()),
                        "row_ids": part.index.tolist(),
                        "extends_after_complete_through": complete is not None
                        and bool(part["__date"].max() > complete),
                    }
                )
            for fid in categories:
                for value in frame[fid].dropna().unique():
                    count = int(part[fid].eq(value).sum())
                    result["category_presence"].append(
                        {
                            "field": fid,
                            "label": labels[fid],
                            "period": period,
                            "category": str(value),
                            "recorded_rows": count,
                            "period_rows": len(part),
                        }
                    )
        for fid in selected:
            records = [r for r in result["time"] if r["field"] == fid]
            rates = [r["missing_share"] for r in records]
            if len(rates) >= 2 and max(rates) - min(rates) >= 0.25:
                result["flags"].append(
                    {
                        "field": fid,
                        "kind": "coverage_contrast",
                        "range": max(rates) - min(rates),
                        "meaning": "Observed missingness differs across periods; this is a review trigger, not proof of a recording change.",
                    }
                )
        if complete is None:
            result["warnings"].append(
                "No confirmed complete-through date for this timestamp; recent outcomes may be incomplete."
            )
    groups = [
        f.id
        for f in dataset.record.fields
        if f.role in {Role.CATEGORY, Role.BOOL, Role.ORDINAL}
        and not f.excluded
        and 2 <= frame[f.id].nunique() <= 8
    ]
    group_field = group_field or next(iter(groups), None)
    if group_field:
        if group_field not in groups:
            raise ValueError("Choose an included grouping field with two to eight recorded levels.")
        result["group_field"] = group_field
        for value, part in frame.groupby(group_field, dropna=False, observed=True):
            for fid in selected:
                result["groups"].append(
                    {
                        "group": str(value) if not pd.isna(value) else "[Missing group value]",
                        "group_missing": bool(pd.isna(value)),
                        "field": fid,
                        "label": labels[fid],
                        "rows": len(part),
                        "missing": int(part[fid].isna().sum()),
                        "missing_share": float(part[fid].isna().mean()),
                    }
                )
    return clean(result)


def recording_plan(dataset, ctx, fields=None):
    from firstlook.discovery import plan_for

    packet = report(dataset, ctx, fields=fields)
    if not packet["time_field"] or not packet["time"]:
        raise ValueError("Temporal coverage needs recorded timestamps.")
    return plan_for(
        ctx,
        "recording_process",
        [packet["time_field"]] + packet["fields"],
        "How does recorded coverage change across time?",
        {"time_field": packet["time_field"]},
    )


def analyze_recording(dataset, ctx, plan):
    packet = report(dataset, ctx, time_field=plan.params.get("time_field"), fields=plan.fields[1:])
    rows = [
        {
            "x": r["period"],
            "y": r["label"],
            "value": r["missing_share"],
            "n": r["rows"],
            "missing": r["missing"],
            "row_ids": r["row_ids"],
        }
        for r in packet["time"]
    ]
    result = ResultArtifact(
        id=plan.id,
        plan=plan,
        records=rows,
        metrics={
            "active_rows": packet["active_rows"],
            "undated_rows": packet["undated_rows"],
            "review_triggers": len(packet["flags"]),
        },
        support=packet["active_rows"] - packet["undated_rows"],
        missing=packet["undated_rows"],
        warnings=packet["warnings"],
        metadata={
            "proportion": True,
            "recording_report": packet,
            "scope": "All dated rows in the exact active population; each cell's denominator is its recorded period row count.",
        },
    )
    chart = ChartSpec(
        id=digest([plan.id, "coverage"]),
        result_id=plan.id,
        context=ctx.id,
        template="heatmap",
        x_label="Recorded period",
        y_label="Field · proportion missing",
        rules=["SOURCE-01"],
        alt="Missing-value proportions by field and recorded period, with row-count denominators",
    )
    finding = Finding(
        id=plan.id,
        title=plan.question,
        observation=f"Coverage is summarized for {len(packet['fields'])} fields over recorded periods. {len(packet['flags'])} large coverage contrasts are review triggers, not established causes.",
        result_id=plan.id,
        chart=chart,
        family="recording",
        score=0.7,
        limitations=packet["warnings"],
    )
    return result, finding


def compact_packet(dataset, ctx):
    packet = report(dataset, ctx)
    return {
        k: packet[k] for k in ["context", "active_rows", "time_field", "undated_rows", "warnings", "flags"]
    }
