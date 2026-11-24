"""Render isolated, synthetic native charts and measure their actual SVG geometry.

Runs its own localhost-only Streamlit fixture, never opens the analyst workspace,
never imports provider configuration, and never uploads data or preserves pins.
The generated fixture, server log and report remain in ignored ``reports/``.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import time

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r"""
import json
import streamlit as st
from firstlook.contracts import AnalysisPlan, ChartSpec, ResultArtifact
from firstlook.visualization.compiler import compile_chart, selected_rows
from firstlook.visualization.layout import chart_dimensions

st.set_page_config(page_title="Isolated native chart fixtures", layout="wide")
st.title("Native chart rendering fixtures")

hist = [
    {"x": 0.5, "left": 0.0, "right": 1.0, "label": "0–1", "value": 3, "row_ids": [1,2,3]},
    {"x": 1.5, "left": 1.0, "right": 2.0, "label": "1–2", "value": 1, "row_ids": [4]},
]
scatter = [{"x": 10, "y": 1000, "row_id": 1}, {"x": 20, "y": 1200, "row_id": 2}, {"x": 30, "y": 1100, "row_id": 3}]
fixtures = [
    ("scatter_wide", "scatter", scatter, {}),
    ("scatter_narrow", "scatter", scatter, {}),
    ("bar", "bar", [{"label": "A", "value": 3, "row_ids": [1]}, {"label": "B", "value": 1, "row_ids": [2]}], {}),
    ("dot", "dot", [{"label": "A", "value": 100}, {"label": "B", "value": 150}], {}),
    ("histogram", "histogram", hist, {}),
    ("frequency_polygon", "frequency_polygon", hist, {}),
    ("ecdf", "ecdf", [{"x": 1, "value": 0.5, "row_ids": [1]}, {"x": 2, "value": 1, "row_ids": [2]}], {}),
    ("box", "box", [{"label": "A", "min": 1, "q1": 2, "median": 3, "q3": 4, "max": 5, "n": 5, "value": 3}], {}),
    ("line", "line", [{"x": 1, "value": 2}, {"x": 2, "value": None}, {"x": 3, "value": 4}], {}),
    ("heatmap", "heatmap", [{"x": "A", "y": "One", "value": -2}, {"x": "A", "y": "Two", "value": 1}, {"x": "B", "y": "One", "value": 0}, {"x": "B", "y": "Two", "value": 2}], {"normalization": "residual"}),
    ("density", "density", [{"x": x, "y": y, "value": 1+x+y, "row_ids": [x*2+y]} for x in range(2) for y in range(2)], {"numeric_grid": {"x_edges": [0,1,2], "y_edges": [10,20,30]}}),
    ("facet", "facet", [{"facet": g, "label": l, "value": v} for g in ["A","B","C","D"] for l,v in [("One",2),("Two",4)]], {}),
    ("quantile_difference", "quantile_difference", [{"x": 0.25, "value": -1, "first": 2, "second": 3}, {"x": 0.75, "value": 2, "first": 5, "second": 3}], {}),
    ("treemap", "treemap", [{"label": "A", "key": "a", "amount": 8, "share": 0.8, "value": 0.8, "row_ids": [10]}, {"label": "B", "key": "b", "amount": 2, "share": 0.2, "value": 1, "row_ids": [11]}, {"label": "Zero", "key": "z", "amount": 0, "share": 0, "value": 1, "row_ids": [12]}], {"partwhole_verified": True, "full_original_parts": True, "definition": {"aggregation": "sum", "transform": "identity"}}),
]
for name, template, records, metadata in fixtures:
    plan = AnalysisPlan(id=name, operation="exploration" if template=="treemap" else "fixture", fields=["f000"], context="synthetic-fixture", question=name, params={"recipe": "concentration"} if template=="treemap" else {})
    result = ResultArtifact(id=name, plan=plan, records=records, support=10, metadata=metadata, metrics={"total": 10} if template=="treemap" else {})
    spec = ChartSpec(id="chart-"+name, result_id=name, context=plan.context, template=template, x_label="Recorded X", y_label="Recorded Y", zero_baseline=template in {"bar","histogram","facet"}, value_field="amount" if template=="treemap" else "value", alt="Synthetic "+name)
    with st.container(key="fixture_"+name):
        st.subheader(name)
        width,height = chart_dimensions(spec,result,360 if template=="facet" else 340)
        compiled = compile_chart(spec,result,width=width,height=height)
        holder = st.container(width=250) if name=="scatter_narrow" else st.container()
        with holder:
            event = st.echarts_chart(compiled.options,key="native_"+name,renderer="svg",width=width,height=height,on_select="rerun" if template=="treemap" else "ignore",alt=spec.alt)
        if template=="treemap":
            st.text("Selected source rows: "+json.dumps(selected_rows(event,compiled,{10,11,12})))
            st.json(dict(event))
