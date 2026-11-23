"""Bounded additional perspectives. Every recipe is deterministic, recorded and replayable."""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, cast

from firstlook.contracts import ChartSpec, Finding, ResultArtifact, Role, clean, digest
from firstlook.exploration_contracts import ExplorationTask, PerspectiveCoverage
from firstlook.numerics import cdf_distance, compressed_ecdf
from firstlook.semantics import dimensions, measures

RECIPES = {
    "group_shape": "Compare two group distributions",
    "density": "Count every paired observation in a numeric grid",
    "influence": "Inspect influence on a linear reference fit",
    "concentration": "Inspect cumulative contribution",
    "categorical_facets": "Compare categorical intersections",
    "temporal": "Inspect temporal context",
    "histogram_sensitivity": "Inspect histogram width and origin",
}


def display_result(inv, result_id):
    """Deterministic shared axes for compatible, recorded companion relationships."""
    result = inv.results[result_id]
    relation = next(
        (
            (primary, link["companion"])
            for primary, link in inv.related_views.items()
            if result_id in {primary, link["companion"]}
        ),
        None,
    )
    if relation is None:
        return result
    from firstlook.visualization.compiler import axis_domains

    a, b = [inv.results[i] for i in relation]
    fa, fb = [next((f for f in inv.findings if f.result_id == i), None) for i in relation]
    cumulative_pair = bool(
        fa
        and fb
        and {fa.chart.template, fb.chart.template} == {"histogram", "ecdf"}
        and a.plan.fields == b.plan.fields
    )
    calendar_pair = bool(
        a.plan.operation == "exploration"
        and a.plan.params.get("recipe") == "temporal"
        and a.plan.params.get("mode") == "calendar"
        and b.plan.operation == "metric"
        and a.plan.params.get("metric") == b.plan.params.get("metric")
    )
    compatible = calendar_pair or (
        cumulative_pair
        or (
            a.plan.operation == "quantile_bin_summary"
            and b.plan.operation == "relationship"
            and a.plan.fields == b.plan.fields
        )
        or (fa and fb and fa.chart.template == fb.chart.template == "histogram")
    )
    if not compatible or fa is None or fb is None:
        return result
    da, db = axis_domains(fa.chart, a), axis_domains(fb.chart, b)
    axes = {"y"} if calendar_pair else {"x"} if cumulative_pair else da.keys() & db.keys()
    domains = {
        **(da if result_id == a.id else db),
        **{axis: (min(da[axis][0], db[axis][0]), max(da[axis][1], db[axis][1])) for axis in axes},
    }
    view = result.model_copy(deep=True)
    view.metadata["comparison_domains"] = clean(domains)
    return view


