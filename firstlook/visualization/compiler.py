"""Compile a finite chart catalog and keep every mark linked to its source rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
import math

import pandas as pd

from firstlook.contracts import ChartSpec, ResultArtifact, digest

PALETTE = ["#4169D8", "#209589", "#C67049", "#9774BD", "#A58A30", "#647B9C", "#CD7099", "#5598B0"]


def axis_domains(spec: ChartSpec, result: ResultArtifact) -> dict[str, tuple[float, float]]:
    """One explicit domain policy for the interactive and offscreen renderers."""
    rows = result.records
    domains = {}

    def span(axis: str, keys: list[str], zero: bool = False):
        values = [
            float(r[k])
            for r in rows
            for k in keys
            if isinstance(r.get(k), (int, float)) and math.isfinite(r[k])
        ]
        if not values:
            return
        lo, hi = min(values), max(values)
        if axis == "y" and spec.scale == "log":
            domains[axis] = (lo / 1.05, hi * 1.05)
            return
        pad = (hi - lo) * 0.05 if hi > lo else max(abs(hi) * 0.05, 1.0)
        lower, upper = (min(0.0, lo) if zero else lo - pad, max(0.0, hi + pad) if zero else hi + pad)
        # Round outwards to avoid long floating-point endpoint labels. Both
        # renderers consume these bounds, and every plotted value stays inside.
        width = upper - lower
        if math.isfinite(width) and width > 0:
            step = 10.0 ** (math.floor(math.log10(width)) - 1)
            if step > 0:
                lower = min(lower, float(f"{math.floor(lower / step) * step:.12g}"))
                upper = max(upper, float(f"{math.ceil(upper / step) * step:.12g}"))
        domains[axis] = lower, upper

    if spec.template == "scatter":
        span("x", ["x"])
        span("y", ["y"])
    elif spec.template == "histogram":
        span("x", ["left", "right"] if "left" in rows[0] else ["x"])
        span("y", ["value"], True)
    elif spec.template in {"bar", "dot"}:
        span("x", ["value"], spec.template == "bar")
        if result.metadata.get("proportion"):
            domains["x"] = (0.0, 1.0)
        if spec.template == "dot":
            domains["x"] = (min(-1.0, domains["x"][0]), max(1.0, domains["x"][1]))
    elif spec.template == "box":
        span("y", ["min", "max"])
    elif spec.template in {"line", "ecdf"}:
        if not result.metadata.get("time_axis"):
            span("x", ["x"])
        span("y", ["value"])
        if spec.template == "ecdf":
            domains["y"] = (0.0, 1.0)
    return domains


@dataclass
class CompiledChart:
    options: dict
    row_map: dict[tuple[int, int], list[int]]
    mapping_hash: str


def validate_chart(spec: ChartSpec, result: ResultArtifact) -> None:
    if spec.result_id != result.id or spec.context != result.plan.context:
        raise ValueError("The chart and result belong to different contexts.")
    if result.support < 1 or not result.records:
        raise ValueError("A chart requires supported data.")
    if spec.template in {"bar", "histogram"} and not spec.zero_baseline:
        raise ValueError("Magnitude bars require a zero baseline.")
    if spec.scale == "log":
        if spec.template not in {"scatter", "line"}:
            raise ValueError("Log scales are supported only on numerical scatter and line ordinates.")
        values = [r.get("value", r.get("y")) for r in result.records]
        if any(v is not None and (not isinstance(v, (int, float)) or v <= 0) for v in values):
            raise ValueError("A log scale requires positive numerical values.")


def compile_chart(spec: ChartSpec, result: ResultArtifact, dark: bool = False) -> CompiledChart:
    validate_chart(spec, result)
    ink = "#B5C4DB" if dark else "#58677F"
    grid = "#2B3A51" if dark else "#E5EAF3"
    rows = result.records
    options: dict[str, Any] = {
        "animationDuration": 250,
        "animationDurationUpdate": 250,
        "grid": {"left": 64, "right": 24, "top": 32, "bottom": 68, "containLabel": True},
        "tooltip": {"trigger": "item"},
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
            install(subset, "scatter", {"x": "x", "y": "y", "tooltip": ["x", "y"]}, group, PALETTE[i % 8])
            series[-1]["symbolSize"] = 6
        options["brush"] = {"xAxisIndex": "all", "brushMode": "multiple"}
        options["toolbox"] = {"left": 8, "feature": {"brush": {"type": ["rect", "clear"]}}}
        if len(groups) > 1:
            options["legend"] = {"top": 0}
    elif spec.template in {"bar", "dot"}:
        install(
            rows,
            "bar" if spec.template == "bar" else "scatter",
            {"x": "value", "y": "label", "tooltip": ["label", "value"]},
            color=PALETTE[0],
        )
        y_axis.update(
            {
                "type": "category",
                "name": "",
                "inverse": True,
                "axisLabel": {"color": ink, "width": 125, "overflow": "truncate"},
            }
        )
        if spec.template == "bar":
            x_axis["min"] = min(0, min(float(r["value"]) for r in rows))
            series[0]["barMaxWidth"] = 26
            options["grid"]["left"] = 130
        else:
            series[0]["symbolSize"] = 13
            x_axis["min"] = min(-1, min(float(r["value"]) for r in rows))
            x_axis["max"] = max(1, max(float(r["value"]) for r in rows))
    elif spec.template == "histogram":
        install(rows, "bar", {"x": "x", "y": "value", "tooltip": ["label", "value"]}, color=PALETTE[0])
        series[0]["barCategoryGap"] = "4%"
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
        series[0]["itemStyle"] = {"color": "#C3D1F7", "borderColor": PALETTE[0]}
    elif spec.template in {"line", "ecdf"}:
        install(rows, "line", {"x": "x", "y": "value", "tooltip": ["x", "value"]}, color=PALETTE[0])
        x_axis["type"] = "time" if result.metadata.get("time_axis") else "value"
        series[0]["connectNulls"] = False
        series[0]["symbolSize"] = 6
        series[0]["lineStyle"] = {"width": 2.5}
        if spec.template == "ecdf":
            series[0]["step"] = "end"
    elif spec.template == "heatmap":
        xs = list(dict.fromkeys(str(r["x"]) for r in rows))
        ys = list(dict.fromkeys(str(r["y"]) for r in rows))
        heat = [{**r, "x": xs.index(str(r["x"])), "y": ys.index(str(r["y"]))} for r in rows]
        install(heat, "heatmap", {"x": "x", "y": "y", "value": "value", "tooltip": ["value"]})
        x_axis.update({"type": "category", "data": xs})
        y_axis.update({"type": "category", "data": ys})
        options["visualMap"] = {
            "min": 0,
            "max": max(r["value"] for r in rows),
            "calculable": False,
            "orient": "horizontal",
            "bottom": 0,
            "inRange": {"color": ["#E8EFFC", "#4169D8", "#182F72"]},
        }
        options["grid"]["bottom"] = 95
    options["dataset"], options["series"] = datasets, series
    for axis, (lo, hi) in axis_domains(spec, result).items():
        options[axis + "Axis"].update(min=lo, max=hi, scale=True)
    if spec.scale == "log":
        y_axis["type"] = "log"
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
