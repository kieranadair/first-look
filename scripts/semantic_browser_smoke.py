"""Use the actual semantic workspace and native ECharts with no image capture."""

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
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.get_by_role("button", name="Explore semantic example", exact=True).click(timeout=45000)
        page.get_by_role("button", name="Investigate this dataset", exact=True).wait_for(timeout=30000)
        page.get_by_role("link", name="Meaning", exact=True).click()
        page.get_by_role("heading", name="Meaning", exact=True).wait_for(timeout=30000)
        page.get_by_role("tab", name="Metrics", exact=True).click()
        page.get_by_role("combobox", name="Recorded metric", exact=True).click()
        page.get_by_role("combobox", name="Recorded metric", exact=True).fill("Sales per distinct order")
        page.get_by_role("option", name="Sales per distinct order", exact=True).click()
        page.get_by_role("combobox", name="Group by", exact=True).click()
        page.get_by_role("option", name="category", exact=True).click()
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Compute and inspect metric", exact=True).click()
        page.get_by_role("heading", name="Inspect finding", exact=True).wait_for(timeout=30000)
        expect(page.locator('[data-testid="stEChartsChart"]').first).to_be_visible()
        expect(page.get_by_text("Sales per distinct order by category", exact=True).first).to_be_visible()
        page.get_by_role("button", name="Pin finding", exact=True).click()
        page.get_by_role("button", name="Pinned", exact=True).first.wait_for()
        page.get_by_role("link", name="Evidence", exact=True).click()
        page.get_by_role("button", name="Prepare downloads", exact=True).click(timeout=15000)
        with page.expect_download() as pending:
            page.get_by_role("button", name="Download investigation", exact=True).click()
        blob = Path(pending.value.path()).read_bytes()
        from firstlook.evidence import read_bundle

        files = read_bundle(blob)
        contract = json.loads(files["semantics/contract.json"])
        assert any(m["id"] == "demo_order_average" and m["confirmed"] for m in contract["metrics"])
        findings = json.loads(files["analysis/findings.json"])
        assert findings[0]["family"] == "metric"
        assert not errors, errors
        browser.close()
    report = {
        "actual_metric_controls": True,
        "native_echarts_rendered": True,
        "semantic_contract_in_download": True,
        "download_bytes": len(blob),
        "page_errors": errors,
        "screenshots_video_traces": False,
    }
    Path("reports/semantic-browser.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
