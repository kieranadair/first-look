"""Metric algebra with explicit denominators, source memberships and temporal policies."""

from __future__ import annotations
from typing import Any, cast
from datetime import timedelta
import numpy as np
import pandas as pd
from firstlook.contracts import ChartSpec, Finding, ResultArtifact, clean, digest
from firstlook.semantic_contracts import Metric
from firstlook.semantic.model import get_model
from firstlook.semantic.policy import decision


def _ids(frame):
    if "__source_rows" in frame:
        return sorted({int(i) for ids in frame["__source_rows"] for i in ids})
    return [int(i) for i in frame.index]


def _entity_ids(frame, keys):
    return set(frame[keys].dropna().itertuples(index=False, name=None))


def _scalar(
    dataset, metric: Metric, part: pd.DataFrame, whole: pd.DataFrame, group_keys=None
) -> dict[str, Any]:
    model = get_model(dataset)
    if metric.aggregation == "ratio":
        numerator = _scalar(dataset, model.metric(metric.numerator or ""), part, whole, group_keys)
        denom_part = part if metric.denominator_scope == "group" else whole
        denominator = _scalar(
            dataset,
            model.metric(metric.denominator or ""),
            denom_part,
            whole,
            group_keys if metric.denominator_scope == "group" else None,
        )
        d = denominator["value"]
        n = numerator["value"]
        if d is None or d <= 0:
            return {
                "value": None,
                "numerator": n,
                "denominator": d,
                "n": numerator["n"],
                "undefined": "Nonpositive or missing denominator",
            }
        return {"value": None if n is None else n / d, "numerator": n, "denominator": d, "n": numerator["n"]}
    original = part
    if metric.aggregation == "count_rows":
        return {"value": len(part) if len(part) else None, "n": len(part)}
    entity = model.entity(metric.entity or "") if metric.entity else None
    if metric.aggregation == "count_distinct":
        assert entity is not None
        n = len(_entity_ids(part, entity.keys))
        return {"value": n if len(part) else None, "n": n}
    if entity and metric.aggregation in {"sum", "mean", "median", "weighted_mean"}:
        part = part.dropna(subset=entity.keys).drop_duplicates(entity.keys)
    values = part[metric.field]
    valid = values.dropna().astype(float)
    n = len(valid)
    if metric.aggregation == "sum":
        value = valid.sum() if n else None
        if entity and group_keys and metric.allocation == "equal":
            columns = list(dict.fromkeys(entity.keys + group_keys))
            memberships = whole.dropna(subset=columns).drop_duplicates(columns)
            frequencies = memberships.groupby(entity.keys, dropna=False).size().to_dict()
            unique = original.dropna(subset=list(dict.fromkeys(columns + [metric.field]))).drop_duplicates(
                columns
            )
            value = (
                sum(
                    float(r[metric.field])
                    / frequencies[
                        tuple(r[k] for k in entity.keys) if len(entity.keys) > 1 else r[entity.keys[0]]
                    ]
                    for _, r in unique.iterrows()
                )
                if len(unique)
                else None
            )
    elif metric.aggregation == "mean":
        value = valid.mean() if n else None
    elif metric.aggregation == "median":
        value = valid.median() if n else None
    elif metric.aggregation == "weighted_mean":
        paired = part[list(dict.fromkeys([metric.field, metric.weight]))].dropna()
        weight = paired[metric.weight].astype(float)
        if weight.sum() <= 0:
            raise ValueError("A weighted mean requires positive total exposure/weight.")
        value = float(np.average(paired[metric.field], weights=weight))
        n = len(paired)
        return {"value": value, "n": n, "weight_sum": float(weight.sum())}
    elif metric.aggregation == "average_per_entity":
        assert entity is not None
        usable = part.dropna(subset=entity.keys + [metric.field])
        n = len(_entity_ids(usable, entity.keys))
        numerator = float(usable[metric.field].sum())
        return {"value": numerator / n if n else None, "n": n, "numerator": numerator, "denominator": n}
    elif metric.aggregation == "snapshot_last":
        assert entity is not None
        last = (
            part.dropna(subset=entity.keys).sort_values("__time").groupby(entity.keys, dropna=False).tail(1)
        )
        value = last[metric.field].sum(min_count=len(last)) if len(last) else None
        n = int(last[metric.field].notna().sum())
    elif metric.aggregation == "delta":
        valid = part["__delta"].dropna()
        value = valid.sum() if len(valid) else None
        n = len(valid)
    elif metric.aggregation == "circular_mean":
        from scipy.stats import circmean

        resultant = abs(np.exp(1j * np.deg2rad(valid)).mean()) if n else 0.0
        value = float(circmean(valid, high=360, low=0)) % 360 if n and resultant > 1e-8 else None
    else:
        raise ValueError("Unsupported metric operation.")
    result = {"value": clean(value), "n": int(n)}
    if len(original) != len(part):
        result["deduplicated_rows"] = len(original) - len(part)
    return result


