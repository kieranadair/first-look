"""Offscreen analytical chart assets. Never captures the Streamlit application."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import threading
from pathlib import Path
from dataclasses import dataclass

import pandas as pd
import numpy as np

from firstlook.contracts import ChartSpec, ResultArtifact, digest
from firstlook.visualization.compiler import (
    PALETTE,
    axis_domains,
    validate_chart,
    plotting_records,
    category_label,
    encoded_records,
    series_colors,
    categorical_order,
    color_domain,
    heatmap_colors,
)

_LOCK = threading.Lock()


@dataclass
class ReviewAsset:
    manifest: dict
    png: bytes
    records: list[dict]


def render_asset(result: ResultArtifact, spec: ChartSpec, max_points: int = 600) -> ReviewAsset:
    validate_chart(spec, result)
    cache = Path(tempfile.gettempdir()) / "firstlook-render-cache"
    cache.mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache))
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.dates import date2num
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Rectangle

    data = pd.DataFrame(encoded_records(spec, result))
    reduction = {}
    curves = data.group.nunique() if spec.template == "ecdf" and "group" in data else 1
    budget = max_points - 2 * curves if spec.template == "ecdf" else max_points
    if len(data) > budget:
        if spec.template == "scatter":
            data = data.sample(max_points, random_state=20261120).sort_index()
            reduction = {"method": "seeded sample of displayed points", "seed": 20261120}
        elif spec.template == "ecdf":
            groups = list(data.groupby("group", sort=False)) if "group" in data else [("", data)]
            frames = []
            errors = {}
            per = budget // len(groups)
            if per < 3:
                raise ValueError("The review budget cannot preserve each cumulative curve.")
            for label, part in groups:
                p = part.value.to_numpy()
                positions = np.unique(
                    np.r_[
                        0,
                        np.minimum(np.searchsorted(p, np.linspace(0, 1, max(1, per - 2))), len(p) - 1),
                        len(p) - 1,
                    ]
                )
                reduced = part.iloc[positions]
                previous = np.searchsorted(reduced.x, part.x, side="right") - 1
                errors[str(label)] = float(
                    np.max(np.abs(p - reduced.value.to_numpy()[np.maximum(previous, 0)]))
                )
                frames.append(reduced)
            data = pd.concat(frames)
            reduction = {
                "method": "observed-location cumulative subset",
                "additional_max_vertical_error_by_group": errors,
                "source_error": result.metadata.get("ecdf_error", result.metrics),
            }
        else:
            raise ValueError(
                "A complete aggregate/temporal view does not fit the review budget; no cells or intervals were sampled."
            )
    if spec.template == "ecdf":
        data = pd.DataFrame(plotting_records(spec, result, data.to_dict("records")))
    table = data.drop(columns=["row_ids", "row_id"], errors="ignore")
    with _LOCK:
        fig = Figure(
            figsize=(6, 6) if spec.template in {"scatter", "density"} else (8, 4.6),
            dpi=140,
            layout="constrained",
        )
        canvas = FigureCanvasAgg(fig)
        facets = list(dict.fromkeys(data.facet)) if spec.template == "facet" else []
        if facets:
            columns = min(2, len(facets))
            array = fig.subplots(int(np.ceil(len(facets) / columns)), columns, squeeze=False).ravel()
            axes = list(array[: len(facets)])
            for unused in array[len(facets) :]:
                unused.set_visible(False)
        else:
            axes = [fig.subplots()]
        ax = axes[0]
        base_color = result.metadata.get("comparison_color", PALETTE[0])
        colors = series_colors(result)
        ax.set_facecolor("#F6F8FC")
        if spec.template == "scatter":
            if "group" in data:
                for i, (label, group) in enumerate(data.groupby("group", sort=False)):
                    ax.scatter(group.x, group.y, s=11, alpha=0.65, label=str(label), color=colors[str(label)])
                ax.legend()
            else:
                ax.scatter(data.x, data.y, s=11, alpha=0.65, color=PALETTE[0])
        elif spec.template in {"line", "ecdf"}:
            grouped = list(data.groupby("group", sort=False)) if "group" in data else [("", data)]
            for i, (label, part) in enumerate(grouped):
                x = pd.to_datetime(part.x) if result.metadata.get("time_axis") else part.x
                color = colors[str(label)] if str(label) else base_color
                if spec.template == "ecdf":
                    ax.step(x, part.value, where="post", color=color, label=str(label))
                else:
                    ax.plot(
                        x,
                        part.value,
                        color=color,
                        marker="o",
                        markersize=2,
                        label=str(label),
                        linestyle="--" if any(r.get("synthetic") for r in result.records) else "-",
                    )
                    if result.metadata.get("conditional_spread"):
                        ax.plot(x, part.q1, color=PALETTE[1], linestyle="--", label="25th percentile")
                        ax.plot(x, part.q3, color=PALETTE[1], linestyle="--", label="75th percentile")
            if len(grouped) > 1 or result.metadata.get("conditional_spread"):
                ax.legend(fontsize=7)
        elif spec.template in {"histogram", "frequency_polygon"}:
            if spec.template == "histogram":
                widths = data.right - data.left if "right" in data else None
                ax.bar(data.x, data.value, width=widths if widths is not None else 0.04, color=base_color)
            else:
                grouped = list(data.groupby("group", sort=False)) if "group" in data else [("", data)]
                for label, part in grouped:
                    ax.plot(
                        part.x,
                        part.value,
                        marker="o",
                        markersize=3,
                        color=colors[str(label)] if str(label) else base_color,
                        label=str(label),
                    )
                if len(grouped) > 1:
                    ax.legend(fontsize=7)
            if all(isinstance(result.metrics.get(key), (int, float)) for key in ("q1", "q3")):
                ax.axvspan(result.metrics["q1"], result.metrics["q3"], color=base_color, alpha=0.07)
            if isinstance(result.metrics.get("median"), (int, float)):
                ax.axvline(
                    result.metrics["median"], color="#58677F", linestyle="--", linewidth=1, label="Median"
                )
                ax.legend(fontsize=7)
        elif spec.template == "quantile_difference":
            ax.scatter(data.x, data.value, color=base_color, s=24)
        elif spec.template == "treemap":
            from firstlook.visualization.composition import treemap_rectangles

            rectangles = treemap_rectangles(data.value.tolist())
            for row, (x, y, width, height) in zip(data.to_dict("records"), rectangles):
                if width <= 0 or height <= 0:
                    continue
                ax.add_patch(
                    Rectangle((x, y), width, height, facecolor=base_color, edgecolor="white", linewidth=1)
                )
                if width >= 0.13 and height >= 0.09:
                    text = str(row["label"])
                    ax.text(
                        x + width / 2,
                        y + height / 2,
                        text[:24] + ("…" if len(text) > 24 else ""),
                        ha="center",
                        va="center",
                        fontsize=7,
                        color="white",
                        clip_on=True,
                    )
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_axis_off()
        elif spec.template in {"bar", "dot"}:
            if spec.template == "bar":
                ax.barh(range(len(data)), data.value, color=base_color)
                ax.set_yticks(range(len(data)), [category_label(r) for r in data.to_dict("records")])
            else:
                ax.scatter(data.value, data.label.astype(str), color=PALETTE[0])
            ax.invert_yaxis()
        elif spec.template == "box":
            ax.bxp(
                [
                    {
                        "label": str(r["label"]),
                        "whislo": r["min"],
                        "q1": r["q1"],
                        "med": r["median"],
                        "q3": r["q3"],
                        "whishi": r["max"],
                        "fliers": [],
                    }
                    for r in data.to_dict("records")
                ],
                showfliers=False,
            )
        elif spec.template == "heatmap":
            data["x"], data["y"] = data.x.astype(str), data.y.astype(str)
            matrix = data.pivot(index="y", columns="x", values="value").reindex(
                index=categorical_order(result, "y"), columns=categorical_order(result, "x")
            )
            lo, hi = color_domain(result)
            image = ax.imshow(
                matrix.values,
                cmap=LinearSegmentedColormap.from_list("evidence", heatmap_colors(result)),
                aspect="auto",
                origin="upper",
                vmin=lo,
                vmax=hi,
            )
            fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.06, pad=0.15)
            ax.set_xticks(range(len(matrix.columns)), matrix.columns.astype(str))
            ax.set_yticks(range(len(matrix.index)), matrix.index.astype(str))
        elif spec.template == "density":
            matrix = data.pivot(index="y", columns="x", values="value").sort_index().sort_index(axis=1)
            xe, ye = result.metadata["numeric_grid"]["x_edges"], result.metadata["numeric_grid"]["y_edges"]
            lo, hi = color_domain(result)
            image = ax.imshow(
                matrix.values,
                origin="lower",
                extent=(xe[0], xe[-1], ye[0], ye[-1]),
                aspect="auto",
                cmap=LinearSegmentedColormap.from_list("evidence", heatmap_colors(result)),
                vmin=lo,
                vmax=hi,
            )
            fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.06, pad=0.15)
        elif spec.template == "facet":
            for axis, facet in zip(axes, facets):
                part = data[data.facet == facet]
                axis.barh(range(len(part)), pd.to_numeric(part.value).to_numpy(), color=base_color)
                axis.set_yticks(range(len(part)), part.label.astype(str))
                axis.invert_yaxis()
                axis.set_title(str(facet), fontsize=9)
                axis.set_xlim(axis_domains(spec, result).get("x", (0, 1)))
        else:
            raise ValueError("This view has no supported review renderer.")
        if spec.template != "facet":
            for axis, domain in axis_domains(spec, result).items():
                if axis == "x" and result.metadata.get("time_axis"):
                    ax.set_xlim(
                        float(date2num(pd.to_datetime(domain[0], unit="ms"))),
                        float(date2num(pd.to_datetime(domain[1], unit="ms"))),
                    )
                else:
                    (ax.set_xlim if axis == "x" else ax.set_ylim)(domain)
        if spec.scale == "log":
            ax.set_yscale("log")
        if spec.template in {"scatter", "density"}:
            ax.set_box_aspect(1)
        if result.metadata.get("reference") == "identity":
            domain = axis_domains(spec, result)["x"]
            ax.plot(
                domain,
                domain,
                linestyle="--",
                linewidth=1,
                color="#58677F",
                label="Equal observed and predicted",
            )
        elif result.metadata.get("reference") == "zero" or spec.template == "quantile_difference":
            ax.axhline(0, linestyle="--", linewidth=1, color="#58677F")
        if spec.template != "facet":
            ax.set_title(result.plan.question, fontsize=11)
        ax.set_xlabel(spec.x_label)
        ax.set_ylabel(spec.y_label)
        ax.grid(alpha=0.15 if spec.template != "treemap" else 0)
        out = io.BytesIO()
        canvas.print_png(out)
        png = out.getvalue()
        bounds = ax.get_window_extent()
        plot_geometry = {"width": bounds.width, "height": bounds.height}
        fig.clear()
    if len(png) > 1_500_000:
        raise ValueError("Review asset exceeds the image budget.")
    return ReviewAsset(
        {
            "id": result.id,
            "result_id": result.id,
            "chart_id": spec.id,
            "contract_hash": digest(spec.model_dump()),
            "axis_domains": axis_domains(spec, result),
            "labels": {"x": spec.x_label, "y": spec.y_label},
            "context": result.plan.context,
            "sha256": hashlib.sha256(png).hexdigest(),
            "plotted_rows": len(data),
            "support": result.support,
            "kind": "offscreen_analysis",
            "sampled": bool(reduction),
            "reduction": reduction,
            "analysis_scope": result.metadata.get("analysis_scope", {}),
            "cdf_endpoint_extensions": spec.template == "ecdf",
            "plot_geometry": plot_geometry,
            "value_field": spec.value_field,
            "reference": result.metadata.get("reference"),
            "whisker_convention": result.metadata.get("whisker_convention")
            if spec.template == "box"
            else None,
        },
        png,
        table.to_dict("records"),
    )