def validate_task(ds, ctx, plan):
    recipe = str(plan.params.get("recipe", ""))
    if recipe not in RECIPES or len(plan.fields) != len(set(plan.fields)):
        raise ValueError("Choose a recorded exploration recipe with distinct fields.")
    parameters = {
        "group_shape": {"levels", "representation", "bins"},
        "density": {"bins"},
        "influence": set(),
        "concentration": {"metric", "groups"},
        "categorical_facets": {"metric", "groups"},
        "histogram_sensitivity": {"bins", "origin", "normalization"},
        "temporal": {"metric", "metrics", "time_field", "period", "mode", "window", "baseline"},
    }
    if set(plan.params) - ({"recipe", "recipe_version"} | parameters[recipe]):
        raise ValueError("Unknown recipe parameters are not executable.")
    if (
        not ctx.row_ids
        or len(ctx.row_ids) != len(set(ctx.row_ids))
        or not set(ctx.row_ids) <= set(ds.frame.index)
    ):
        raise ValueError("Exploration needs a nonempty exact source population.")
    if any(fid not in ds.frame or ds.field(fid).excluded for fid in plan.fields):
        raise ValueError("An exploration field is unknown or excluded.")
    nums, cats = measures(ds), dimensions(ds)
    if recipe in {"density", "influence"} and (len(plan.fields) != 2 or not set(plan.fields) <= set(nums)):
        raise ValueError("Choose two measures.")
    if recipe == "group_shape" and (
        len(plan.fields) != 2 or plan.fields[0] not in cats or plan.fields[1] not in nums
    ):
        raise ValueError("Choose a category and a measure.")
    if recipe == "histogram_sensitivity" and (len(plan.fields) != 1 or plan.fields[0] not in nums):
        raise ValueError("Choose one measure.")
    from firstlook.semantic.model import get_model
    from firstlook.semantic.planner import metric_fields

    if recipe in {"concentration", "categorical_facets", "temporal"}:
        mids = [str(plan.params.get("metric", ""))]
        if recipe == "temporal" and plan.params.get("mode") == "index":
            mids = list(plan.params.get("metrics", []))
            if not 2 <= len(mids) <= 4:
                raise ValueError("Index comparison needs two to four approved series.")
        expected = set()
        for mid in mids:
            expected.update(metric_fields(ds, get_model(ds).metric(mid)))
        groups = list(plan.params.get("groups", []))
        expected.update(groups)
        if any(g not in cats for g in groups):
            raise ValueError("Grouping needs categorical fields.")
        if recipe == "temporal":
            time = str(plan.params.get("time_field", ""))
            if time not in ds.frame or ds.field(time).role != Role.TIME:
                raise ValueError("Choose a timestamp.")
            expected.add(time)
        if expected != set(plan.fields):
            raise ValueError("Recipe dependencies do not match its recorded metric and fields.")
    if ds.record.semantic_model and recipe in {
        "density",
        "influence",
        "group_shape",
        "histogram_sensitivity",
    }:
        if any(
            ds.record.semantic_model.meaning(f).kind in {"circular", "coordinate", "composition"}
            for f in plan.fields
            if f in nums
        ):
            raise ValueError(
                "This recipe assumes linear scalar geometry; choose a supported domain summary in Meaning."
            )