def _transform(records: list[dict], transform: str, time_view: bool) -> list[str]:
    warnings = []
    if transform == "identity":
        return warnings
    values = np.array([r["value"] if r["value"] is not None else np.nan for r in records], dtype=float)
    finite = np.isfinite(values)
    if transform == "log":
        if (values[finite] <= 0).any():
            raise ValueError(
                "Log transformation requires positive values; zeros and losses are not silently removed or shifted."
            )
        values[finite] = np.log(values[finite])
    elif transform == "sqrt":
        if (values[finite] < 0).any():
            raise ValueError("Square-root transformation requires nonnegative values.")
        values[finite] = np.sqrt(values[finite])
    elif transform == "zscore":
        if finite.sum() < 2 or np.std(values[finite]) == 0:
            raise ValueError("Standardization needs at least two varying values.")
        values[finite] = (values[finite] - values[finite].mean()) / values[finite].std(ddof=0)
        warnings.append(
            "Display standardization is fitted on these aggregates; it is not a model preprocessing artifact."
        )
    elif transform in {"difference", "percent_change"}:
        if not time_view:
            raise ValueError("Changes require temporal ordering.")
        previous = np.roll(values, 1)
        previous[0] = np.nan
        if transform == "difference":
            values = values - previous
        else:
            out = np.full(len(values), np.nan)
            usable = np.isfinite(previous) & (previous != 0) & finite
            out[usable] = (values[usable] - previous[usable]) / np.abs(previous[usable])
            values = out
            warnings.append(
                "Relative change uses the absolute previous value; zero/missing predecessors remain unavailable."
            )
    else:
        raise ValueError("Unsupported transformation.")
    for row, value in zip(records, values):
        row["original_value"] = row["value"]
        row["value"] = clean(float(value))
    return warnings


def _counter_frame(dataset, metric, frame, time_field):
    entity = get_model(dataset).entity(metric.entity)
    ordered = frame.dropna(subset=entity.keys + [time_field]).sort_values(entity.keys + [time_field]).copy()
    if ordered.duplicated(entity.keys + [time_field]).any():
        raise ValueError("Counter differences require one reading per entity and instant.")
    grouped = ordered.groupby(entity.keys, dropna=False)
    ordered["__delta"] = grouped[metric.field].diff()
    # Source membership includes both ends of each measured interval.
    previous = {}
    for _, group in grouped:
        last = None
        for i in group.index:
            previous[i] = [] if last is None else [int(last), int(i)]
            last = i
    ordered["__source_rows"] = [previous[i] for i in ordered.index]
    resets = int((ordered["__delta"] < 0).sum())
    ordered.loc[ordered["__delta"] < 0, "__delta"] = np.nan
    return ordered, resets


def evaluate(dataset, ctx, plan):
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _evaluate(dataset, ctx, plan)
    except ArithmeticError as exc:
        raise ValueError(
            "Metric arithmetic exceeded a finite numerical domain. Review magnitude, weights and units."
        ) from exc


