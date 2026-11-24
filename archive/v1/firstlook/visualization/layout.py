"""Native ECharts geometry: a square coordinate area, independent of axis units.

ECharts media options react to the actual chart container in the browser. This
keeps both inner dimensions equal even when Streamlit caps a chart's width to a
narrow column. Axis labels have their own reserved margins and cannot silently
shrink one dimension through ``containLabel`` or automatic outer bounds.
"""

from __future__ import annotations

from typing import Literal

from firstlook.contracts import ChartSpec, ResultArtifact

ChartWidth = int | Literal["stretch"]
LEFT, RIGHT, TOP = 76, 24, 42


def plot_bottom(template: str) -> int:
    return 100 if template == "density" else 66


def chart_dimensions(
    spec: ChartSpec, result: ResultArtifact, requested_height: int = 310
) -> tuple[ChartWidth, int]:
    """Return bounded outer dimensions; square applies to the inner plot only."""
    if spec.template not in {"scatter", "density"}:
        return "stretch", requested_height
    height = max(350 if spec.template == "density" else 320, requested_height)
    side = height - TOP - plot_bottom(spec.template)
    return side + LEFT + RIGHT, height


def square_geometry(width: int, height: int, template: str = "scatter") -> tuple[dict, list[dict]]:
    """Exact square grids, with bounded 8px native-responsive size increments.

    Each breakpoint fits its lower width bound, so between breakpoints the plot
    has a few pixels of spare horizontal room rather than overflowing. ECharts
    merges every matching query; ascending lower bounds make the last match
    the largest square that fits. No data coordinates change on resize.
    """
    side = max(1, min(width - LEFT - RIGHT, height - TOP - plot_bottom(template)))

    def grid(size: int) -> dict:
        return {
            "left": LEFT,
            "top": TOP,
            "width": size,
            "height": size,
            "containLabel": False,
            "outerBoundsMode": "none",
        }

    # The fallback also covers exceptionally narrow embedded chart containers.
    # Below the reserved axis margins labels may clip, but geometry stays square.
    media = [{"option": {"grid": grid(1)}}]
    for lower in range(LEFT + RIGHT + 8, width + 8, 8):
        media.append(
            {
                "query": {"minWidth": lower},
                "option": {"grid": grid(min(side, lower - LEFT - RIGHT))},
            }
        )
    return grid(side), media