def execute(ds, ctx, plan):
    from firstlook.discovery import analyze, paired, plan_for
    from firstlook.semantic.model import get_model
    from firstlook.semantic.planner import metric_plan

    validate_task(ds, ctx, plan)
    recipe, params = str(plan.params["recipe"]), plan.params
    frame = ds.frame.loc[ctx.row_ids]
    records: list[dict] = []
    metrics: dict = {}
    warnings: list[str] = []
    meta: dict[str, Any] = {"recipe_version": 2}
    n, missing = len(frame), 0
    template, x_label, y_label = "line", "", ""
    observation = ""
    if recipe == "group_shape":
        category, value = plan.fields
        valid = frame[[category, value]].dropna()
        levels = list(params.get("levels", valid[category].astype(str).value_counts().head(2).index.tolist()))
        if len(levels) != 2 or len(set(levels)) != 2:
            raise ValueError("Choose two distinct named groups.")
        arrays = []
        for level in levels:
            s = valid.loc[valid[category].astype(str).eq(str(level)), value].astype(float)
            if len(s) < 20:
                raise ValueError("Each distribution needs at least 20 recorded values.")
            arrays.append(s.to_numpy())
            xs, ps, error, distinct = compressed_ecdf(s, cap=598)
            memberships = s.groupby(s).groups
            records.extend(
                {
                    "x": float(x),
                    "value": float(p),
                    "group": str(level),
                    "row_ids": [int(i) for i in memberships[x]],
                }
                for x, p in zip(xs, ps)
            )
            metrics[str(level)] = {"n": len(s), "max_cdf_error": error, "distinct": distinct}
        grid = [0.1, 0.25, 0.5, 0.75, 0.9]
        qa, qb = np.quantile(arrays[0], grid), np.quantile(arrays[1], grid)
        metrics.update(
            cdf_distance=cdf_distance(*arrays),
            quantiles=[
                {"quantile": q, "first": float(a), "second": float(b), "difference": float(a - b)}
                for q, a, b in zip(grid, qa, qb)
            ],
            estimator="linear; full source values",
        )
        n, missing = sum(map(len, arrays)), len(frame) - len(valid)
        metrics["omitted_other_group_rows"] = len(valid) - n
        template, x_label, y_label = "ecdf", ds.label(value), "Within-group cumulative proportion"
        meta.update(step="post", selection_semantics="Exact-value source members of retained vertices")
        representation = str(params.get("representation", "ecdf"))
        if representation not in {"ecdf", "frequency_polygon"}:
            raise ValueError("Choose cumulative distributions or common-bin frequency polygons.")
        if representation == "frequency_polygon":
            bins = int(params.get("bins", 15))
            if not 5 <= bins <= 50:
                raise ValueError("Choose between five and fifty common equal-width bins.")
            pooled = np.concatenate(arrays)
            _, edges = np.histogram(pooled, bins=bins)
            records = []
            for level in levels:
                source = valid.loc[valid[category].astype(str).eq(str(level)), value].astype(float)
                counts, _ = np.histogram(source, bins=edges)
                for i, count in enumerate(counts):
                    members = source.index[
                        (source >= edges[i])
                        & ((source <= edges[i + 1]) if i == bins - 1 else (source < edges[i + 1]))
                    ].tolist()
                    records.append(
                        {
                            "group": str(level),
                            "x": float((edges[i] + edges[i + 1]) / 2),
                            "left": float(edges[i]),
                            "right": float(edges[i + 1]),
                            "value": float(count / len(source)),
                            "count": int(count),
                            "label": f"{edges[i]:.3g}–{edges[i + 1]:.3g}",
                            "row_ids": members,
                        }
                    )
            template, y_label = "frequency_polygon", "Within-group proportion per bin"
            meta.update(
                normalization="proportion",
                common_bin_edges=edges.tolist(),
                selection_semantics="All recorded source members in the selected bins",
            )
        observation = "Compare shape, center and tails using within-group cumulative proportions. CDF distance and quantile differences use full source values; these are descriptive effects."
        if representation == "frequency_polygon":
            observation = "Compare two shapes with common equal-width bins and within-group proportions. Straight segments connect bin midpoints; these are not smoothed densities. Group sizes, full-source quantile differences and CDF distance remain recorded."
        warnings.append(
            "Independent-sample inference is not assumed. Different distributions do not establish a treatment effect or distinct latent populations."
        )
    elif recipe in {"density", "influence"}:
        valid = paired(frame, plan.fields)
        if len(valid) < 30 or any(valid[f].nunique() < 2 for f in plan.fields):
            raise ValueError("Choose two varying measures with at least 30 complete pairs.")
        x, y = valid[plan.fields[0]].to_numpy(dtype=float), valid[plan.fields[1]].to_numpy(dtype=float)
        n, missing = len(valid), len(frame) - len(valid)
        x_label, y_label = map(ds.label, plan.fields)
        if recipe == "density":
            bins = max(4, min(24, int(params.get("bins", 12))))
            counts, xe, ye = np.histogram2d(x, y, bins=bins)
            ix = np.clip(np.searchsorted(xe, x, side="right") - 1, 0, bins - 1)
            iy = np.clip(np.searchsorted(ye, y, side="right") - 1, 0, bins - 1)
            members = {}
            for row, a, b in zip(valid.index, ix, iy):
                members.setdefault((int(a), int(b)), []).append(int(row))
            records = [
                {
                    "x": a,
                    "y": b,
                    "left": float(xe[a]),
                    "right": float(xe[a + 1]),
                    "bottom": float(ye[b]),
                    "top": float(ye[b + 1]),
                    "value": int(counts[a, b]),
                    "row_ids": members.get((a, b), []),
                }
                for a in range(bins)
                for b in range(bins)
            ]
            template = "density"
            meta["numeric_grid"] = {
                "x_edges": xe.tolist(),
                "y_edges": ye.tolist(),
                "closure": "Left closed/right open, final bin closed",
                "complete_grid": True,
            }
            metrics = {"counted_pairs": int(counts.sum()), "cells": bins * bins}
            observation = "Every complete pair contributes to exactly one equal-width numeric cell, including zero-count cells. Use raw points to inspect details; cells do not establish clusters."
        else:
            # Standardizing protects the fit; recorded diagnostics retain original units.
            zx, zy = (x - x.mean()) / x.std(), (y - y.mean()) / y.std()
            design = np.column_stack([np.ones(n), zx])
            beta = np.linalg.lstsq(design, zy, rcond=None)[0]
            residual = zy - design @ beta
            leverage = np.sum(design * (design @ np.linalg.inv(design.T @ design)), axis=1)
            mse = float(residual @ residual / (n - 2))
            if mse <= 1e-20 or np.any(leverage >= 1 - 1e-10):
                raise ValueError(
                    "The fit is perfect or has near-unit leverage; ordinary influence diagnostics are undefined."
                )
            student = residual / np.sqrt(mse * (1 - leverage))
            cook = student**2 * leverage / (2 * (1 - leverage))
            keep = np.unique(
                np.r_[
                    np.argsort(cook)[-25:],
                    np.random.default_rng(20261120).choice(n, min(4975, n), replace=False),
                ]
            )
            records = [
                {
                    "x": float(leverage[i]),
                    "y": float(student[i]),
                    "cook": float(cook[i]),
                    "residual": float(residual[i] * y.std()),
                    "row_id": int(valid.index[i]),
                }
                for i in keep
            ]
            metrics = {
                "source_pairs": n,
                "max_cook": float(cook.max()),
                "largest_influence_row": int(valid.index[int(cook.argmax())]),
                "rmse": float(np.sqrt(np.mean(residual**2)) * y.std()),
                "fit": "OLS with intercept",
                "displayed_points": len(keep),
            }
            meta.update(
                sampled=len(keep) < n,
                analysis_scope={
                    "eligible_rows": n,
                    "statistical_rows": n,
                    "displayed_marks": len(keep),
                    "display_sample": len(keep) < n,
                    "selection": "Displayed diagnostic points only",
                },
            )
            template, x_label, y_label = "scatter", "Leverage", "Internally studentized residual"
            observation = "Leverage, residual size and influence answer different questions. Cook's distance measures sensitivity of this linear reference fit; no records are removed."
    elif recipe in {"concentration", "categorical_facets"}:
        metric = get_model(ds).metric(str(params["metric"]))
        groups = list(params.get("groups", []))
        if len(groups) != (1 if recipe == "concentration" else 2):
            raise ValueError("Choose the required distinct categorical dimensions.")
        if frame[groups].dropna().drop_duplicates().shape[0] > (200 if recipe == "concentration" else 32):
            raise ValueError("Narrow the family: at most 200 original parts or 32 facet intersections.")
        if recipe == "categorical_facets":
            if (
                frame[groups[0]].nunique() > 4
                or frame[groups[1]].nunique() > 8
                or frame[groups[0]].nunique() * frame[groups[1]].nunique() > 32
            ):
                raise ValueError(
                    "Facets require at most four panels, eight items and 32 complete intersections."
                )
        original, _ = analyze(ds, ctx, metric_plan(ds, ctx, metric.id, groups, limit=201, full_family=True))
        if any(r.get("other") for r in original.records):
            raise ValueError("This view requires original groups, not pooled Other.")
        if recipe == "concentration":
            if (
                metric.aggregation not in {"sum", "count_rows"}
                or metric.transform != "identity"
                or original.missing
                or any(r["value"] is None or r["value"] < 0 for r in original.records)
            ):
                raise ValueError(
                    "Concentration requires a complete nonnegative additive partition with an identity transform."
                )
            if metric.entity and metric.allocation != "equal":
                memberships = frame.dropna(
                    subset=get_model(ds).entity(metric.entity).keys + groups
                ).drop_duplicates(get_model(ds).entity(metric.entity).keys + groups)
                if memberships.duplicated(get_model(ds).entity(metric.entity).keys).any():
                    raise ValueError("Overlapping full-credit entity memberships are not a partition.")
            total = sum(r["value"] for r in original.records)
            if total <= 0:
                raise ValueError("Contribution needs a positive total.")
            cumulative = 0.0
            for i, r in enumerate(original.records, 1):
                cumulative += r["value"]
                records.append(
                    {
                        **r,
                        "x": i,
                        "amount": r["value"],
                        "value": cumulative / total,
                        "share": r["value"] / total,
                    }
                )
            template, x_label, y_label = (
                "line",
                "Original categories, ranked by contribution",
                "Cumulative share",
            )
            metrics = {"total": total, "original_parts": len(records)}
            meta.update(partwhole_verified=True, full_original_parts=True)
            observation = "Cumulative contribution over original eligible parts. This describes the observed concentration; no 80/20 or power-law model is assumed."
        else:
            if metric.transform in {"zscore", "index", "percent_change"}:
                raise ValueError("Facet comparisons need a fixed, compatible transformation reference.")
            from itertools import product

            lookup = {tuple(str(v) for v in r["group_values"]): r for r in original.records}
            for facet, label in product(
                sorted(frame[groups[0]].dropna().astype(str).unique()),
                sorted(frame[groups[1]].dropna().astype(str).unique()),
            ):
                r = lookup.get((facet, label))
                records.append(
                    {**r, "facet": facet, "label": label}
                    if r
                    else {
                        "facet": facet,
                        "label": label,
                        "value": 0 if metric.aggregation == "count_rows" else None,
                        "n": 0,
                        "row_ids": [],
                        "key": digest([groups, facet, label]),
                    }
                )
            template, x_label, y_label = "facet", metric.label, ds.label(groups[1])
            meta["facet_field"] = ds.label(groups[0])
            observation = "Compare the same approved metric across a small complete grid. Panels share categories and a numerical scale; absent values and per-cell support remain explicit."
        n, missing, warnings = original.support, original.missing, original.warnings
        meta.update(definition=original.metadata["definition"], semantic_revision=get_model(ds).revision)
    elif recipe == "histogram_sensitivity":
        s = frame[plan.fields[0]].dropna().astype(float)
        if s.empty or s.nunique() < 2:
            raise ValueError("Histogram sensitivity needs a varying finite measure.")
        bins = max(5, min(50, int(params.get("bins", 15))))
        origin = float(params.get("origin", 0))
        if not 0 <= origin <= 1:
            raise ValueError("Origin shift must be between zero and one bin width.")
        width = float((s.max() - s.min()) / bins)
        start = float(s.min() - origin * width)
        edges = start + np.arange(bins + 2) * width
        inner = plan_for(
            ctx,
            "distribution",
            plan.fields,
            plan.question,
            {"edges": edges.tolist(), "normalization": params.get("normalization", "count")},
        )
        result, finding = analyze(ds, ctx, inner)
        result.id, result.plan = plan.id, plan
        result.metadata.update(bin_width=width, origin=start)
        result.metadata["task"] = ExplorationTask(
            family=recipe, question=plan.question, fields=plan.fields, base_context=ctx.id, operation=recipe
        ).model_dump(mode="json")
        finding.id, finding.result_id = plan.id, plan.id
        finding.chart.id, finding.chart.result_id = digest([plan.id, "histogram"]), plan.id
        finding.family = recipe
        return result, finding
    elif recipe == "temporal":
        mode, period, time = (
            str(params.get("mode", "aggregation")),
            str(params.get("period", "MS")),
            str(params["time_field"]),
        )
        if mode not in {"aggregation", "smooth", "calendar", "index"}:
            raise ValueError("Unsupported temporal recipe.")
        mids = list(params.get("metrics", [])) if mode == "index" else [str(params["metric"])]
        series = []
        units = []
        for mid in mids:
            metric = get_model(ds).metric(mid)
            source, _ = analyze(ds, ctx, metric_plan(ds, ctx, mid, time_field=time, period=period))
            series.append((metric, source))
            units.append(get_model(ds).meaning(metric.field).unit if metric.field else "count")
        metric, source = series[0]
        n, missing, warnings = source.support, source.missing, source.warnings
        meta.update(
            time_axis=True, definition=source.metadata["definition"], semantic_revision=get_model(ds).revision
        )
        x_label, y_label = ds.label(time), metric.label
        if mode == "aggregation":
            records = source.records
            observation = f"The approved metric is recomputed from source components at {period} resolution. Unknown gaps and incomplete periods retain their meaning."
        elif mode == "smooth":
            window = max(2, min(12, int(params.get("window", 3))))
            if (
                metric.aggregation not in {"sum", "count_rows", "count_distinct"}
                or metric.transform != "identity"
            ):
                raise ValueError(
                    "This smoother accepts identity-scale period amounts/counts, not averages of rates or states."
                )
            records = [{**r, "group": "Recorded period"} for r in source.records]
            supported = 0
            for i, r in enumerate(source.records):
                parts = source.records[max(0, i - window + 1) : i + 1]
                okay = len(parts) == window and all(
                    p.get("complete") and p["value"] is not None for p in parts
                )
                value = sum(p["value"] for p in parts) / window if okay else None
                supported += okay
                records.append(
                    {
                        **r,
                        "value": value,
                        "group": f"Trailing {window} complete periods",
                        "row_ids": sorted({row for p in parts for row in p["row_ids"]}) if okay else [],
                    }
                )
            if not supported:
                raise ValueError(
                    "No complete consecutive window under the scoped coverage declaration. Confirm coverage in Meaning or inspect raw periods."
                )
            observation = f"Raw period values and a trailing {window}-period mean. Full complete windows only; the companion is delayed and is not a forecast."
            metrics["window"] = window
            meta["selection_semantics"] = (
                "Union of source contributors to each complete trailing window; this is not an instantaneous observation"
            )
        elif mode == "calendar":
            if period not in {"D", "MS"}:
                raise ValueError("Calendar context supports daily weekday or monthly month-of-year series.")
            by_cycle = {}
            for r in source.records:
                stamp = pd.Timestamp(r["x"])
                cycle = str(stamp.year) if period == "MS" else str(cast(Any, stamp).to_period("W"))
                phase = stamp.month if period == "MS" else stamp.dayofweek + 1
                by_cycle.setdefault(cycle, []).append({**r, "x": phase, "date": r["x"], "group": cycle})
            complete = [
                v
                for v in by_cycle.values()
                if len(v) == (12 if period == "MS" else 7)
                and all(r.get("complete") and r["value"] is not None for r in v)
            ]
            if len(complete) < 2:
                raise ValueError(
                    "Calendar context needs at least two complete recorded cycles; incomplete cycles are excluded."
                )
            records = [r for cycle in complete[-4:] for r in cycle]
            metrics.update(complete_cycles=len(complete), displayed_cycles=min(4, len(complete)))
            meta["time_axis"] = False
            x_label = "Month of year" if period == "MS" else "Day of week (Monday=1)"
            observation = "Chronological observations aligned by calendar phase, up to four complete cycles. Repetition in this view does not establish seasonality."
        else:
            if len(set(units)) != 1 or not units[0]:
                raise ValueError("Common-baseline series require explicitly compatible recorded units.")
            from firstlook.semantic.policy import unit_registry
            from pint.errors import PintError

            signatures = []
            for m, _ in series:
                if not m.field:
                    signatures.append(("count", "", ""))
                    continue
                meaning = get_model(ds).meaning(m.field)
                if not meaning.confirmed or meaning.kind in {
                    "unknown",
                    "temperature",
                    "coordinate",
                    "circular",
                    "composition",
                    "index",
                }:
                    raise ValueError(
                        "Common-baseline indexing needs confirmed ratio-scale quantities with a meaningful zero."
                    )
                signatures.append((meaning.unit, meaning.currency, meaning.basis))
                if meaning.currency:
                    if not meaning.basis:
                        raise ValueError(
                            "Declare a compatible currency/reference basis before indexing monetary series."
                        )
                else:
                    try:
                        if (
                            unit_registry()
                            .Quantity(0, unit_registry().Unit(meaning.unit))
                            .to_base_units()
                            .magnitude
                            != 0
                        ):
                            raise ValueError(
                                "Offset units cannot be indexed without an explicit reference construction."
                            )
                    except (PintError, KeyError, TypeError) as exc:
                        raise ValueError(
                            "Resolve the recorded units before common-baseline indexing."
                        ) from exc
            if len(set(signatures)) != 1:
                raise ValueError(
                    "Series need the same recorded unit, currency and basis; no implicit conversion is performed."
                )
            date = str(params.get("baseline", ""))
            if not date:
                raise ValueError("Choose one common baseline date, not each series' first observation.")
            for metric, source in series:
                base = next((r for r in source.records if str(r["x"])[:10] == date[:10]), None)
                if not base or base["value"] is None or base["value"] <= 0 or not base.get("complete"):
                    raise ValueError(
                        "Each series needs a positive complete value at the common reference date."
                    )
                if metric.transform != "identity":
                    raise ValueError(
                        "Index original identity-scale series; transformed metrics need a different task."
                    )
                records.extend(
                    {
                        **r,
                        "original_value": r["value"],
                        "value": r["value"] / base["value"] * 100 if r["value"] is not None else None,
                        "group": metric.label,
                    }
                    for r in source.records
                )
            y_label = "Index (common reference=100)"
            metrics.update(baseline=date, original_unit=units[0])
            observation = "Two to four compatible series indexed to the same positive complete reference. Index-point differences are not percentage growth. Original values remain in the table."
    if recipe == "temporal" and len(records) > 1200:
        raise ValueError(
            "The combined temporal view exceeds 1,200 marks. Choose a coarser period or fewer series."
        )
    task = ExplorationTask(
        family=recipe, question=plan.question, fields=plan.fields, base_context=ctx.id, operation=recipe
    )
    meta["task"] = task.model_dump(mode="json")
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
        id=digest([plan.id, template]),
        result_id=plan.id,
        context=ctx.id,
        template=template,
        x_label=x_label,
        y_label=y_label,
        zero_baseline=template in {"bar", "histogram", "facet"},
        alt=observation,
        rules=[
            "VALID-01",
            "SOURCE-01",
            "SUPPORT-01",
            "SCALE-01",
            "EXP-TIME"
            if recipe == "temporal"
            else "EXP-COMP"
            if recipe == "categorical_facets"
            else "EXP-SHAPE",
        ],
    )
    finding = Finding(
        id=plan.id,
        title=plan.question,
        observation=observation,
        result_id=plan.id,
        chart=chart,
        family=recipe,
        score=0.65,
        limitations=warnings + ["Exploratory descriptive evidence; no causal or significance claim."],
    )
    return result, finding


