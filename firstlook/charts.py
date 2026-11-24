"""Finite ECharts representations of recorded results, with truthful comparison scales."""

from firstlook.types import clean

PALETTE = ["#3157CE", "#208F84", "#BE7148", "#9271B5", "#9C8531", "#647B9C", "#C46A91", "#4995AD"]


def _axis(name="", kind="value", bounds=None, zero=False):
    axis = {
        "type": kind,
        "name": name,
        "nameLocation": "middle",
        "nameGap": 34,
        "axisLabel": {"hideOverlap": True},
        "splitLine": {"show": kind == "value"},
    }
    if bounds and len(bounds) == 2 and all(v is not None for v in bounds):
        low, high = bounds
        if low == high:
            pad = abs(low) * 0.05 or 1
            low, high = low - pad, high + pad
        axis.update(min=min(0, low) if zero else low, max=max(0, high) if zero else high)
    elif zero:
        axis["min"] = 0
    return axis


def _name(ds, fid, result=None):
    if not fid:
        return ""
    field = ds.field(fid)
    unit = result.meta.get("units", {}).get(fid, field.unit) if result else field.unit
    return ds.label(fid) + (" (" + unit + ")" if unit else "")


def options(ds, result, comparison=None):
    if result.request.view in {"category_relationship", "multivariate"}:
        from firstlook.perspectives import extra_options

        return extra_options(ds, result)
    req = result.request
    results = (
        [("Selected", comparison.selected), ("Reference", comparison.reference)]
        if comparison
        else [("Recorded", result)]
    )
    option = {
        "animation": False,
        "backgroundColor": "transparent",
        "color": PALETTE,
        "textStyle": {"fontFamily": "Plex Sans, sans-serif"},
        "tooltip": {"trigger": "axis", "confine": True},
        "grid": {"left": 64, "right": 22, "top": 32, "bottom": 58, "containLabel": True},
        "legend": {"show": bool(comparison), "top": 0},
        "aria": {"enabled": True},
        "series": [],
    }
    if req.view == "relationship":
        option["tooltip"] = {"trigger": "item", "confine": True}
        # Keep the *data region* square: theme-driven label containment otherwise
        # subtracts different margins from its width and height.
        option["grid"] = {
            "left": 72,
            "top": 40,
            "width": 340,
            "height": 340,
            "containLabel": False,
            "outerBoundsMode": "none",
        }
        option["media"] = [
            {"query": {"maxWidth": 500}, "option": {"grid": {"width": 290, "height": 290}}},
            {"query": {"maxWidth": 390}, "option": {"grid": {"left": 56, "width": 220, "height": 220}}},
        ]
        option["xAxis"] = _axis(_name(ds, req.x, result), bounds=result.meta.get("x_bounds"))
        option["yAxis"] = _axis(_name(ds, req.y, result), bounds=result.meta.get("y_bounds"))
        option["yAxis"].update(nameRotate=90, nameGap=48)
        series = []
        for population, record in results:
            groups = sorted({r["group"] for r in record.table})
            for group in groups:
                points = [r for r in record.table if r["group"] == group]
                levels = sorted(ds.frame[req.group].dropna().astype(str).unique()) if req.group else []
                colour = PALETTE[levels.index(group) % len(PALETTE)] if group in levels else PALETTE[0]
                series.append(
                    {
                        "type": "scatter",
                        "name": population if comparison else group,
                        "data": [[r["x"], r["y"], r["row"]] for r in points],
                        "symbolSize": 7,
                        "itemStyle": {"opacity": 0.68, "color": colour},
                        "encode": {"x": 0, "y": 1, "tooltip": [0, 1]},
                    }
                )
        option["series"] = series
        option["legend"]["show"] = len(series) > 1
    elif req.view in {"distribution", "groups"}:
        normalized = bool(comparison or result.meta.get("comparison_measure"))
        option["xAxis"] = _axis(_name(ds, req.x, result), bounds=result.meta.get("x_bounds"))
        option["yAxis"] = _axis(
            "Within-population share" if normalized or req.view == "groups" else "Recorded observations",
            bounds=result.meta.get("y_bounds"),
            zero=True,
        )
        if req.view == "distribution" and not normalized:
            # Each bar retains its numeric interval, rather than becoming an ordinal category.
            table = result.table
            width = table[0]["high"] - table[0]["low"] if table else 1
            option["series"] = [
                {
                    "type": "bar",
                    "barWidth": "95%",
                    "barGap": "0%",
                    "data": [[(r["low"] + r["high"]) / 2, r["count"]] for r in table],
                    "encode": {"x": 0, "y": 1},
                    "itemStyle": {"color": PALETTE[0]},
                    "dimensions": ["Bin midpoint", "Recorded observations"],
                }
            ]
            # Native ECharts uses coordinate-aligned centers with explicit equal source intervals.
            option["xAxis"]["minInterval"] = width
        else:
            series = []
            for population, record in results:
                groups = sorted({r["label"] for r in record.table}) if req.view == "groups" else [population]
                for group in groups:
                    table = [r for r in record.table if r.get("label", group) == group]
                    levels = sorted(ds.frame[req.group].dropna().astype(str).unique()) if req.group else []
                    colour = PALETTE[levels.index(group) % len(PALETTE)] if group in levels else PALETTE[0]
                    series.append(
                        {
                            "type": "line",
                            "name": population + " · " + group
                            if comparison and req.view == "groups"
                            else group,
                            "showSymbol": False,
                            "data": [[(r["low"] + r["high"]) / 2, r["share"]] for r in table],
                            "lineStyle": {"width": 2, "color": colour},
                        }
                    )
            option["series"] = series
            option["legend"]["show"] = len(series) > 1
    elif req.view == "time":
        option["xAxis"] = _axis(_name(ds, req.x, result), "time")
        if result.meta.get("time_bounds"):
            option["xAxis"].update(min=result.meta["time_bounds"][0], max=result.meta["time_bounds"][1])
        option["yAxis"] = _axis(
            req.metric.replace("_", " ") + (" · " + _name(ds, req.y, result) if req.y else ""),
            bounds=result.meta.get("y_bounds"),
            zero=req.metric in {"count", "sum", "distinct"},
        )
        option["series"] = [
            {
                "type": "line",
                "name": name,
                "data": [[r["date"], r["value"]] for r in record.table],
                "connectNulls": False,
                "showSymbol": len(record.table) <= 60,
                "symbolSize": 5,
                "lineStyle": {"width": 2},
            }
            for name, record in results
        ]
    else:
        labels = result.meta.get("labels") or list(
            dict.fromkeys(r["label"] for _, record in results for r in record.table)
        )
        option["grid"]["left"] = 12
        option["xAxis"] = _axis(
            "Missing records" if req.view == "missingness" else req.metric.replace("_", " "),
            bounds=result.meta.get("y_bounds"),
            zero=True,
        )
        option["yAxis"] = _axis(kind="category")
        option["yAxis"].update(data=labels, inverse=True, axisLabel={"width": 160, "overflow": "truncate"})
        option["series"] = [
            {
                "type": "bar",
                "name": name,
                "data": [
                    next((r.get("value", r.get("count")) for r in record.table if r["label"] == label), None)
                    for label in labels
                ],
                "barMaxWidth": 28,
            }
            for name, record in results
        ]
    return clean(_representation(ds, result, results, option))


