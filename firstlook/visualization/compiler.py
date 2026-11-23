"""Compile a finite chart catalog and keep every mark linked to its source rows."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, cast
import math

import pandas as pd

from firstlook.contracts import ChartSpec, ResultArtifact, digest
from firstlook.visualization.layout import chart_dimensions, square_geometry

PALETTE = ["#4169D8", "#209589", "#C67049", "#9774BD", "#A58A30", "#647B9C", "#CD7099", "#5598B0"]
DARK_PALETTE = ["#86A9FF", "#63CFBD", "#E8A47D", "#B59ADD", "#D5BD67", "#9DB6DC", "#EA9DC3", "#84BDCE"]


def category_label(record):
    return str(record["label"]) + (" (pooled)" if record.get("other") else "")


def encoded_records(spec: ChartSpec, result: ResultArtifact) -> list[dict]:
    """Select a validated quantity without mutating the recorded result artifact."""
    if getattr(spec, "value_field", "value") == "amount":
        from firstlook.visualization.composition import amount_records

        return amount_records(result)
    return result.records


def category_color(label: str, dark: bool = False) -> str:
    """A category keeps its colour when another view omits or reorders groups."""
    palette = DARK_PALETTE if dark else PALETTE
    return palette[int(hashlib.sha256(str(label).encode()).hexdigest()[:8], 16) % len(palette)]


def series_colors(result: ResultArtifact, dark: bool = False) -> dict[str, str]:
    """Resolve collisions within a declared or sorted series universe.

    Recording ``series_order`` keeps that universe fixed across subset views.
    The eight-colour palette is finite; more groups require separate panels.
    """
    palette = DARK_PALETTE if dark else PALETTE
    observed = sorted({str(row.get("group", "")) for row in result.records})
    universe = list(
        dict.fromkeys([str(value) for value in result.metadata.get("series_order", [])] + observed)
    )
    used: set[int] = set()
    output = {}
    for label in universe:
        index = int(hashlib.sha256(label.encode()).hexdigest()[:8], 16) % len(palette)
        if len(used) < len(palette):
            while index in used:
                index = (index + 1) % len(palette)
            used.add(index)
        output[label] = palette[index]
    return output


def categorical_order(result: ResultArtifact, axis: str) -> list[str]:
    """Share the recorded category ordering with the offscreen renderer."""
    declared = result.metadata.get("category_order", {}).get(axis) or result.metadata.get(axis + "_levels")
    observed = list(dict.fromkeys(str(row[axis]) for row in result.records))
    if declared:
        return list(dict.fromkeys([str(value) for value in declared] + observed))
    return observed


def residual_colors(result: ResultArtifact) -> bool:
    return result.metadata.get("normalization", result.plan.params.get("normalization")) == "residual"


def color_domain(result: ResultArtifact) -> tuple[float, float]:
    values = [float(row["value"]) for row in result.records if row.get("value") is not None]
    if residual_colors(result):
        extent = max((abs(value) for value in values), default=0.0) or 1.0
        return -extent, extent
    return min(0.0, min(values, default=0.0)), max(values, default=0.0) or 1.0


def heatmap_colors(result: ResultArtifact, dark: bool = False) -> list[str]:
    if residual_colors(result):
        return ["#BF6A42", "#F3F4F6", "#4169D8"]
    return ["#182235", "#4169D8", "#B9CDFF"] if dark else ["#EDF2FB", "#7294E8", "#2349A2"]


def axis_domains(spec: ChartSpec, result: ResultArtifact) -> dict[str, tuple[float, float]]:
    """One explicit domain policy for the interactive and offscreen renderers."""
    rows = encoded_records(spec, result)
    domains: dict[str, tuple[float, float]] = {}

    def span(axis: str, keys: list[str], zero: bool = False):
        values = [
            float(row[key])
            for row in rows
            for key in keys
            if isinstance(row.get(key), (int, float)) and math.isfinite(row[key])
        ]
        if not values:
            return
        lo, hi = min(values), max(values)
        if axis == "y" and spec.scale == "log":
            domains[axis] = (lo / 1.05, hi * 1.05)
            return
        pad = (hi - lo) * 0.05 if hi > lo else max(abs(hi) * 0.05, 1.0)
        lower = min(0.0, lo - pad) if zero and lo < 0 else 0.0 if zero else lo - pad
        upper = max(0.0, hi + pad) if zero else hi + pad
        if lower == upper:
            lower, upper = (-1.0, 1.0) if spec.template == "quantile_difference" else (0.0, 1.0)
        width = upper - lower
        if math.isfinite(width) and width > 0:
            step = 10.0 ** (math.floor(math.log10(width)) - 1)
            if step > 0:
                lower = min(lower, float(f"{math.floor(lower / step) * step:.12g}"))
                upper = max(upper, float(f"{math.ceil(upper / step) * step:.12g}"))
        domains[axis] = lower, upper

    if spec.template == "scatter":
        span("x", ["x"])
        span("y", ["y"], result.metadata.get("reference") == "zero")
        for axis, bounds in result.metadata.get("full_pair_domains", {}).items():
            lo, hi = bounds
            pad = (hi - lo) * 0.05 if hi > lo else max(abs(hi) * 0.05, 1)
            domains[axis] = (lo - pad, hi + pad)
    elif spec.template in {"histogram", "frequency_polygon"}:
        span("x", ["left", "right"] if "left" in rows[0] else ["x"])
        span("y", ["value"], True)
    elif spec.template in {"bar", "dot", "facet"}:
        span("x", ["value"], spec.template in {"bar", "facet"})
        if result.metadata.get("proportion"):
            domains["x"] = (0.0, 1.0)
        if spec.template == "dot" and result.metadata.get("correlation"):
            domains["x"] = (-1.0, 1.0)
    elif spec.template == "box":
        span("y", ["min", "max"])
    elif spec.template in {"line", "ecdf", "quantile_difference"}:
        if not result.metadata.get("time_axis"):
            span("x", ["x"])
        else:
            stamps = [
                cast(Any, pd.Timestamp(row["x"])).timestamp() * 1000
                for row in rows
                if row.get("x") is not None
            ]
            if stamps:
                lo, hi = min(stamps), max(stamps)
                pad = (hi - lo) * 0.03 if hi > lo else 86400000
                domains["x"] = (lo - pad, hi + pad)
        span(
            "y",
            ["value", "q1", "q3"] if result.metadata.get("conditional_spread") else ["value"],
            spec.template == "quantile_difference",
        )
        if spec.template == "ecdf":
            domains["y"] = (0.0, 1.0)
        elif spec.template == "quantile_difference":
            domains["x"] = (0.0, 1.0)

    for axis, bounds in result.metadata.get("comparison_domains", {}).items():
        if axis not in {"x", "y"} or len(bounds) != 2:
            raise ValueError("Comparison axes require two finite ordered bounds.")
        lo, hi = map(float, bounds)
        if not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi:
            raise ValueError("Comparison axes require two finite ordered bounds.")
        domains[axis] = (lo, hi)

    zero_axis = (
        "x"
        if spec.template in {"bar", "facet"}
        else "y"
        if spec.template in {"histogram", "frequency_polygon", "quantile_difference"}
        or result.metadata.get("reference") == "zero"
        else None
    )
    if zero_axis and zero_axis in domains:
        lo, hi = domains[zero_axis]
        if not lo <= 0 <= hi:
            raise ValueError("This chart's declared comparison domain must include zero.")
    if spec.template == "scatter" and result.metadata.get("reference") == "identity":
        shared = min(domains["x"][0], domains["y"][0]), max(domains["x"][1], domains["y"][1])
        domains["x"] = domains["y"] = shared
    return domains


@dataclass
class CompiledChart:
    options: dict
    row_map: dict[tuple[int, int], list[int]]
    mapping_hash: str


def plotting_records(spec, result, source=None):
    """CDF endpoint extensions are display geometry, never invented observations."""
    rows = encoded_records(spec, result) if source is None else source
    if spec.template != "ecdf":
        return rows
    lo, hi = axis_domains(spec, result)["x"]
    groups = list(dict.fromkeys(r.get("group", "") for r in rows))
    output = []
    for group in groups:
        subset = [r for r in rows if r.get("group", "") == group]
        identity = {"group": group} if "group" in subset[0] else {}
        output.append({"x": lo, "value": 0.0, "row_ids": [], "endpoint_extension": True, **identity})
        output.extend({**r, "endpoint_extension": False} for r in subset)
        output.append({"x": hi, "value": 1.0, "row_ids": [], "endpoint_extension": True, **identity})
    return output


def validate_chart(spec: ChartSpec, result: ResultArtifact) -> None:
    if spec.result_id != result.id or spec.context != result.plan.context:
        raise ValueError("The chart and result belong to different contexts.")
    if result.support < 1 or not result.records:
        raise ValueError("A chart requires supported data.")
    if spec.template in {"bar", "histogram", "facet"} and not spec.zero_baseline:
        raise ValueError("Magnitude bars require a zero baseline.")
    if spec.template == "treemap" and getattr(spec, "value_field", "value") != "amount":
        raise ValueError("Treemap areas must bind validated original amounts, not cumulative shares.")
    encoded_records(spec, result)
    if spec.template in {"histogram", "frequency_polygon"}:
        histogram_bin_width(result.records)
    if spec.template == "quantile_difference" and any(
        not isinstance(row.get("x"), (int, float)) or not 0 <= row["x"] <= 1 for row in result.records
    ):
        raise ValueError("Quantile differences require quantile positions between zero and one.")
    if spec.scale == "log":
        if result.metadata.get("reference") in {"identity", "zero"}:
            raise ValueError("Identity and zero diagnostic references require matching linear coordinates.")
        if spec.template not in {"scatter", "line"}:
            raise ValueError("Log scales are supported only on numerical scatter and line ordinates.")
        values = [r.get("value", r.get("y")) for r in result.records]
        if any(v is not None and (not isinstance(v, (int, float)) or v <= 0) for v in values):
            raise ValueError("A log scale requires positive numerical values.")
    axis_domains(spec, result)


def histogram_bin_width(rows: list[dict]) -> float | None:
    """Only equal, contiguous recorded bins are supported by native value bars."""
    if any("group" in row for row in rows):
        groups = list(dict.fromkeys(str(row.get("group", "")) for row in rows))
        parts = [
            [
                {key: value for key, value in row.items() if key != "group"}
                for row in rows
                if str(row.get("group", "")) == group
            ]
            for group in groups
        ]
        widths = [histogram_bin_width(part) for part in parts]
        edges = [[(row.get("left"), row.get("right")) for row in part] for part in parts]
        if any(edge != edges[0] for edge in edges[1:]):
            raise ValueError("Grouped frequency polygons require the same recorded bin boundaries.")
        return widths[0]
    if all("left" not in row and "right" not in row for row in rows):
        return None  # Legacy inspection-only artifacts may predate recorded edges.
    previous = None
    width = None
    for row in rows:
        left, right, center = row.get("left"), row.get("right"), row.get("x")
        if not all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in (left, right, center)
        ):
            raise ValueError("Histogram bounds and midpoint must be finite.")
        left, right, center = (float(cast(Any, value)) for value in (left, right, center))
        current = right - left
        coordinate_tolerance = max(1e-10, *(4 * math.ulp(value) for value in (left, right, center)))
        if current <= 0 or not math.isclose(
            center, left + current / 2, rel_tol=0, abs_tol=coordinate_tolerance
        ):
            raise ValueError("Histogram midpoints must match positive recorded bin widths.")
        if width is not None and not math.isclose(current, width, rel_tol=1e-8, abs_tol=1e-10):
            raise ValueError("Native histograms require equal-width recorded bins.")
        if previous is not None and not math.isclose(left, previous, rel_tol=0, abs_tol=coordinate_tolerance):
            raise ValueError("Histogram bins must be contiguous and ordered.")
        previous, width = right, current
    return width


def compile_chart(
    spec: ChartSpec,
    result: ResultArtifact,
    dark: bool = False,
    *,
    width: int | str | None = None,
    height: int | None = None,
) -> CompiledChart:
    validate_chart(spec, result)
    ink = "#B5C4DB" if dark else "#58677F"
    grid = "#2B3A51" if dark else "#E5EAF3"
    rows = plotting_records(spec, result)
    base_color = result.metadata.get("comparison_color", PALETTE[0])
    group_colors = series_colors(result, dark)
    default_width, default_height = chart_dimensions(spec, result, height or 310)
    actual_width, actual_height = width or default_width, height or default_height
    options: dict[str, Any] = {
        "animationDuration": 250,
        "animationDurationUpdate": 250,
        "textStyle": {"fontFamily": "Plex Sans, sans-serif", "fontSize": 12, "color": ink},
        "grid": {"left": 64, "right": 24, "top": 32, "bottom": 68, "containLabel": True},
        "tooltip": {"trigger": "item", "confine": True},
        "aria": {"enabled": True},
        "xAxis": {
            "type": "value",
            "name": spec.x_label,
            "nameLocation": "middle",
            "nameGap": 38,
            "axisLabel": {"color": ink},
            "splitLine": {"lineStyle": {"color": grid}},
        },
        "yAxis": {
            "type": "value",
            "name": spec.y_label,
            "nameGap": 20,
            "axisLabel": {"color": ink},
            "splitLine": {"lineStyle": {"color": grid}},
        },
    }
    x_axis = cast(dict[str, Any], options["xAxis"])
    y_axis = cast(dict[str, Any], options["yAxis"])
    mapping: dict[tuple[int, int], list[int]] = {}
    series: list[dict[str, Any]] = []
    datasets = []

    def install(
        source: list[dict], kind: str, encode: dict, name: str = "", color: str | None = None
    ) -> None:
        idx = len(series)
        for i, r in enumerate(source):
            ids = r.get("row_ids", [r["row_id"]] if "row_id" in r else [])
            mapping[idx, i] = [int(v) for v in ids]
        data = pd.DataFrame([{k: v for k, v in r.items() if k not in {"row_ids", "row_id"}} for r in source])
        datasets.append({"source": data})
        item = {"id": f"s{idx}", "name": name, "type": kind, "datasetIndex": idx, "encode": encode}
        if any(mapping[idx, i] for i in range(len(source))):
            item["selectedMode"] = "multiple"
            item["select"] = {"itemStyle": {"borderColor": "#172F74", "borderWidth": 2}}
        if color:
            item["itemStyle"] = {"color": color, "opacity": 0.8}
        series.append(item)

    if spec.template == "scatter":
        groups = list(dict.fromkeys(str(r.get("group", "")) for r in rows))
        for i, group in enumerate(groups):
            subset = [r for r in rows if str(r.get("group", "")) == group]
            install(
                subset,
                "scatter",
                {
                    "x": "x",
                    "y": "y",
                    "tooltip": [key for key in ["x", "y", "cook", "residual"] if key in subset[0]],
                },
                group,
                group_colors[group] if group else base_color,
            )
            series[-1].update(symbolSize=5 if len(rows) > 1000 else 6)
            series[-1]["itemStyle"]["opacity"] = 0.55 if len(rows) > 1000 else 0.72
        options["brush"] = {"xAxisIndex": "all", "brushMode": "multiple"}
        options["toolbox"] = {"left": 8, "feature": {"brush": {"type": ["rect", "clear"]}}}
        if len(groups) > 1:
            options["legend"] = {"top": 0, "type": "scroll", "textStyle": {"color": ink}}
        reference = result.metadata.get("reference")
        if reference in {"identity", "zero"}:
            domain = axis_domains(spec, result)
            points = (
                [{"coord": [domain["x"][0], domain["x"][0]]}, {"coord": [domain["x"][1], domain["x"][1]]}]
                if reference == "identity"
                else {"yAxis": 0, "name": "Zero residual"}
            )
            series[0]["markLine"] = {
                "silent": True,
                "symbol": ["none", "none"],
                "lineStyle": {"color": ink, "type": "dashed", "width": 1},
                "label": {"show": False},
                "data": [points],
            }
    elif spec.template in {"bar", "dot"}:
        install(
            [{**r, "position": i} for i, r in enumerate(rows)],
            "bar" if spec.template == "bar" else "scatter",
            {
                "x": "value",
                "y": "position",
                "tooltip": ["label", "value", *(["n", "member_rows"] if "member_rows" in rows[0] else [])],
            },
            color=base_color,
        )
        y_axis.update(
            {
                "type": "category",
                "name": "",
                "inverse": True,
                "axisLabel": {"color": ink, "width": 125, "overflow": "truncate"},
                "data": [category_label(r) for r in rows],
            }
        )
        if spec.template == "bar":
            x_axis["min"] = min(0, min(float(r["value"]) for r in rows if r["value"] is not None))
            series[0]["barMaxWidth"] = 26
            options["grid"]["left"] = 130
        else:
            series[0]["symbolSize"] = 13
        from firstlook.visualization.composition import labelled_part_capacity

        capacity = labelled_part_capacity(actual_height)
        if len(rows) > capacity:
            options["dataZoom"] = [
                {
                    "type": "slider",
                    "yAxisIndex": 0,
                    "orient": "vertical",
                    "right": 0,
                    "width": 12,
                    "filterMode": "none",
                    "startValue": 0,
                    "endValue": capacity - 1,
                    "showDetail": False,
                }
            ]
    elif spec.template in {"histogram", "frequency_polygon"}:
        groups = list(dict.fromkeys(str(row.get("group", "")) for row in rows))
        if spec.template == "histogram" and len(groups) > 1:
            raise ValueError("Grouped distributions use frequency polygons or separate histogram panels.")
        for group in groups:
            part = [row for row in rows if str(row.get("group", "")) == group]
            install(
                part,
                "bar" if spec.template == "histogram" else "line",
                {
                    "x": "x",
                    "y": "value",
                    "tooltip": [
                        key for key in ["group", "label", "value", "count", "left", "right"] if key in part[0]
                    ],
                },
                group,
                color=group_colors[group] if group else base_color,
            )
            if spec.template == "histogram":
                bin_width = histogram_bin_width(part)
                # Percent width uses the minimum midpoint interval. A single
                # value instead has an 80%-of-axis-span native fallback band.
                percent = 100.0
                if len(part) == 1 and bin_width is not None:
                    lo, hi = axis_domains(spec, result)["x"]
                    percent = 100 * bin_width / ((hi - lo) * 0.8)
                series[-1].update(
                    barWidth=f"{percent:.12g}%", barCategoryGap="0%", barGap=0, barMinWidth=0.01
                )
            else:
                series[-1].update(smooth=False, connectNulls=False, showSymbol=True, symbolSize=4)
        if len(groups) > 1:
            options["legend"] = {"top": 0, "type": "scroll", "textStyle": {"color": ink}}
        median, q1, q3 = (result.metrics.get(key) for key in ("median", "q1", "q3"))
        if len(groups) == 1 and isinstance(median, (int, float)):
            series[0]["markLine"] = {
                "silent": True,
                "symbol": ["none", "none"],
                "lineStyle": {"color": ink, "type": "dashed", "width": 1},
                "label": {"show": True, "formatter": "Median", "color": ink},
                "data": [{"xAxis": median}],
            }
        if len(groups) == 1 and all(isinstance(value, (int, float)) for value in (q1, q3)):
            series[0]["markArea"] = {
                "silent": True,
                "label": {"show": False},
                "itemStyle": {"color": base_color, "opacity": 0.07},
                "data": [[{"xAxis": q1}, {"xAxis": q3}]],
            }
        y_axis["min"] = 0
    elif spec.template == "box":
        install(
            rows,
            "boxplot",
            {
                "x": "label",
                "y": ["min", "q1", "median", "q3", "max"],
                "tooltip": ["label", "n", "min", "q1", "median", "q3", "max"],
            },
        )
        x_axis.update({"type": "category"})
        series[0]["itemStyle"] = {"color": "#C3D1F7", "borderColor": base_color}
        series[0]["boxWidth"] = [12, 34]
    elif spec.template == "quantile_difference":
        install(
            rows,
            "scatter",
            {
                "x": "x",
                "y": "value",
                "tooltip": [
                    key
                    for key in ["x", "value", "selected", "reference", "first", "second"]
                    if key in rows[0]
                ],
            },
            color=base_color,
        )
        series[0].update(symbolSize=8)
        series[0]["markLine"] = {
            "silent": True,
            "symbol": ["none", "none"],
            "lineStyle": {"color": ink, "type": "dashed", "width": 1},
            "label": {"show": False},
            "data": [{"yAxis": 0}],
        }
    elif spec.template in {"line", "ecdf"}:
        x_axis["type"] = "time" if result.metadata.get("time_axis") else "value"
        groups = list(dict.fromkeys(str(r.get("group", "")) for r in rows))
        for i, group in enumerate(groups):
            subset = [r for r in rows if str(r.get("group", "")) == group]
            tooltip = [
                k
                for k in [
                    "x",
                    "value",
                    "q1",
                    "q3",
                    "n",
                    "synthetic",
                    "complete",
                    "original_value",
                    "date",
                    "endpoint_extension",
                ]
                if k in rows[0]
            ]
            install(
                subset,
                "line",
                {"x": "x", "y": "value", "tooltip": tooltip},
                group,
                group_colors[group] if group else base_color,
            )
            series[-1].update(
                connectNulls=False,
                symbolSize=4,
                lineStyle={
                    "width": 2.3,
                    "type": "dashed" if any(r.get("synthetic") for r in subset) else "solid",
                },
            )
            if spec.template == "ecdf":
                series[-1]["step"] = "end"
            if result.metadata.get("conditional_spread"):
                for key, label in [("q1", "25th percentile"), ("q3", "75th percentile")]:
                    install(subset, "line", {"x": "x", "y": key, "tooltip": tooltip}, label, PALETTE[1])
                    series[-1].update(
                        connectNulls=False, showSymbol=False, lineStyle={"type": "dashed", "width": 1.5}
                    )
        if len(series) > 1:
            options["legend"] = {"top": 0, "textStyle": {"color": ink}}
    elif spec.template in {"heatmap", "density"}:
        if spec.template == "density":
            numeric_grid = result.metadata["numeric_grid"]
            xs = [str(i) for i in range(len(numeric_grid["x_edges"]) - 1)]
            ys = [str(i) for i in range(len(numeric_grid["y_edges"]) - 1)]
        else:
            xs, ys = categorical_order(result, "x"), categorical_order(result, "y")
        heat = [{**r, "x": xs.index(str(r["x"])), "y": ys.index(str(r["y"]))} for r in rows]
        install(
            heat,
            "heatmap",
            {
                "x": "x",
                "y": "y",
                "value": "value",
                "tooltip": [
                    k
                    for k in ["value", "count", "denominator", "left", "right", "bottom", "top"]
                    if k in rows[0]
                ],
            },
        )
        if spec.template == "density":
            xe, ye = result.metadata["numeric_grid"]["x_edges"], result.metadata["numeric_grid"]["y_edges"]
            xs = [f"{a:.3g}–{b:.3g}" for a, b in zip(xe, xe[1:])]
            ys = [f"{a:.3g}–{b:.3g}" for a, b in zip(ye, ye[1:])]
        x_axis.update({"type": "category", "data": xs, "splitLine": {"show": False}})
        y_axis.update(
            {
                "type": "category",
                "data": ys,
                "splitLine": {"show": False},
                "inverse": spec.template == "heatmap",
            }
        )
        color_min, color_max = color_domain(result)
        options["visualMap"] = {
            "min": color_min,
            "max": color_max,
            "calculable": False,
            "orient": "horizontal",
            "bottom": 0,
            "left": "center",
            "text": [f"{color_max:.3g}", f"{color_min:.3g}"],
            "textStyle": {"color": ink},
            "inRange": {"color": heatmap_colors(result, dark)},
        }
        options["grid"]["bottom"] = 95
    elif spec.template == "treemap":
        data = []
        # ECharts' implicit root occupies flattened data index zero. There is
        # no analytical member at that index; supplied flat parts start at one.
        mapping[0, 0] = []
        for i, row in enumerate(rows):
            ids = row.get("row_ids", [row["row_id"]] if "row_id" in row else [])
            mapping[0, i + 1] = [int(value) for value in ids]
            label = category_label(row)
            data.append(
                {
                    "id": str(row.get("key") or digest([label, i])),
                    "name": label,
                    "value": row["value"],
                    "original_index": i,
                    "share": row.get("share"),
                    "itemStyle": {"color": base_color},
                }
            )
        series.append(
            {
                "id": "parts",
                "type": "treemap",
                "data": data,
                "left": 0,
                "right": 0,
                "top": 8,
                "bottom": 8,
                "roam": False,
                "nodeClick": False,
                "sort": False,
                "leafDepth": 1,
                "visibleMin": 0,
                "childrenVisibleMin": 0,
                "breadcrumb": {"show": False},
                "upperLabel": {"show": False},
                "label": {"show": True, "formatter": "{b}", "overflow": "truncate"},
                "itemStyle": {
                    "borderWidth": 1,
                    "gapWidth": 1,
                    "borderColor": "#182235" if dark else "#FFFFFF",
                },
                "selectedMode": "multiple",
                "select": {"itemStyle": {"borderColor": ink, "borderWidth": 3}},
            }
        )
        for component in ("grid", "xAxis", "yAxis"):
            options.pop(component, None)
    elif spec.template == "facet":
        facets = list(dict.fromkeys(r["facet"] for r in rows))
        labels = list(dict.fromkeys(r["label"] for r in rows))
        options["grid"], options["xAxis"], options["yAxis"], options["title"] = [], [], [], []
        domain = axis_domains(spec, result).get("x", (0, 1))
        columns = min(2, len(facets))
        panel_rows = math.ceil(len(facets) / columns)
        row_height = (actual_height - 20) / panel_rows
        for i, facet in enumerate(facets):
            left = 100 * (i % columns) / columns
            top = (i // columns) * row_height
            options["grid"].append(
                {
                    "left": f"{left + 2}%",
                    "width": f"{100 / columns - 4}%",
                    "top": top + 36,
                    "height": max(50, row_height - 64),
                    "containLabel": True,
                }
            )
            options["title"].append(
                {
                    "text": str(facet),
                    "left": f"{left + 3}%",
                    "textStyle": {"fontSize": 12, "color": ink},
                    "top": top + 4,
                }
            )
            options["xAxis"].append(
                {
                    "type": "value",
                    "gridIndex": i,
                    "min": domain[0],
                    "max": domain[1],
                    "axisLabel": {"color": ink},
                    "splitLine": {"lineStyle": {"color": grid}},
                }
            )
            options["yAxis"].append(
                {
                    "type": "category",
                    "gridIndex": i,
                    "data": labels,
                    "inverse": True,
                    "axisLabel": {"color": ink, "width": 80, "overflow": "truncate"},
                }
            )
            subset = [{**r, "position": labels.index(r["label"])} for r in rows if r["facet"] == facet]
            install(
                subset,
                "bar",
                {"x": "value", "y": "position", "tooltip": ["facet", "label", "value", "n"]},
                str(facet),
                base_color,
            )
            series[-1].update(xAxisIndex=i, yAxisIndex=i, barMaxWidth=22)
    options["dataset"], options["series"] = datasets, series
    if spec.template not in {"facet", "treemap"}:
        for axis, (lo, hi) in axis_domains(spec, result).items():
            options[axis + "Axis"].update(min=lo, max=hi, scale=True)
    if spec.scale == "log":
        y_axis["type"] = "log"
    if spec.template in {"scatter", "density"}:
        native_width = actual_width if isinstance(actual_width, int) else cast(int, default_width)
        options["grid"], options["media"] = square_geometry(native_width, actual_height, spec.template)
        y_axis.update(nameLocation="middle", nameRotate=90, nameGap=56)
    return CompiledChart(options, mapping, digest([[list(k), v] for k, v in mapping.items()]))


def selected_rows(event: dict, compiled: CompiledChart, allowed: set[int]) -> list[int]:
    selection = event.get("selection", {})
    found: set[int] = set()
    for group in selection.get("selected", []):
        if group.get("data_type", "main") != "main":
            continue
        series = group.get("series_index", -1)
        for i in group.get("data_indices", []):
            found.update(compiled.row_map.get((series, i), []))
    return sorted(found & allowed)