def perspective_coverage(ds, inv, opened=()):
    """Coverage of this finite catalog, never a percentage of dataset understanding."""
    nums, cats = measures(ds), dimensions(ds)
    definitions = [
        (
            "Category contribution",
            {"frequency", "metric", "concentration"},
            len(cats),
            "Up to 10 dimensions and 16 semantic metric definitions; original eligible groups ranked by requested quantity",
        ),
        (
            "Distribution",
            {"distribution", "ecdf", "group_distribution", "group_shape", "histogram_sensitivity"},
            len(nums),
            "First 12 focused measures; two-group shape checks available on request",
        ),
        (
            "Time",
            {"time", "temporal"},
            sum(f.role == Role.TIME and not f.excluded for f in ds.record.fields),
            "Eligible timestamps; first two focused measures automatically; explicit semantic time recipes on request",
        ),
        (
            "Numeric relationships",
            {"relationship", "quantile_bin_summary", "density", "influence"},
            len(nums) * (len(nums) - 1) // 2,
            "First 40 focused measures, 300 pair screens and 24 conditional center/spread screens",
        ),
        (
            "Categorical intersections",
            {"category_relationship", "categorical_facets"},
            len(cats) * (len(cats) - 1) // 2,
            "First 10 focused dimensions, 20 pairs; complete small cross-tabs and up to four facets on request",
        ),
        (
            "Spatial applicability",
            set(),
            0,
            "Geographic meaning and task guards only; maps and spatial-transfer evaluation unavailable",
        ),
        (
            "Data and meaning fitness",
            {"missingness"},
            1,
            "Exact bounded profiling and recorded semantic decisions; declarations are not inferred domain truth",
        ),
    ]
    output = []
    for family, ops, available, scope in definitions:
        screens = [r for r in inv.candidate_log if r.get("operation") in ops]
        views = [f for f in inv.findings if f.family in ops or inv.results[f.result_id].plan.operation in ops]
        checked = sum(c.parent_id in {f.id for f in views} for c in inv.challenges)
        visited = sum(f.id in opened for f in views)
        excluded = (
            max(0, available - 300)
            if family == "Numeric relationships"
            else max(0, len(cats) * (len(cats) - 1) // 2 - 20)
            if family == "Categorical intersections"
            else max(0, len(nums) - 12)
            if family == "Distribution"
            else 0
        )
        blocked = [r.get("reason", "") for r in screens if r.get("eligible") is False and r.get("reason")]
        status = (
            "checked"
            if checked
            else "opened"
            if visited
            else "computed"
            if views
            else "screened"
            if screens
            else "available"
            if available
            else "blocked"
        )
        output.append(
            PerspectiveCoverage(
                family=family,
                status=status,
                scope=scope,
                reason="; ".join(dict.fromkeys(blocked))[:500]
                if blocked
                else "No applicable fields or supported operation"
                if not available
                else "",
                screened=len(screens),
                computed=len(views),
                opened=visited,
                checked=checked,
                outside_budget=excluded,
            ).model_dump(mode="json")
        )
    return output
