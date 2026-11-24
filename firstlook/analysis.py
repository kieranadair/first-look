"""A small finite analysis engine. Meaning changes calculations, never source values."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

from firstlook.types import ChoiceRequired, Comparison, Meaning, Request, Result, TimeRule, clean, digest


def _rows(ds, rows):
    ids = list(ds.frame.index) if rows is None else list(rows)
    if (
        not ids
        or len(ids) != len(set(ids))
        or any(
            isinstance(i, bool) or not isinstance(i, (int, np.integer)) or i not in ds.frame.index
            for i in ids
        )
    ):
        raise ValueError("Choose a nonempty set of distinct source records.")
    return sorted(int(i) for i in ids)


def context_id(ds, meanings=None, rows=None, time_rules=None):
    return digest(
        {
            "source": ds.fingerprint,
            "parser": ds.parser,
            "fields": ds.fields,
            "meanings": meanings or {},
            "rows": _rows(ds, rows),
            "time_rules": time_rules or {},
        }
    )


def _meaning(meanings, fid):
    value = (meanings or {}).get(fid, Meaning())
    return Meaning(**value) if isinstance(value, dict) else value


def _edges(values):
    values = values.dropna().astype(float)
    if not len(values):
        return np.array([0.0, 1.0])
    return np.histogram_bin_edges(values, bins=min(30, max(1, int(np.sqrt(len(values))))))


def _hist(values, edges):
    values = values.dropna().astype(float)
    counts, _ = np.histogram(values, bins=edges)
    return [
        {
            "low": float(a),
            "high": float(b),
            "count": int(n),
            "share": float(n / len(values)) if len(values) else None,
        }
        for a, b, n in zip(edges[:-1], edges[1:], counts)
    ]


def _summary(values):
    s = values.dropna().astype(float)
    return clean(
        {
            "n": len(s),
            "missing": int(values.isna().sum()),
            "min": s.min(),
            "q1": s.quantile(0.25),
            "median": s.median(),
            "mean": s.mean(),
            "q3": s.quantile(0.75),
            "max": s.max(),
        }
    )


def _groups(series):
    missing = "(Missing values)"
    existing = set(series.dropna().astype(str))
    while missing in existing:
        missing += " — unrecorded"
    return series.map(lambda v: missing if pd.isna(v) else str(v))


def _value(ds, part, whole, request, meanings, group_column=None, group_label=None, cache=None):
    cache = {} if cache is None else cache
    if request.metric == "count":
        return len(part), len(part)
    if request.metric == "distinct":
        if not request.entity:
            raise ChoiceRequired("What recorded identifier should I count?", request.x)
        ds.field(request.entity)
        return int(part[request.entity].nunique()), int(part[request.entity].notna().sum())
    fid = request.y if request.view == "time" else request.x
    if request.view == "categories":
        fid = request.y
    if not fid or ds.field(fid).kind != "number":
        raise ValueError("Choose a numerical quantity for this summary.")
    meaning = _meaning(meanings, fid)
    entity = request.entity or meaning.entity
    if request.entity and meaning.entity and request.entity != meaning.entity:
        raise ValueError("This summary's value grain conflicts with the declared meaning.")
    if request.metric == "sum" and meaning.kind != "additive":
        raise ChoiceRequired(
            "Does this quantity describe amounts that can be added? Recorded values remain available while you decide.",
            fid,
            {
                "alternatives": [
                    "Amounts on recorded rows",
                    "Values repeated from an identifier",
                    "Rates, balances or another nonadditive quantity",
                ]
            },
        )
    use = part
    if entity:
        ds.field(entity)
        usable = ds.frame.dropna(subset=[entity])
        varying_key = (entity, fid, "varying")
        if varying_key not in cache:
            cache[varying_key] = usable.groupby(entity, dropna=False)[fid].nunique(dropna=False)
        varying = cache[varying_key]
        if varying.max() > 1:
            raise ChoiceRequired(
                "This value varies within the selected identifier. Counting it once would discard different values.",
                fid,
                {"entity": entity, "violating_entities": int((varying > 1).sum())},
            )
        use = part.dropna(subset=[entity]).drop_duplicates(entity)
        if request.metric == "sum" and group_column:
            membership_key = (entity, group_column, "memberships")
            if membership_key not in cache:
                cache[membership_key] = whole.dropna(subset=[entity]).groupby(entity)[group_column].nunique()
            memberships = cache[membership_key]
            if (memberships > 1).any() and request.attribution == "none":
                raise ChoiceRequired(
                    "Some identifiers belong to several groups. Should their amount count fully in each group, or be shared across groups?",
                    fid,
                    {"entity": entity, "overlapping_entities": int((memberships > 1).sum())},
                )
            if request.attribution == "equal":
                valid = use.dropna(subset=[fid])
                return float(
                    sum(row[fid] / memberships.loc[row[entity]] for _, row in valid.iterrows())
                ) if len(valid) else None, len(valid)
    values = use[fid].dropna().astype(float)
    if request.metric == "weighted_mean":
        if not request.weight or ds.field(request.weight).kind != "number":
            raise ChoiceRequired("Which quantity represents the intended weight or exposure?", fid)
        if (
            entity
            and ds.frame.dropna(subset=[entity]).groupby(entity)[request.weight].nunique(dropna=False).max()
            > 1
        ):
            raise ValueError("The weight varies within the declared value identifier.")
        paired = use[[fid, request.weight]].dropna()
        weights = paired[request.weight].astype(float)
        if (weights < 0).any() or weights.sum() <= 0:
            raise ValueError("Weights must be nonnegative with positive total exposure.")
        return float(np.average(paired[fid], weights=weights)), len(paired)
    if not len(values):
        return None, 0
    return float({"sum": values.sum, "mean": values.mean, "median": values.median}[request.metric]()), len(
        values
    )


def _relationship(part, x, y):
    paired = part[[x, y]].dropna()
    correlation = None
    if len(paired) >= 3 and paired[x].nunique() > 1 and paired[y].nunique() > 1:
        correlation = float(paired[x].corr(paired[y]))
    return {"n": len(paired), "correlation": correlation}


def _quantity_definition(ds, request, meanings):
    if request.metric == "count":
        return "Count of recorded rows"
    if request.metric == "distinct":
        return "Distinct nonmissing " + ds.label(request.entity)
    meaning = _meaning(meanings, request.y)
    entity = request.entity or meaning.entity
    unit = meaning.unit or ds.field(request.y).unit
    grain = "one nonmissing value per " + ds.label(entity) if entity else "nonmissing recorded row values"
    description = (
        request.metric.replace("_", " ")
        + " of "
        + ds.label(request.y)
        + (" (" + unit + ")" if unit else "")
        + ", using "
        + grain
    )
    if request.metric == "weighted_mean":
        description += ", weighted by " + ds.label(request.weight)
    if entity and request.metric == "sum" and request.attribution != "none":
        description += "; each entity contributes " + (
            "equally across its recorded groups"
            if request.attribution == "equal"
            else "its full amount in every recorded group"
        )
    return description


def analyze(ds, request, meanings=None, rows=None, time_rules=None, edges=None) -> Result:
    if isinstance(request, dict):
        request = Request(**request)
    if request.view in {"category_relationship", "spatial", "multivariate"}:
        from firstlook.perspectives import calculate

        return calculate(ds, request, meanings, rows, time_rules)
    if request.view not in {
        "distribution",
        "categories",
        "groups",
        "relationship",
        "time",
        "missingness",
    } or request.metric not in {"count", "distinct", "sum", "mean", "median", "weighted_mean"}:
        raise ValueError("Choose a supported view and summary.")
    ids = _rows(ds, rows)
    frame = ds.frame.loc[ids].copy()
    context = context_id(ds, meanings, ids, time_rules)
    warnings: list[str] = []
    meta: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    table: list[dict[str, Any]] = []
    omitted = 0
    calc_cache = {}
    if request.view != "missingness":
        ds.field(request.x)
    if request.view == "time" and request.representation == "calendar" and request.zero_fill:
        raise ValueError(
            "Weekday/hour cells have different recording exposure. Keep their gaps unknown; use the calendar-period view for declared event zero filling."
        )
    for fid in [request.y, request.group, request.entity, request.weight]:
        if fid:
            ds.field(fid)
    if request.view in {"distribution", "groups", "relationship"} and ds.field(request.x).kind != "number":
        raise ValueError("Choose a numerical field for this perspective.")
    if request.view == "distribution":
        s = frame[request.x]
        boundaries = _edges(s) if edges is None else np.asarray(edges, dtype=float)
        table, summary = _hist(s, boundaries), _summary(s)
        omitted = int(s.isna().sum())
        meta = {"edges": boundaries.tolist(), "x_bounds": [float(boundaries[0]), float(boundaries[-1])]}
        values = s.dropna().astype(float)
        meta["quantiles"] = (
            [{"probability": float(p), "value": float(values.quantile(p))} for p in np.linspace(0, 1, 41)]
            if len(values)
            else []
        )
        definition = (
            f"Distribution of recorded {ds.label(request.x)}; {len(s) - omitted} nonmissing source records."
        )
    elif request.view == "categories":
        if ds.field(request.x).kind not in {"category", "identifier", "text"}:
            raise ValueError("Choose a categorical or identifier field for a category comparison.")
        frame["__group"] = _groups(frame[request.x])
        if frame["__group"].nunique() > 1000:
            raise ValueError("This field has more than 1,000 levels. Choose a more useful grouping field.")
        groups: list[dict[str, Any]] = []
        for label, part in frame.groupby("__group", sort=True):
            value, n = _value(ds, part, frame, request, meanings, "__group", label, calc_cache)
            groups.append({"label": label, "value": value, "n": n, "rows": list(part.index)})
        groups.sort(key=lambda r: (r["value"] is None, -(r["value"] or 0), r["label"]))
        if len(groups) > 20:
            top = {r["label"] for r in groups[:19]}
            other = "Other recorded levels"
            while other in set(frame["__group"]):
                other += " — combined"
            frame["__group"] = frame["__group"].where(frame["__group"].isin(top), other)
            calc_cache.clear()
            groups = []
            for label, part in frame.groupby("__group", sort=True):
                value, n = _value(ds, part, frame, request, meanings, "__group", label, calc_cache)
                groups.append({"label": label, "value": value, "n": n, "rows": list(part.index)})
            groups.sort(
                key=lambda r: (r["label"] == other, r["value"] is None, -(r["value"] or 0), r["label"])
            )
            warnings.append(
                "The final group combines remaining levels; its estimator is recomputed from their source records."
            )
        table = groups
        summary = {"n": len(frame), "groups": len(groups)}
        denominator = (
            len(frame)
            if request.metric == "count"
            else int(frame[request.entity].nunique())
            if request.metric == "distinct" and request.entity
            else None
        )
        if denominator is not None:
            for row in table:
                row["share"] = row["value"] / denominator if denominator else None
            summary["denominator"] = denominator
        composition = request.metric == "count"
        entity = request.entity or (_meaning(meanings, request.y).entity if request.y else None)
        overlap = bool(entity and (frame.groupby(entity)["__group"].nunique() > 1).any())
        if request.metric == "distinct":
            composition = not overlap
            if overlap:
                warnings.append(
                    "Identifier incidence overlaps across groups; these shares need not add to 100%."
                )
        if request.metric == "sum":
            composition = not overlap or request.attribution == "equal"
        meta_composition = (
            composition
            and all(r["value"] is not None and r["value"] >= 0 for r in table)
            and sum(r["value"] or 0 for r in table) > 0
        )
        meta = {
            "y_bounds": [
                min(0.0, min((r["value"] for r in groups if r["value"] is not None), default=0.0)),
                max(0.0, max((r["value"] for r in groups if r["value"] is not None), default=0.0)),
            ]
        }
        meta["composition"] = meta_composition
        definition = (
            _quantity_definition(ds, request, meanings)
            + f" by {ds.label(request.x)} in the active recorded population."
        )
    elif request.view == "groups":
        if not request.group or ds.field(request.group).kind not in {"category", "identifier"}:
            raise ValueError("Choose a recorded category to compare distributions.")
        frame["__group"] = _groups(frame[request.group])
        if frame["__group"].nunique() > 8:
            raise ValueError(
                "Choose a grouping with at most eight levels so its distributions remain comparable."
            )
        boundaries = _edges(frame[request.x]) if edges is None else np.asarray(edges, dtype=float)
        group_stats = []
        for label, part in frame.groupby("__group", sort=True):
            stats = {"label": label, **_summary(part[request.x])}
            group_stats.append(stats)
            table.extend({**stats, **bin} for bin in _hist(part[request.x], boundaries))
        summary = {"n": len(frame), "groups": group_stats}
        meta = {
            "edges": boundaries.tolist(),
            "x_bounds": [float(boundaries[0]), float(boundaries[-1])],
            "group_stats": group_stats,
        }
        omitted = int(frame[request.x].isna().sum())
        definition = f"Recorded {ds.label(request.x)} distributions by {ds.label(request.group)}; common bin boundaries and proportions within each group."
    elif request.view == "relationship":
        if not request.y or request.y == request.x or ds.field(request.y).kind != "number":
            raise ValueError("Choose two different numerical fields.")
        paired = frame.dropna(subset=[request.x, request.y])
        omitted = len(frame) - len(paired)
        summary = _relationship(frame, request.x, request.y)
        group_stats = []
        if request.group:
            if (
                ds.field(request.group).kind not in {"category", "identifier"}
                or frame[request.group].nunique() > 8
            ):
                raise ValueError("Choose a recorded grouping with at most eight levels.")
            for label, part in paired.groupby(request.group, dropna=True, sort=True):
                group_stats.append({"label": str(label), **_relationship(part, request.x, request.y)})
        shown = paired if len(paired) <= 1000 else paired.sample(1000, random_state=20261124).sort_index()
        table = [
            {
                "x": float(r[request.x]),
                "y": float(r[request.y]),
                "group": str(r[request.group])
                if request.group and pd.notna(r[request.group])
                else "Recorded pairs",
                "row": int(i),
            }
            for i, r in shown.iterrows()
        ]
        meta = {
            "group_stats": group_stats,
            "displayed": len(shown),
            "statistical_n": len(paired),
            "x_bounds": clean([paired[request.x].min(), paired[request.x].max()]),
            "y_bounds": clean([paired[request.y].min(), paired[request.y].max()]),
        }
        if len(paired) > len(shown):
            warnings.append(
                f"The plot displays a fixed sample of {len(shown):,} pairs; statistics use all {len(paired):,} complete pairs."
            )
        if request.group and frame[request.group].isna().any():
            warnings.append(
                "Pooled statistics include complete pairs with missing group labels; within-group statistics exclude those labels."
            )
        definition = f"Recorded relationship between {ds.label(request.x)} and {ds.label(request.y)}. Association does not establish causation."
    elif request.view == "time":
        if ds.field(request.x).kind != "time" or request.period not in {"D", "W", "MS"}:
            raise ValueError("Choose a timestamp and a supported calendar interval.")
        if request.group:
            raise ValueError(
                "This time view summarizes one population. Compare a selected population alongside its reference."
            )
        dated = frame.dropna(subset=[request.x]).copy()
        omitted = len(frame) - len(dated)
        if dated.empty:
            raise ValueError("There are no recorded dates in this population.")
        stamps = dated[request.x]
        if stamps.dt.tz is not None:
            stamps = stamps.dt.tz_convert("UTC").dt.tz_localize(None)
            warnings.append("Calendar intervals use UTC for timezone-aware timestamps.")
        frequency = {"D": "D", "W": "W-SUN", "MS": "M"}[request.period]
        dated["__period"] = stamps.dt.to_period(frequency)
        low, high = dated["__period"].min(), dated["__period"].max()
        rule = (time_rules or {}).get(request.x, TimeRule())
        rule = TimeRule(**rule) if isinstance(rule, dict) else rule
        cutoff: Any = None
        if request.zero_fill:
            if (
                not rule.events
                or not rule.complete
                or not rule.complete_through
                or request.metric not in {"count", "sum"}
                or ids != list(ds.frame.index)
            ):
                raise ChoiceRequired(
                    "Zero-filling needs complete event recording for the whole table and a last-complete date. Means and selected records keep gaps unknown.",
                    request.x,
                )
            parsed = pd.Timestamp(rule.complete_through).as_unit("ns")
            if pd.isna(parsed):
                raise ValueError("Supply a valid last complete date.")
            cutoff = cast(pd.Timestamp, parsed)
            if cutoff.tzinfo:
                cutoff = cast(pd.Timestamp, cutoff.tz_convert("UTC").tz_localize(None))
            cutoff = cast(pd.Timestamp, cutoff.normalize())
            high = max([high, cutoff.to_period(frequency)], key=lambda p: p.ordinal)
        periods = pd.period_range(low, high, freq=frequency)
        if len(periods) > 1200:
            raise ValueError("This interval creates more than 1,200 periods. Choose weeks or months.")
        grouped = {p: part for p, part in dated.groupby("__period", sort=True)}
        for period in periods:
            part = grouped.get(period)
            value, n = (
                _value(ds, part, dated, request, meanings, "__period", cache=calc_cache)
                if part is not None
                else (None, 0)
            )
            if part is None and cutoff is not None and period.end_time.normalize() <= cutoff:
                value = 0
            table.append(
                {
                    "label": period.start_time.isoformat(),
                    "date": period.start_time.isoformat(),
                    "value": value,
                    "n": n,
                    "observed": part is not None,
                    "rows": list(part.index) if part is not None else [],
                }
            )
        summary = {"n": len(dated), "periods": len(periods), "undated": omitted}
        if request.representation == "calendar":
            dated["__phase"] = stamps.dt.dayofweek * 24 + stamps.dt.hour
            cells = []
            phase_cache = {}
            for phase, part in dated.groupby("__phase", sort=True):
                value, n = _value(ds, part, dated, request, meanings, "__phase", cache=phase_cache)
                cells.append({"hour": int(phase % 24), "weekday": int(phase // 24), "value": value, "n": n})
            meta["calendar_cells"] = clean(cells)
            warnings.append(
                "Calendar cells aggregate recorded weekday/hour combinations across the included weeks; absent cells remain unknown and recording exposure may differ."
            )
        definition = (
            _quantity_definition(ds, request, meanings)
            + f" by {request.period} calendar intervals; absent periods are {'zero only within declared complete event coverage' if request.zero_fill else 'unknown'}."
        )
        if request.representation == "calendar":
            definition = (
                _quantity_definition(ds, request, meanings)
                + " by recorded weekday and hour across the included dates; absent combinations remain unknown."
            )
    else:
        table = [
            {
                "field": f.id,
                "label": ds.label(f.id),
                "count": int(frame[f.id].isna().sum()),
                "share": float(frame[f.id].isna().mean()),
                "value": int(frame[f.id].isna().sum()),
            }
            for f in ds.fields
        ]
        summary = {"n": len(frame), "missing_cells": int(frame.isna().sum().sum())}
        definition = "Missing recorded values by field; absence is not automatically zero."
    if request.metric in {"mean", "median"} and request.view in {"categories", "time"}:
        warnings.append(
            "The estimator weights nonmissing recorded rows equally, unless a value identifier is explicitly declared."
        )
    required = []
    if request.view in {"distribution", "groups"}:
        required = [request.x]
    elif request.view == "relationship":
        required = [request.x, request.y]
    elif request.view == "time":
        required = [request.x] + (
            [request.y] if request.metric not in {"count", "distinct"} and request.y else []
        )
    elif request.view == "categories" and request.metric not in {"count", "distinct"}:
        required = [request.y]
    if request.metric == "distinct" and request.entity:
        required.append(request.entity)
    if request.metric in {"sum", "mean", "median", "weighted_mean"} and request.view in {
        "categories",
        "time",
    }:
        entity = request.entity or (_meaning(meanings, request.y).entity if request.y else None)
        if entity:
            required.append(entity)
    if request.metric == "weighted_mean" and request.weight:
        required.append(request.weight)
    meta["population_rows"] = ids
    meta["units"] = {
        fid: _meaning(meanings, fid).unit or ds.field(fid).unit for fid in [request.x, request.y] if fid
    }
    meta["eligible_rows"] = (
        list(frame.dropna(subset=list(dict.fromkeys(required))).index) if required else ids
    )
    if required:
        omitted = len(ids) - len(meta["eligible_rows"])
    _representation(request, table, meta, warnings)
    result_id = digest([context, request, table, meta])
    return Result(
        result_id,
        context,
        request,
        clean(table),
        clean(summary),
        ids,
        omitted,
        definition,
        warnings,
        clean(meta),
    )


def _representation(request, table, meta, warnings):
    """Validate a finite representation and record any derived plotted values."""
    allowed = {
        "distribution": {"auto", "frequency", "quantile", "box"},
        "groups": {"auto", "box"},
        "categories": {"auto", "treemap"},
        "time": {"auto", "bars", "share", "smooth", "deviation", "calendar"},
        "relationship": {"auto"},
        "missingness": {"auto"},
    }
    mode = request.representation
    if mode not in allowed[request.view]:
        raise ValueError("Choose a supported representation for this perspective.")
    if mode == "treemap" and not meta.get("composition"):
        raise ValueError(
            "A treemap needs a nonnegative partition of one total. Use ranked bars for this definition."
        )
    if mode == "box":
        warnings.append(
            "Boxes show the middle half and median; whiskers show the full observed minimum and maximum, not a 1.5-IQR outlier rule."
        )
    if mode in {"share", "smooth", "deviation"}:
        values = pd.Series([r["value"] for r in table], dtype=float)
        if mode == "share":
            if request.metric not in {"count", "sum"} or (values.dropna() < 0).any() or values.sum() <= 0:
                raise ValueError("A share of the series total needs a positive nonnegative additive series.")
            transformed = values / values.sum()
            warnings.append(
                "Each plotted value is a fraction of this series' recorded total. Missing periods are outside that denominator."
            )
        else:
            smooth = values.rolling(3, min_periods=3).mean()
            transformed = values - smooth if mode == "deviation" else smooth
            warnings.append(
                "Uses three consecutive calendar periods; gaps and the first two periods remain unknown. This is a descriptive trailing mean, not seasonal adjustment."
            )
        meta["plotted_values"] = clean([{"date": r["date"], "value": v} for r, v in zip(table, transformed)])


def compare(ds, request, selected_rows, meanings=None, reference_rows=None, time_rules=None) -> Comparison:
    if request.view in {"spatial", "multivariate", "category_relationship"} or request.representation in {
        "treemap",
        "calendar",
    }:
        raise ValueError(
            "This representation already combines several perspectives. Use a distribution, ranked bars, scatter or time series for a population comparison."
        )
    selected = _rows(ds, selected_rows)
    reference = _rows(
        ds,
        reference_rows
        if reference_rows is not None
        else [i for i in ds.frame.index if i not in set(selected)],
    )
    union = sorted(set(selected) | set(reference))
    edges = _edges(ds.frame.loc[union, request.x]) if request.view in {"distribution", "groups"} else None
    left = analyze(ds, request, meanings, selected, time_rules, edges)
    right = analyze(ds, request, meanings, reference, time_rules, edges)
    if request.view == "relationship":
        for key, fid in [("x_bounds", request.x), ("y_bounds", request.y)]:
            bounds = clean([ds.frame.loc[union, fid].min(), ds.frame.loc[union, fid].max()])
            left.meta[key] = right.meta[key] = bounds
    elif request.view == "distribution":
        maximum = max(
            (r["share"] for result in [left, right] for r in result.table if r["share"] is not None),
            default=1.0,
        )
        for result in [left, right]:
            result.meta["comparison_measure"] = "within-population share"
            result.meta["y_bounds"] = [0.0, maximum]
            result.warnings.append(
                "Common-bin frequency lines compare shapes using each population's nonmissing recorded values as its denominator; the exact table also retains counts."
            )
    elif request.view in {"categories", "missingness", "time"}:
        values = [r["value"] for result in [left, right] for r in result.table if r.get("value") is not None]
        bounds = [min([0.0] + values), max([0.0] + values)]
        left.meta["y_bounds"] = right.meta["y_bounds"] = bounds
        if request.view in {"categories", "missingness"}:
            if request.view == "categories" and _groups(ds.frame.loc[union, request.x]).nunique() > 20:
                raise ValueError(
                    "Choose a grouping with at most twenty levels for an aligned population comparison."
                )
            labels = list(dict.fromkeys(r["label"] for r in left.table + right.table))
            left.meta["labels"] = right.meta["labels"] = labels
        else:
            dates = [r["date"] for result in [left, right] for r in result.table]
            left.meta["time_bounds"] = right.meta["time_bounds"] = [min(dates), max(dates)]
            if request.representation in {"share", "smooth", "deviation"}:
                values = [
                    r["value"]
                    for result in [left, right]
                    for r in result.meta["plotted_values"]
                    if r["value"] is not None
                ]
                left.meta["y_bounds"] = right.meta["y_bounds"] = [min([0.0] + values), max([0.0] + values)]
    elif request.view == "groups":
        maximum = max(
            (r["share"] for result in [left, right] for r in result.table if r["share"] is not None),
            default=1.0,
        )
        left.meta["y_bounds"] = right.meta["y_bounds"] = [0.0, maximum]
    for result in [left, right]:
        entity = request.entity or (_meaning(meanings, request.y).entity if request.y else None)
        if entity and request.metric != "count":
            shared = set(ds.frame.loc[selected, entity].dropna()) & set(
                ds.frame.loc[reference, entity].dropna()
            )
            if shared:
                result.warnings.append(
                    f"The populations share {len(shared):,} recorded value identifiers. Disjoint source rows do not make these entities independent or a partition."
                )
        result.id = digest([result.context, result.request, result.table, result.meta])
    overlap = bool(set(selected) & set(reference))
    return Comparison(
        left,
        right,
        "Selected source records beside an overlapping reference population."
        if overlap
        else "Selected source records beside a disjoint reference population.",
    )