def _representation(ds, result, results, option):
    req, mode = result.request, result.request.representation
    if req.view in {"distribution", "groups"} and mode == "box":
        groups = (
            [
                {
                    **stats,
                    "label": population + " · " + stats["label"] if len(results) > 1 else stats["label"],
                }
                for population, record in results
                for stats in record.meta.get("group_stats", [])
            ]
            if req.view == "groups"
            else [{"label": population, **record.summary} for population, record in results]
        )
        option["xAxis"] = _axis(kind="category")
        option["xAxis"]["data"] = [r["label"] for r in groups]
        option["yAxis"] = _axis(_name(ds, req.x, result), bounds=result.meta.get("x_bounds"))
        option["legend"]["show"] = False
        option["series"] = [
            {
                "type": "boxplot",
                "data": [
                    [r[k] for k in ["min", "q1", "median", "q3", "max"]] if r.get("n", 0) else [None] * 5
                    for r in groups
                ],
                "itemStyle": {"color": "#D8E6F4", "borderColor": PALETTE[0]},
            }
        ]
    elif req.view == "distribution" and mode in {"frequency", "quantile"}:
        quantile = mode == "quantile"
        option["yAxis"] = _axis(
            "Cumulative fraction at saved quantiles"
            if quantile
            else "Within-population share"
            if len(results) > 1 or result.meta.get("comparison_measure")
            else "Recorded observations",
            bounds=result.meta.get("y_bounds") if not quantile else None,
            zero=True,
        )
        if quantile:
            option["yAxis"].update(min=0, max=1)
        option["series"] = [
            {
                "name": name,
                "type": "line",
                "showSymbol": False,
                "data": [[p["value"], p["probability"]] for p in record.meta.get("quantiles", [])]
                if quantile
                else [
                    [
                        (r["low"] + r["high"]) / 2,
                        r["share"]
                        if len(results) > 1 or result.meta.get("comparison_measure")
                        else r["count"],
                    ]
                    for r in record.table
                ],
            }
            for name, record in results
        ]
    elif req.view == "categories" and mode == "treemap":
        if not result.meta.get("composition"):
            raise ValueError(
                "This definition is not a nonnegative partition. Use ranked bars to preserve its meaning."
            )
        option = {
            "animation": False,
            "tooltip": {"confine": True},
            "series": [
                {
                    "type": "treemap",
                    "roam": False,
                    "breadcrumb": {"show": False},
                    "label": {"show": True},
                    "data": [
                        {"name": r["label"], "value": r["value"]} for r in result.table if r["value"] > 0
                    ],
                }
            ],
        }
    elif req.view == "time":
        if mode == "calendar":
            cells = result.meta.get("calendar_cells", [])
            values = [r["value"] for r in cells if r["value"] is not None]
            low, high = min(values, default=0), max(values, default=1)
            return {
                "animation": False,
                "tooltip": {"position": "top", "confine": True},
                "grid": {"left": 75, "right": 30, "top": 25, "bottom": 90},
                "xAxis": {"type": "category", "data": list(range(24)), "name": "Recorded hour"},
                "yAxis": {
                    "type": "category",
                    "data": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    "inverse": True,
                },
                "visualMap": {
                    "min": low,
                    "max": high if high > low else low + 1,
                    "orient": "horizontal",
                    "left": "center",
                    "bottom": 0,
                    "inRange": {"color": ["#F0F5FA", "#246A93"]},
                },
                "series": [
                    {
                        "type": "heatmap",
                        "data": [
                            [r["hour"], r["weekday"], r["value"]] for r in cells if r["value"] is not None
                        ],
                    }
                ],
            }
        if mode == "bars":
            for series in option["series"]:
                series["type"] = "bar"
        if mode in {"share", "smooth", "deviation"}:
            for series, (_, record) in zip(option["series"], results):
                if mode == "share":
                    option["yAxis"] = _axis(
                        "Share of this series' recorded total", bounds=result.meta.get("y_bounds"), zero=True
                    )
                else:
                    option["yAxis"] = _axis(
                        "Deviation from trailing three-period mean"
                        if mode == "deviation"
                        else "Trailing three-period mean",
                        bounds=result.meta.get("y_bounds"),
                    )
                series["data"] = [[r["date"], r["value"]] for r in record.meta["plotted_values"]]
    return option
