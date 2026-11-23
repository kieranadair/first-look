"""Actual native comparison layout and interactions, using DOM measurements only."""

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    cache = Path("/workspace/.cache/ms-playwright")
    if cache.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    errors, warnings, checks = [], [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: warnings.append(m.text) if m.type in {"error", "warning"} else None)
        page.goto(args.url)
        page.get_by_role("button", name="Explore semantic example", exact=True).click(timeout=45000)
        page.get_by_role("button", name="Investigate this dataset", exact=True).click(timeout=30000)
        page.get_by_role("button", name="Inspect this perspective", exact=True).wait_for(timeout=45000)
        page.get_by_role("link", name="Compare", exact=True).click()
        page.get_by_role("combobox", name="Include levels", exact=True).click()
        page.get_by_role("option", name="Furniture", exact=True).click()
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Preview cohort", exact=True).click()
        page.get_by_role("button", name="Compare populations", exact=True).click(timeout=15000)
        expect(page.locator('[data-testid="stEChartsChart"]')).to_have_count(2, timeout=30000)
        page.get_by_role("heading", name="Compare", exact=True).scroll_into_view_if_needed()
        charts = page.locator('[data-testid="stEChartsChart"]')
        boxes = [chart.bounding_box() for chart in charts.all()]
        assert all(box is not None for box in boxes)
        assert abs(boxes[0]["y"] - boxes[1]["y"]) < 5, boxes
        assert max(b["y"] + b["height"] for b in boxes) < 900, boxes
        assert charts.evaluate_all("nodes => nodes.every(n => !n.closest('details'))")
        checks["related_curves_visible_together"] = {"viewport": [1440, 900], "chart_bounds": boxes}
        quantiles = page.get_by_text("Differences across the distribution", exact=True)
        qbox = quantiles.bounding_box()
        assert qbox and abs(qbox["y"] - boxes[0]["y"]) < 150, qbox
        checks["quantiles_beside_curves"] = True
        # A table request uses source values, independently of compressed curves.
        page.get_by_role("button", name="Query source values", exact=True).click()
        expect(page.locator('[data-testid="stDataFrame"]')).to_have_count(2)
        page.get_by_role("button", name="Save comparison to Evidence", exact=True).click()
        checks["save_board"] = True
        page.get_by_role("link", name="Evidence", exact=True).click()
        page.get_by_role("button", name="Comparisons", exact=True).click()
        expect(page.get_by_role("combobox", name="Comparison board", exact=True)).to_be_visible()
        expect(page.locator('[data-testid="stEChartsChart"]')).to_have_count(2)
        page.get_by_role("button", name="Prepare downloads", exact=True).click()
        with page.expect_download() as pending:
            page.get_by_role("button", name="Download investigation", exact=True).click()
        from firstlook.evidence import import_bundle

        restored = import_bundle(Path(pending.value.path()).read_bytes())
        assert restored.comparisons and restored.comparisons[0].spec.operation == "ecdf"
        checks["download_contains_comparison"] = True
        page.get_by_role("link", name="Compare", exact=True).click()
        layouts = []
        for width in [1440, 1024, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            page.get_by_role("heading", name="Compare", exact=True).scroll_into_view_if_needed()
            actual = [c.bounding_box() for c in page.locator('[data-testid="stEChartsChart"]').all()]
            assert len(actual) == 2
            assert all(b and b["x"] >= -1 and b["x"] + b["width"] <= width + 1 for b in actual), (
                width,
                actual,
            )
            layouts.append({"width": width, "chart_widths": [round(b["width"]) for b in actual]})
        checks["responsive_companions"] = layouts
        substantive = [
            w
            for w in warnings
            if any(s in w.lower() for s in ["echarts", "uncaught", "deprecated", "unrecognized"])
        ]
        assert not errors and not substantive, (errors, substantive)
        checks.update(page_errors=errors, console_warnings=warnings, screenshots_video_traces=False)
        browser.close()
    Path("reports/exploration-browser.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