st.caption("Fixture rendering complete")
"""


def plot_clip(chart):
    """Read the actual inner SVG plot, including renderers that omit a clip."""
    return chart.locator("svg").first.evaluate(
        """svg => {
          const canvas={width:Number(svg.getAttribute('width')),height:Number(svg.getAttribute('height'))};
          const clips=[...svg.querySelectorAll('clipPath > rect, clipPath > path')].map(r => {
            const b=r.getBBox(); return {x:b.x,y:b.y,width:b.width,height:b.height};
          }).filter(r=>r.width>50 && r.height>50);
          if(clips.length) return {canvas,clips,measurement:'clip'};
          const lines=[...svg.querySelectorAll('path[stroke]')].filter(p=>p.getAttribute('stroke').toLowerCase()==='#e5eaf3').map(p=>p.getBBox());
          const horizontal=lines.filter(b=>b.width>50 && b.height<1);
          const vertical=lines.filter(b=>b.height>50 && b.width<1);
          if(horizontal.length && vertical.length) return {canvas,measurement:'grid_lines',clips:[{
            x:Math.min(...horizontal.map(b=>b.x)),y:Math.min(...vertical.map(b=>b.y)),
            width:Math.max(...horizontal.map(b=>b.width)),height:Math.max(...vertical.map(b=>b.height))
          }]};
          const cells=[...svg.querySelectorAll('path,rect')].filter(p=>{
            const f=p.getAttribute('fill'); return f && f!=='none' && !p.closest('defs') && Number(p.getAttribute('fill-opacity')||1)>0.4;
          }).map(p=>{const b=p.getBoundingClientRect(),r=svg.getBoundingClientRect(); return {x:b.x-r.x,y:b.y-r.y,width:b.width,height:b.height};}).filter(b=>b.width>40 && b.height>40);
          if(cells.length) return {canvas,measurement:'cell_union',clips:[{
            x:Math.min(...cells.map(b=>b.x)),y:Math.min(...cells.map(b=>b.y)),
            width:Math.max(...cells.map(b=>b.x+b.width))-Math.min(...cells.map(b=>b.x)),
            height:Math.max(...cells.map(b=>b.y+b.height))-Math.min(...cells.map(b=>b.y))
          }]};
          return {canvas,clips:[],measurement:'unavailable'};
        }"""
    )


def filled_paths(chart, color=None):
    return chart.locator("svg").first.evaluate(
        """(svg, color) => [...svg.querySelectorAll('path,rect')].filter(p => {
          const fill = p.getAttribute('fill');
          return fill && fill !== 'none' && (!color || fill.toLowerCase() === color.toLowerCase()) &&
            Number(p.getAttribute('fill-opacity') || 1) > 0.4 && !p.closest('defs');
        }).map(p => {
          const b=p.getBoundingClientRect(), root=svg.getBoundingClientRect();
          return {x:b.x-root.x,y:b.y-root.y,width:b.width,height:b.height,fill:p.getAttribute('fill')};
        }).filter(b => b.width>2 && b.height>2)""",
        color,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    fixture = report_dir / "chart-review-app.py"
    fixture.write_text(FIXTURE)
    static = report_dir / "static"
    static.mkdir(exist_ok=True)
    for font in ("IBMPlexSans.ttf", "IBMPlexMono.ttf"):
        shutil.copy2(ROOT / "static" / font, static / font)
    cache = Path("/workspace/.cache/ms-playwright")
    env = os.environ.copy()
    if cache.exists():
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(cache))
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["FIRSTLOOK_PROVIDER_MODE"] = "offline"
    with closing(socket.socket()) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", args.port))  # Fail rather than using another app's server.
    url = f"http://127.0.0.1:{args.port}"
    report = {
        "fixture_only": True,
        "provider_calls": False,
        "screenshots_video_traces": False,
        "viewports": [],
    }
    errors, warnings = [], []
    process = None
    try:
        with (report_dir / "chart-render-server.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(fixture),
                    "--server.address=127.0.0.1",
                    f"--server.port={args.port}",
                    "--server.headless=true",
                    "--server.enableAgentApi=false",
                    "--server.fileWatcherType=none",
                    "--server.enableStaticServing=true",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Fixture server exited; see reports/chart-render-server.log")
                try:
                    if httpx.get(url + "/_stcore/health", timeout=1).text == "ok":
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise TimeoutError("Fixture server did not become ready")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
                context = browser.new_context(viewport={"width": 1200, "height": 900}, color_scheme="light")
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_() if route.request.url.startswith(url + "/") else route.abort()
                    ),
                )
                page = context.new_page()
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.on(
                    "console",
                    lambda message: (
                        warnings.append(message.text) if message.type in {"warning", "error"} else None
                    ),
                )
                page.goto(url)
                expect(page.get_by_text("Fixture rendering complete", exact=True)).to_be_visible(
                    timeout=45000
                )
                expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                for viewport_width in (1200, 500):
                    page.set_viewport_size({"width": viewport_width, "height": 900})
                    measured = {"viewport_width": viewport_width, "square_plots": {}}
                    for name in ("scatter_wide", "scatter_narrow", "density"):
                        chart = page.locator(f'.st-key-fixture_{name} [data-testid="stEChartsChart"]')
                        chart.scroll_into_view_if_needed()
                        chart.locator("svg").first.wait_for(timeout=15000, state="attached")
                        (report_dir / f"chart-render-{name}.svg").write_text(
                            chart.locator("svg").first.evaluate("svg => svg.outerHTML")
                        )
                        # The native renderer may omit clipping when all points
                        # are inside the grid. Grid-line spans/cell extents then
                        # expose the same inner rectangle directly.
                        page.wait_for_function(
                            "selector => {const svg=document.querySelector(selector).querySelector('svg'); return svg && svg.querySelectorAll('path').length>3 && Math.abs(Number(svg.getAttribute('width'))-svg.getBoundingClientRect().width)<1.5}",
                            arg=f'.st-key-fixture_{name} [data-testid="stEChartsChart"]',
                            timeout=10000,
                        )
                        geometry = plot_clip(chart)
                        assert geometry["clips"], (name, geometry)
                        for clip in geometry["clips"]:
                            assert abs(clip["width"] - clip["height"]) < 1.5, (name, geometry)
                            assert clip["x"] + clip["width"] <= geometry["canvas"]["width"] + 1.5, (
                                name,
                                geometry,
                            )
                            assert clip["y"] + clip["height"] <= geometry["canvas"]["height"] + 1.5, (
                                name,
                                geometry,
                            )
                        measured["square_plots"][name] = geometry
                    hist = page.locator('.st-key-fixture_histogram [data-testid="stEChartsChart"]')
                    hist.scroll_into_view_if_needed()
                    hist.locator("svg").first.wait_for(state="visible")
                    bars = sorted(filled_paths(hist, "#4169d8"), key=lambda b: b["x"])
                    assert len(bars) == 2, bars
                    gap = bars[1]["x"] - bars[0]["x"] - bars[0]["width"]
                    assert abs(gap) < 1.5, ("Histogram bins do not touch", bars)
                    measured["histogram"] = {"bars": bars, "adjacent_gap_px": gap}
                    # Scroll every finite template into view so lazy rendering runs.
                    charts = page.locator('[data-testid="stEChartsChart"]')
                    expect(charts).to_have_count(14)
                    for chart in charts.all():
                        chart.scroll_into_view_if_needed()
                        expect(chart.locator("svg")).to_have_count(1)
                    measured["native_charts"] = charts.count()
                    report["viewports"].append(measured)
                tree = page.locator('.st-key-fixture_treemap [data-testid="stEChartsChart"]')
                tree.scroll_into_view_if_needed()
                # Labels are attached to the same ECharts node as its rectangle;
                # choosing B avoids dependence on decorative fill colours.
                tree.get_by_text("B", exact=True).click()
                expect(page.get_by_text("Selected source rows: [11]", exact=True)).to_be_visible(
                    timeout=15000
                )
                report["treemap_native_selection"] = {
                    "clicked_part": "B",
                    "source_rows": [11],
                    "implicit_root_has_no_members": True,
                }
                substantive = [
                    warning
                    for warning in warnings
                    if any(
                        term in warning.lower()
                        for term in ("echarts", "uncaught", "deprecated", "unrecognized")
                    )
                ]
                assert not errors and not substantive, (errors, substantive)
                browser.close()
        report["passed"] = True
    except Exception as exc:
        report.update(passed=False, failure=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        report.update(page_errors=errors, console_warnings=warnings)
        (report_dir / "chart-render.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
