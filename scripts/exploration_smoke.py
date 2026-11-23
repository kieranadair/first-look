"""Exercise new exploration and cohort transitions on the real agent API; no paid calls."""

import argparse
import json
import time
from pathlib import Path
import httpx

from scripts.runtime_smoke import walk


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.url, timeout=45)
    client.get("/_stcore/agent/openapi.json").raise_for_status()
    state = {}

    def interact(**kwargs):
        nonlocal state
        state = (
            client.post(
                "/_stcore/agent/interact",
                json={**({"session_id": state["session_id"]} if state else {}), **kwargs},
            )
            .raise_for_status()
            .json()
        )
        assert state["status"] == "ready", json.dumps(state)[-6000:]
        return state

    def click(key):
        assert any(a["key"] == key for a in state["actions"]), state["actions"]
        return interact(trigger={"key": key})

    def text():
        return json.dumps(state["tree"])

    def wait_for(predicate):
        end = time.monotonic() + 40
        while time.monotonic() < end:
            interact()
            if predicate():
                return
            time.sleep(0.15)
        raise AssertionError(text()[-6000:])

    interact()
    click("example_semantic")
    interact(page="discover")
    click(next(a["key"] for a in state["actions"] if a.get("label") == "Run local investigation"))
    wait_for(lambda: any(n["type"] == "echarts_chart" for n in walk(state["tree"])))
    interact(page="explore")
    assert any(a["key"] == "coverage_detail" for a in state["actions"])
    assert any(n["type"] == "dataframe" for n in walk(state["tree"]))
    interact(widget_state={"exploration_lens": "Relationships"})
    if any(a["key"] == "perspective_setup_Relationships" for a in state["actions"]):
        interact(widget_state={"perspective_setup_Relationships": True})
    click("open_perspective")
    wait_for(lambda: sum(n["type"] == "echarts_chart" for n in walk(state["tree"])) >= 2)
    assert "middle half" in text() and "displayed marks" in text()
    interact(page="compare")
    interact(widget_state={"cohort_field": "category"})
    interact(widget_state={"cohort_levels_f004": ["Furniture"]})
    click("preview_cohort")
    assert "Reference:" in text() and "Selected group:" in text()
    builder = next(n for n in walk(state["tree"]) if n.get("key") == "cohort_builder")
    assert builder["value"] is False
    interact(widget_state={"compare_measure": "sales"})
    click("compute_comparison")
    wait_for(lambda: sum(n["type"] == "echarts_chart" for n in walk(state["tree"])) == 3)
    assert "Reference" in text() and "quantile" in text()
    click("save_comparison")
    interact(page="evidence")
    interact(widget_state={"evidence_view": "Comparisons"})
    assert any(a["key"] == "evidence_comparison" for a in state["actions"])
    assert sum(n["type"] == "echarts_chart" for n in walk(state["tree"])) == 3
    click("prepare_export")
    assert len([n for n in walk(state["tree"]) if n["type"] == "download_button"]) == 2
    interact(page="compare")
    click("filter_cohort")
    assert any(a.get("label") == "Return to reference" for a in state["actions"])
    click("global_reset")
    assert any(n["type"] == "echarts_chart" for n in walk(state["tree"]))
    interact(page="models")
    assert all(
        any(n.get("key") == key for n in walk(state["tree"]))
        for key in ("model_target", "model_split", "model_hosted")
    )
    report = {
        "perspective_coverage": True,
        "conditional_companions": True,
        "preview_preserves_reference": True,
        "builder_collapses_after_preview": True,
        "comparison_board": True,
        "preserved_comparison_export": True,
        "filter_and_return_restore_investigation": True,
        "dedicated_models_page": True,
        "live_provider_calls": False,
        "screenshots_video_traces": False,
    }
    Path("reports/exploration-runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