def _evaluate(dataset, ctx, plan):
    model = get_model(dataset)
    if plan.context != ctx.id or ctx.dataset != dataset.record.fingerprint:
        raise ValueError("The metric plan has a stale context.")
    if ctx.semantics != dataset.context([], ctx.focus, ctx.assumption).semantics:
        raise ValueError("Field meanings or semantic contract changed; recompute this plan.")
    if (
        not ctx.row_ids
        or len(set(ctx.row_ids)) != len(ctx.row_ids)
        or not set(ctx.row_ids) <= set(dataset.frame.index)
    ):
        raise ValueError("A metric needs valid, distinct active row identities.")
    mid = str(plan.params.get("metric", ""))
    metric = model.metric(mid).model_copy(deep=True)
    if plan.params.get("variant") == "recorded_mean":
        if metric.aggregation != "average_per_entity":
            raise ValueError("This comparison requires an entity-average definition.")
        metric.aggregation = "mean"
        metric.entity = None
        metric.transform = "identity"
    elif plan.params.get("variant") == "group_denominator":
        if metric.aggregation != "ratio":
            raise ValueError("A denominator comparison requires a ratio metric.")
        metric.denominator_scope = "group"
    group_by = list(plan.params.get("group_by", []))
    if set(plan.params) - {"metric", "group_by", "time_field", "period", "limit", "variant"}:
        raise ValueError("Unknown metric parameters are not executable.")
    if plan.params.get("variant") not in {
        None,
        "recorded_mean",
        "group_denominator",
        "preserve_gaps",
    }:
        raise ValueError("Unknown metric comparison variant.")
    time_field = plan.params.get("time_field")
    period = str(plan.params.get("period", "MS"))
    if period not in {"D", "W", "MS"}:
        raise ValueError("Unsupported aggregation period.")
    check = decision(dataset, metric, group_by, time_field, ctx.row_ids)
    if check.status != "allowed":
        raise ValueError(" ".join(check.reasons + check.requirements))
    frame = dataset.frame.loc[ctx.row_ids]
    warnings = list(check.warnings)
    if metric.field and frame[metric.field].isna().any():
        warnings.append(
            f"{int(frame[metric.field].isna().sum())} value observations are missing. Summaries use recorded values; entity averages require at least one recorded value per counted entity. Unknown amounts are not structural zeros."
        )
    records: list[dict[str, Any]] = []
    metric_groups = []
    missing_group = int(frame[group_by].isna().any(axis=1).sum()) if group_by else 0
    if missing_group:
        warnings.append(
            f"{missing_group:,} rows have unassigned grouping values; the active-population denominator retains them when eligible."
        )
    limit = max(2, min(20, int(plan.params.get("limit", 12))))
    if time_field:
        if group_by:
            raise ValueError(
                "Use one time series per metric view; select a subgroup as a new context to compare it."
            )
        policy = next((t for t in model.time_policies if t.id == metric.time_policy), None)
        if policy is None:
            policy = next((t for t in model.time_policies if t.field == time_field), None)
        if policy and policy.field != time_field:
            raise ValueError("Metric and selected time policy refer to different timestamps.")
        working = frame.dropna(subset=[time_field]).copy()
        if working.empty:
            raise ValueError("No timestamped observations.")
        span_days = (working[time_field].max() - working[time_field].min()).days
        if span_days > {"D": 1199, "W": 8393, "MS": 36500}[period]:
            raise ValueError(
                "This time view exceeds the 1,200-period budget. Choose a coarser period or a narrower active context."
            )
        if metric.aggregation == "delta":
            working, resets = _counter_frame(dataset, metric, working, time_field)
            warnings.append(
                f"Counter differences use consecutive readings; {resets} negative/reset intervals remain missing. Values are assigned to the ending observation, not spread over unobserved days."
            )
        working["__time"] = working[time_field]
        if (
            metric.aggregation == "snapshot_last"
            and working.duplicated(model.entity(metric.entity or "").keys + [time_field]).any()
        ):
            raise ValueError("Snapshot selection requires unambiguous entity/timestamp observations.")
        # Filling is performed at the declared series grain, before time aggregation.
        fill = policy.gap_policy if policy and policy.confirmed else "preserve"
        coverage_scope = set(ctx.row_ids) == set(dataset.frame.index)
        if fill != "preserve" and not coverage_scope:
            fill = "preserve"
            warnings.append(
                "Observation coverage was declared for the whole upload. Gap filling is disabled for this arbitrary selected-row context; coverage has not been re-established for it."
            )
        if plan.params.get("variant") == "preserve_gaps":
            fill = "preserve"
        if fill != "preserve":
            assert policy is not None
            if {"D": 1, "W": 7, "MS": 28}[period] < {"D": 1, "2D": 2, "W": 7, "MS": 28}.get(
                policy.expected_frequency, 1
            ):
                raise ValueError("A filled time view cannot be finer than the declared observation schedule.")
            if metric.aggregation == "ratio" or metric.transform in {"difference", "percent_change"}:
                raise ValueError("Gap filling must be applied to a base metric before ratios or changes.")
            if metric.aggregation in {"sum", "average_per_entity"} and fill != "zero":
                raise ValueError("An additive event metric cannot be interpolated or carried forward.")
            if metric.aggregation == "delta":
                raise ValueError(
                    "Counter intervals cannot be filled as daily consumption without an allocation model."
                )
            if fill == "zero" and metric.aggregation not in {"sum", "count_rows", "count_distinct"}:
                raise ValueError("Structural zeros are supported for event amounts and counts.")
            if metric.aggregation == "snapshot_last" and not set(
                model.entity(metric.entity or "").keys
            ) <= set(policy.series):
                raise ValueError("Fill snapshots at the entity series grain, not across a pooled total.")
        series = policy.series if policy and fill != "preserve" else []
        grouped = (
            [("", working)]
            if not series
            else list(working.dropna(subset=series).groupby(series, dropna=False))
        )
        if len(grouped) > 200:
            raise ValueError("At most 200 source series may be expanded in one view.")
        filled = []
        cells = 0
        synthetic = 0
        for series_key, source in grouped:
            frequency = policy.expected_frequency if fill != "preserve" and policy else period
            frequency = "W-MON" if frequency == "W" else frequency
            frequency = "B" if policy and policy.calendar == "business" and frequency == "D" else frequency
            buckets = []
            for stamp, part in source.groupby(
                cast(Any, pd.Grouper)(key=time_field, freq=frequency, label="left", closed="left")
            ):
                buckets.append(
                    {
                        "stamp": stamp,
                        **_scalar(dataset, metric, part, working),
                        "row_ids": _ids(part),
                        "source_rows": len(part),
                    }
                )
            if not buckets:
                continue
            table = pd.DataFrame(buckets).set_index("stamp")
            table["__series"] = digest(str(series_key))
            if fill != "preserve":
                assert policy is not None
                end = (
                    max(
                        table.index.max(),
                        working[time_field].max().normalize(),
                        pd.Timestamp(policy.complete_through).as_unit("ns"),
                    )
                    if policy.complete_through
                    else max(table.index.max(), working[time_field].max().normalize())
                )
                start = working[time_field].min().normalize()
                if frequency not in {"D", "B", "2D"}:
                    start = table.index.min()
                index = pd.date_range(start, end, freq=frequency)
                if (
                    policy.kind != "event"
                    and frequency == "2D"
                    and not source[time_field].dt.normalize().isin(index).all()
                ):
                    raise ValueError(
                        "Observed readings do not align with the declared two-day schedule. Preserve gaps or correct the schedule; observations cannot be moved silently."
                    )
                cells += len(index)
                if cells > 20000:
                    raise ValueError("The declared schedule exceeds the 20,000-cell expansion budget.")
                table = table.reindex(index)
                table["row_ids"] = table["row_ids"].map(lambda ids: ids if isinstance(ids, list) else [])
                absent = table["source_rows"].isna() | table["source_rows"].eq(0)
                table["source_rows"] = table["source_rows"].fillna(0)
                table["__series"] = digest(str(series_key))
                original = table["value"].copy()
                if fill == "zero":
                    assert policy.complete_through is not None
                    eligible = absent & (table.index <= pd.Timestamp(policy.complete_through).as_unit("ns"))
                    table.loc[eligible, "value"] = 0.0
                else:
                    # Explicit NULL observations break carry/interpolation. Fill absent rows only.
                    # NULL observations are barriers, not implicit scheduled gaps.
                    barriers = (~absent & original.isna()).cumsum()
                    candidates = original.copy()
                    for _, segment in original.groupby(barriers):
                        candidate = (
                            segment.ffill(limit=policy.max_gap_periods)
                            if fill == "forward_fill"
                            else segment.interpolate(method="time", limit_area="inside")
                        )
                        if fill == "interpolate":
                            runs = segment.isna().ne(segment.isna().shift()).cumsum()
                            run_lengths = segment.isna().groupby(runs).transform("sum")
                            candidate = candidate.mask(
                                segment.isna() & run_lengths.gt(policy.max_gap_periods)
                            )
                        candidates.loc[segment.index] = candidate
                    table.loc[absent, "value"] = candidates.loc[absent]
                table["synthetic"] = absent & table["value"].notna()
                synthetic += int(table["synthetic"].sum())
            else:
                table["synthetic"] = False
            table["n"] = table["n"].fillna(0)
            filled.append(table)
        if not filled:
            raise ValueError("No supported temporal buckets.")
        expanded = pd.concat(filled).sort_index()
        period_frequency = "W-MON" if period == "W" else period
        for stamp, part in expanded.groupby(
            cast(Any, pd.Grouper)(freq=period_frequency, label="left", closed="left")
        ):
            stamp = cast(Any, stamp)
            if len(records) >= 1200:
                raise ValueError("Time view exceeds 1,200 periods.")
            valid = part["value"].dropna()
            # Additive quantities can reaggregate sufficient amounts/counts; other
            # metrics are recomputed on original rows rather than averaging summaries.
            source_ids = sorted({i for ids in part["row_ids"] for i in ids})
            if fill != "preserve":
                if metric.aggregation in {"sum", "count_rows", "count_distinct"}:
                    end = stamp + pd.tseries.frequencies.to_offset(period_frequency)
                    raw = working[(working[time_field] >= stamp) & (working[time_field] < end)]
                    value = (
                        _scalar(dataset, metric, raw, working)["value"]
                        if len(raw)
                        else 0.0
                        if len(valid) == len(part) and len(part)
                        else None
                    )
                    source_ids = _ids(raw)
                elif metric.aggregation == "snapshot_last":
                    last = part.groupby("__series", sort=False).tail(1)
                    value = last["value"].sum(min_count=len(grouped)) if len(last) == len(grouped) else None
                elif len(part) == 1:
                    value = part["value"].iloc[0]
                else:
                    raise ValueError(
                        "This gap-filled summary cannot be rolled up by summing or averaging. Choose the native period or an explicit weighted definition."
                    )
                item = {"value": clean(value), "n": int(part["n"].sum())}
            else:
                # Original rows are selected by time, not repeated interval-source IDs.
                end = stamp + pd.tseries.frequencies.to_offset(period_frequency)
                raw = working[(working[time_field] >= stamp) & (working[time_field] < end)]
                item = _scalar(dataset, metric, raw, working) if len(raw) else {"value": None, "n": 0}
                source_ids = _ids(raw)
            records.append(
                {
                    "x": stamp,
                    **item,
                    "row_ids": source_ids,
                    "synthetic": bool(part["synthetic"].any()),
                    "complete": bool(
                        policy
                        and coverage_scope
                        and stamp >= working[time_field].min().normalize()
                        and policy.coverage_complete
                        and policy.complete_through
                        and stamp + pd.tseries.frequencies.to_offset(period_frequency)
                        <= pd.Timestamp(policy.complete_through).to_pydatetime() + timedelta(days=1)
                    ),
                }
            )
        if synthetic:
            warnings.append(
                f"{synthetic} absent scheduled observations were filled under the confirmed {fill} policy; original rows were not changed."
            )
        if policy and not policy.coverage_complete:
            warnings.append(
                "Time coverage is unconfirmed; empty periods remain unknown and a partial last period is possible."
            )
        template = "line"
        x_label = dataset.label(time_field)
        y_label = metric.label
    else:
        source = frame.dropna(subset=group_by) if group_by else frame
        parts = (
            [("Active population", source)]
            if not group_by
            else list(source.groupby(group_by, dropna=False, observed=True, sort=True))
        )
        parts.sort(key=lambda pair: -len(pair[1]))
        if len(parts) > limit:
            shown = parts[: limit - 1]
            others = pd.concat([p for _, p in parts[limit - 1 :]])
            parts = shown + [("Other recorded groups", others)]
            warnings.append(
                "Other is recomputed from the union of source rows, not a sum of displayed subgroup statistics."
            )
        for label, part in parts:
            text = " · ".join(str(v) for v in label) if isinstance(label, tuple) else str(label)
            scalar = _scalar(dataset, metric, part, frame, group_by)
            records.append({"label": text, **scalar, "row_ids": _ids(part)})
            metric_groups.append(part)
        template = "bar"
        x_label = metric.label
        y_label = " / ".join(dataset.label(f) for f in group_by) or "Active population"
    if not records or all(r["value"] is None for r in records):
        raise ValueError("No defined metric values in this context.")
    if any(r.get("undefined") for r in records):
        warnings.append("Groups with nonpositive or missing denominators remain undefined.")
    # Explicit full-credit/equal allocation of entity-valued amounts across groups.
    if metric.entity and metric.aggregation == "sum" and group_by and not time_field:
        entity = model.entity(metric.entity or "")
        memberships = frame.dropna(subset=entity.keys + group_by).drop_duplicates(entity.keys + group_by)
        counts = memberships.groupby(entity.keys, dropna=False).size()
        overlap = int((counts > 1).sum())
        if overlap and metric.allocation == "none":
            raise ValueError(
                "The value entity belongs to overlapping groups. Declare full-credit or equal allocation before totaling by these groups."
            )
        if overlap:
            warnings.append(f"{overlap} entities overlap groups; attribution policy is {metric.allocation}.")
    for r in records:
        if r["value"] is not None and not np.isfinite(float(r["value"])):
            raise ValueError("Metric arithmetic exceeded a finite numerical domain.")
    warnings += _transform(records, metric.transform, bool(time_field))
    if metric.transform != "identity":
        x_label = (metric.transform + " of " + metric.label) if not time_field else x_label
        y_label = (metric.transform + " of " + metric.label) if time_field else y_label
    values = [float(r["value"]) for r in records if r["value"] is not None]
    overlap = 0
    if (
        metric.aggregation == "ratio"
        and metric.numerator == metric.denominator
        and metric.denominator_scope == "active_population"
        and metric_groups
    ):
        base = model.metric(metric.numerator or "")
        if base.entity:
            entity = model.entity(base.entity)
            seen = set()
            for part in metric_groups:
                members = _entity_ids(part, entity.keys)
                overlap += len(seen & members)
                seen |= members
        nonnegative_base = not base.field or bool(frame[base.field].dropna().ge(0).all())
        composition = bool(
            not overlap
            and not missing_group
            and nonnegative_base
            and min(values) >= 0
            and np.isclose(sum(values), 1)
        )
        warnings.append(
            "Groups form an observed nonnegative partition of this denominator."
            if composition
            else "These groups are not a verified complete partition of the denominator; do not present them as a 100% composition."
        )
    else:
        composition = False
    result = ResultArtifact(
        id=plan.id,
        plan=plan,
        records=clean(records),
        metrics=clean(
            {
                "metric": metric.id,
                "groups": len(records),
                "overlap_memberships": overlap,
                "sum_of_displayed_values": sum(values),
                "composition": composition,
            }
        ),
        support=len(frame),
        missing=missing_group,
        warnings=list(dict.fromkeys(warnings)),
        metadata=clean(
            {
                "semantic_revision": model.revision,
                "definition": metric.model_dump(mode="json"),
                "time_axis": bool(time_field),
                "proportion": metric.aggregation == "ratio"
                and metric.numerator == metric.denominator
                and min(values) >= 0
                and max(values) <= 1
                and metric.transform == "identity",
                "composition": composition,
                "transform_stage": "after_aggregation",
                "selection_semantics": "Recorded member rows of a displayed group or period. Missing-value exclusions and denominator population remain explicit; a counter interval links both endpoint readings.",
                "quantity_unit": model.meaning(metric.field).unit if metric.field else "",
                "population_rows": len(frame),
                "decision": check.model_dump(mode="json"),
            }
        ),
    )
    observation = f"{metric.label} is computed for {len(records)} displayed groups/periods using {metric.aggregation.replace('_', ' ')}. The definition and active population are recorded."
    if overlap:
        observation += f" {overlap} group memberships overlap at the counted entity grain."
    chart = ChartSpec(
        id=digest([plan.id, template]),
        result_id=result.id,
        context=ctx.id,
        template=template,
        x_label=x_label,
        y_label=y_label,
        zero_baseline=template == "bar",
        alt=observation,
        rules=["SEM-GRAIN", "SEM-AGG", "SEM-DENOM", "SOURCE-01", "SCALE-01"]
        + (["SEM-TIME"] if time_field else [])
        + (["SEM-UNIT"] if metric.transform != "identity" else []),
    )
    finding = Finding(
        id=plan.id,
        title=plan.question,
        observation=observation,
        result_id=result.id,
        chart=chart,
        family="metric",
        score=0.85,
        limitations=result.warnings
        + ["Exploratory evidence under a scoped semantic contract; no causal conclusion."],
    )
    return result, finding
