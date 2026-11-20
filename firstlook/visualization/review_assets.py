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

from firstlook.contracts import ChartSpec, ResultArtifact, digest
from firstlook.visualization.compiler import PALETTE, axis_domains, validate_chart

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

    data = result.frame()
    if len(data) > max_points:
        data = data.sample(max_points, random_state=20261120).sort_index()
    table = data.drop(columns=["row_ids"], errors="ignore")
    with _LOCK:
        fig = Figure(figsize=(8, 4.6), dpi=140, layout="constrained")
        canvas = FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_facecolor("#F6F8FC")
        if spec.template == "scatter":
            if "group" in data:
                for i, (label, group) in enumerate(data.groupby("group", sort=False)):
                    ax.scatter(group.x, group.y, s=11, alpha=0.65, label=str(label), color=PALETTE[i % 8])
                ax.legend()
            else:
                ax.scatter(data.x, data.y, s=11, alpha=0.65, color=PALETTE[0])
        elif spec.template in {"line", "ecdf"}:
            x = pd.to_datetime(data.x) if result.metadata.get("time_axis") else data.x
            if spec.template == "ecdf":
                ax.step(x, data.value, where="post", color=PALETTE[0])
            else:
                ax.plot(x, data.value, color=PALETTE[0], marker="o", markersize=3)
        elif spec.template == "histogram":
            widths = data.right - data.left if "right" in data else None
            ax.bar(data.x, data.value, width=widths if widths is not None else 0.04, color=PALETTE[0])
        elif spec.template in {"bar", "dot"}:
            if spec.template == "bar":
                ax.barh(data.label.astype(str), data.value, color=PALETTE[0])
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
            table = data.pivot(index="y", columns="x", values="value")
            ax.imshow(table.values, cmap="Blues", aspect="auto", vmin=0, vmax=data.value.max())
            ax.set_xticks(range(len(table.columns)), table.columns.astype(str))
            ax.set_yticks(range(len(table.index)), table.index.astype(str))
        else:
            raise ValueError("This view has no supported review renderer.")
        for axis, domain in axis_domains(spec, result).items():
            (ax.set_xlim if axis == "x" else ax.set_ylim)(domain)
        if spec.scale == "log":
            ax.set_yscale("log")
        ax.set_title(result.plan.question, fontsize=11)
        ax.set_xlabel(spec.x_label)
        ax.set_ylabel(spec.y_label)
        ax.grid(alpha=0.15)
        out = io.BytesIO()
        canvas.print_png(out)
        png = out.getvalue()
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
            "sampled": len(data) < len(result.records),
        },
        png,
        table.to_dict("records"),
    )
