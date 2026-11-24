"""A few additional ways to see, chosen for a question rather than a chart gallery."""

from typing import Any

import numpy as np

from firstlook.types import Result, clean, digest, Request


def calculate(ds, request, meanings=None, rows=None, time_rules=None):
    from firstlook.analysis import _rows, _groups, _meaning, context_id, analyze

    allowed = {"category_relationship": {"auto", "share"}, "spatial": {"auto"}, "multivariate": {"auto"}}
    if request.representation not in allowed.get(request.view, set()):
        raise ValueError("Choose a supported representation for this perspective.")

    ids = _rows(ds, rows)
    frame = ds.frame.loc[ids]
    context = context_id(ds, meanings, ids, time_rules)
    meta, summary, warnings, omitted = {}, {"n": len(ids)}, [], 0
    if request.view == "category_relationship":
        if (
            not request.y
            or request.x == request.y
            or any(ds.field(f).kind not in {"category", "identifier"} for f in [request.x, request.y])
        ):
            raise ValueError("Choose two different categorical fields.")
        first, second = _groups(frame[request.x]), _groups(frame[request.y])
        groups, categories = sorted(first.unique()), sorted(second.unique())
        if len(groups) > 8 or len(categories) > 16:
            raise ValueError("Choose up to eight groups and sixteen categories for readable small multiples.")
        table = []
        for group in groups:
            group_rows = frame.index[first.eq(group)]
            denominator = len(group_rows)
            counts = second.loc[group_rows].value_counts()
            for category in categories:
                n = int(counts.get(category, 0))
                table.append(
                    {
                        "group": group,
                        "label": category,
                        "count": n,
                        "share": n / denominator if denominator else None,
                        "denominator": denominator,
                    }
                )
        meta = {"groups": groups, "categories": categories}
        definition = f"Recorded {ds.label(request.y)} within each {ds.label(request.x)} group. Each proportion uses its own group's recorded rows. Missing category labels are shown explicitly."
    elif request.view == "spatial":
        if (
            not request.y
            or request.x == request.y
            or any(ds.field(f).kind != "number" for f in [request.x, request.y])
        ):
            raise ValueError("Choose numerical latitude and longitude fields.")
        valid = frame[[request.x, request.y]].dropna()
        if not valid[request.x].between(-90, 90).all() or not valid[request.y].between(-180, 180).all():
            raise ValueError(
                "These values do not fit latitude/longitude degrees. Check the coordinate system before mapping."
            )
        shown = valid if len(valid) <= 2000 else valid.sample(2000, random_state=20261124).sort_index()
        table = [
            {"latitude": float(row[request.x]), "longitude": float(row[request.y]), "row": int(i)}
            for i, row in shown.iterrows()
        ]
        omitted = len(frame) - len(valid)
        meta = {"statistical_n": len(valid), "displayed": len(shown), "eligible_rows": list(valid.index)}
        definition = "Recorded locations, using the latitude/longitude degree interpretation you selected. Location patterns do not establish a cause."
        if len(shown) < len(valid):
            warnings.append(
                f"The map shows a fixed sample of {len(shown):,} of {len(valid):,} complete locations."
            )
    else:
        fields = list(dict.fromkeys(request.fields))
        if not 2 <= len(fields) <= 6 or any(ds.field(f).kind != "number" for f in fields):
            raise ValueError("Choose two to six numerical fields for a shared perspective.")
        if request.group:
            if (
                ds.field(request.group).kind not in {"category", "identifier"}
                or frame[request.group].nunique() > 12
                or len(fields) > 4
            ):
                raise ValueError("Ranked profiles use up to twelve items and four numerical fields.")
            columns = []
            for fid in fields:
                child = analyze(
                    ds,
                    Request(
                        "categories",
                        request.group,
                        fid,
                        metric=request.metric if request.metric in {"sum", "mean", "median"} else "mean",
                        attribution=request.attribution,
                    ),
                    meanings,
                    ids,
                    time_rules,
                )
                columns.append({r["label"]: r for r in child.table})
                warnings.extend(ds.label(fid) + ": " + w for w in child.warnings)
            labels = sorted(
                set().union(*(set(c) for c in columns)),
                key=lambda label: (
                    columns[0].get(label, {}).get("value") is None,
                    -(columns[0].get(label, {}).get("value") or 0),
                    label,
                ),
            )
            table = [
                {
                    "label": label,
                    **{fid: column.get(label, {}).get("value") for fid, column in zip(fields, columns)},
                }
                for label in labels
            ]
            meta["support"] = [
                {"label": label, **{fid: col.get(label, {}).get("n", 0) for fid, col in zip(fields, columns)}}
                for label in labels
            ]
            estimator = request.metric if request.metric in {"sum", "mean", "median"} else "mean"
            definition = f"Recorded {estimator} profiles by {ds.label(request.group)}, ranked on {ds.label(fields[0])}. Each column has its own units, scale and nonmissing support; compare shared patterns rather than bar lengths across columns."
        else:
            valid = frame[fields].dropna()
            shown = valid if len(valid) <= 350 else valid.sample(350, random_state=20261124).sort_index()
            table = [
                {"row": int(i), **{fid: float(row[fid]) for fid in fields}} for i, row in shown.iterrows()
            ]
            omitted = len(frame) - len(valid)
            meta.update(displayed=len(shown), statistical_n=len(valid), eligible_rows=list(valid.index))
            definition = "Recorded multivariate profiles; each vertical axis has its own units and range. Crossings describe these records, not verified clusters."
            if len(valid) > len(shown):
                warnings.append(
                    f"The view displays a fixed sample of {len(shown)} complete profiles from {len(valid):,} records."
                )
        meta["fields"] = fields
        meta["units"] = {fid: _meaning(meanings, fid).unit or ds.field(fid).unit for fid in fields}
        meta["ranges"] = {fid: clean([frame[fid].min(), frame[fid].max()]) for fid in fields}
    meta.setdefault("eligible_rows", ids)
    meta["population_rows"] = ids
    return Result(
        digest([context, request, table, meta]),
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


def extra_options(ds, result):
    """Native ECharts for a conditional categorical or multivariate question."""
    from firstlook.charts import PALETTE

    req, meta = result.request, result.meta
    option: dict[str, Any] = {
        "animation": False,
        "backgroundColor": "transparent",
        "color": PALETTE,
        "tooltip": {"trigger": "item", "confine": True},
        "textStyle": {"fontFamily": "Plex Sans, sans-serif"},
        "aria": {"enabled": True},
    }
    if req.view == "category_relationship":
        groups, categories = meta["groups"], meta["categories"]
        cols = min(len(groups), 3)
        rows = int(np.ceil(len(groups) / max(cols, 1)))
        share = req.representation == "share"
        maximum = 1 if share else max((r["count"] for r in result.table), default=1)
        option.update(grid=[], xAxis=[], yAxis=[], series=[], title=[])
        for i, group in enumerate(groups):
            left, top = (i % cols) * 100 / cols + 2, (i // cols) * 100 / rows + 11
            option["grid"].append(
                {
                    "left": f"{left}%",
                    "top": f"{top}%",
                    "width": f"{94 / cols - 4}%",
                    "height": f"{75 / rows - 6}%",
                    "containLabel": True,
                }
            )
            option["title"].append(
                {"text": group, "left": f"{left}%", "top": f"{top - 9}%", "textStyle": {"fontSize": 12}}
            )
            option["xAxis"].append({"type": "value", "min": 0, "max": maximum, "gridIndex": i})
            option["yAxis"].append(
                {
                    "type": "category",
                    "data": categories,
                    "inverse": True,
                    "gridIndex": i,
                    "axisLabel": {"width": 85, "overflow": "truncate"},
                }
            )
            data = [
                next(
                    r["share" if share else "count"]
                    for r in result.table
                    if r["group"] == group and r["label"] == c
                )
                for c in categories
            ]
            option["series"].append(
                {
                    "type": "bar",
                    "xAxisIndex": i,
                    "yAxisIndex": i,
                    "data": data,
                    "itemStyle": {"color": PALETTE[0]},
                    "barMaxWidth": 18,
                }
            )
    elif req.group:
        fields, labels = meta["fields"], [r["label"] for r in result.table]
        option.update(grid=[], xAxis=[], yAxis=[], series=[], title=[])
        for i, fid in enumerate(fields):
            width = 100 / len(fields)
            option["grid"].append(
                {
                    "left": f"{i * width + 2}%",
                    "top": 48,
                    "bottom": 42,
                    "width": f"{width - 4}%",
                    "containLabel": True,
                }
            )
            option["title"].append(
                {
                    "text": ds.label(fid) + (" (" + meta["units"][fid] + ")" if meta["units"][fid] else ""),
                    "left": f"{i * width + 2}%",
                    "textStyle": {"fontSize": 12},
                }
            )
            values = [r.get(fid) for r in result.table]
            option["xAxis"].append(
                {"type": "value", "min": min([0] + [v for v in values if v is not None]), "gridIndex": i}
            )
            option["yAxis"].append(
                {
                    "type": "category",
                    "inverse": True,
                    "data": labels,
                    "gridIndex": i,
                    "axisLabel": {"show": i == 0, "width": 80, "overflow": "truncate"},
                }
            )
            option["series"].append(
                {
                    "type": "bar",
                    "xAxisIndex": i,
                    "yAxisIndex": i,
                    "data": values,
                    "barMaxWidth": 20,
                    "itemStyle": {"color": PALETTE[i]},
                }
            )
    else:
        fields = meta["fields"]
        axes = []
        for i, fid in enumerate(fields):
            low, high = meta["ranges"][fid]
            axes.append(
                {
                    "dim": i,
                    "name": ds.label(fid) + (" (" + meta["units"][fid] + ")" if meta["units"][fid] else ""),
                    "min": low,
                    "max": high if high != low else (high or 0) + 1,
                }
            )
        option.update(
            parallel={"left": 65, "right": 55, "top": 45, "bottom": 45},
            parallelAxis=axes,
            series=[
                {
                    "type": "parallel",
                    "lineStyle": {"width": 1, "opacity": 0.18},
                    "data": [[r[fid] for fid in fields] for r in result.table],
                }
            ],
        )
    return clean(option)
