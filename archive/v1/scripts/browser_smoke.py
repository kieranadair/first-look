"""Real ECharts selection, responsive DOM and downloads. No screenshots, video or traces."""

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
    errors, console_warnings, checks = [], [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, color_scheme="light", accept_downloads=True
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda msg: console_warnings.append(msg.text) if msg.type in {"error", "warning"} else None,
        )
        page.goto(args.url)
        page.get_by_role("button", name="Explore example").first.click(timeout=45000)
        page.get_by_role("button", name="Investigate this dataset").click(timeout=30000)
        page.get_by_role("heading", name="Get the lay of the land.", exact=True).wait_for(timeout=30000)
        page.get_by_role("button", name="Inspect this perspective", exact=True).wait_for(timeout=45000)
        page.get_by_role("link", name="Findings", exact=True).click()
        page.get_by_role("button", name="Inspect", exact=True).first.wait_for(timeout=45000)
        expect(page.locator('[data-testid="stEChartsChart"]')).to_have_count(6, timeout=20000)
        expect(page.locator(".stApp")).to_have_css("background-color", "rgb(246, 248, 252)")
        # Every card must fit the viewport; the native grid changes its column count.
        layouts = []
        for width in [1440, 1024, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            page.get_by_role("heading", name="Follow the evidence.").scroll_into_view_if_needed()
            cards = page.locator('[class*="st-key-card_"]')
            boxes = [c.bounding_box() for c in cards.all()]
            assert len(boxes) >= 6
            for box in boxes:
                assert box is not None and box["x"] >= -1 and box["x"] + box["width"] <= width + 1, (
                    width,
                    box,
                )
            layouts.append({"width": width, "card_widths": [round(b["width"]) for b in boxes[:3]]})
        checks["responsive_cards"] = layouts
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Inspect", exact=True).first.click()
        chart = page.locator('[class*="st-key-chart_inspection_"]')
        chart.scroll_into_view_if_needed()
        # Click a rendered data mark, then exercise the actual ECharts selection protocol.
        chart.locator('svg path[fill="#4169D8"]').first.click(force=True)
        page.get_by_role("button", name="Apply selected rows", exact=True).click(timeout=15000)
        page.get_by_role("button", name="Return to reference", exact=True).click(timeout=15000)
        checks["echarts_selection_apply_reset"] = True
        # Returning restores the original investigation; no rebuild is needed.
        page.get_by_role("button", name="Pin", exact=True).first.click(timeout=45000)
        page.get_by_role("button", name="Pinned", exact=True).first.wait_for(timeout=15000)
        page.get_by_role("link", name="Evidence", exact=True).click()
        page.get_by_role("heading", name="Keep the evidence together.").wait_for(timeout=15000)
        page.get_by_role("button", name="Prepare downloads", exact=True).click(timeout=15000)
        with page.expect_download() as pending:
            page.get_by_role("button", name="Download investigation", exact=True).click()
        download = pending.value
        saved = Path(download.path())
        assert saved.read_bytes().startswith(b"PK") and saved.stat().st_size > 1000
        checks["download_zip_bytes"] = saved.stat().st_size
        checks["download_filename"] = download.suggested_filename
        # A new system-dark session must use the configured dark tokens.
        dark = browser.new_context(viewport={"width": 1024, "height": 900}, color_scheme="dark")
        darkpage = dark.new_page()
        darkpage.goto(args.url)
        darkpage.get_by_role("button", name="Explore example").first.wait_for(timeout=30000)
        expect(darkpage.locator(".stApp")).to_have_css("background-color", "rgb(15, 21, 34)")
        checks["light_and_dark_tokens"] = True
        assert not errors, errors
        # Browser extension/network noise is kept in the report; ECharts/app warnings fail.
        substantive = [
            m
            for m in console_warnings
            if any(k in m.lower() for k in ["echarts", "uncaught", "unrecognized", "deprecated", "error"])
        ]
        assert not substantive, substantive
        checks["page_errors"] = errors
        checks["console_warnings"] = console_warnings
        checks["screenshots_video_traces"] = False
        browser.close()
    Path("reports/browser.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
