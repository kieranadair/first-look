"""Exercise semantic definitions, metric computation and context invalidation via real UI API."""

import argparse
import json
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
        assert state["status"] == "ready", json.dumps(state)[-5000:]
        return state

    def action(label):
        return next(a["key"] for a in state["actions"] if a.get("label") == label)

    def click(label):
        return interact(trigger={"key": action(label)})

    def text():
        return json.dumps(state["tree"])

    interact()
    interact(trigger={"key": "example_semantic"})
    interact(page="meaning")
    assert all(
        label in text() for label in ["Quantity meaning", "Run a metric", "Time is an observation process."]
    )
    assert any(a["key"] == "download_contract" for a in state["actions"])
    interact(widget_state={"metric_existing": "Sales per distinct order", "metric_groups": ["category"]})
    click("Compute and add to Discover")
    assert state["page"]["url_path"] == "discover"
    assert "average_per_entity" in text() and "Sales per distinct order" in text()
    assert any(n["type"] == "echarts_chart" for n in walk(state["tree"]))
    click("Pin")
    interact(page="challenge")
    assert "Compare row and entity averaging" in text()
    interact(page="evidence")
    click("Prepare downloads")
    assert len([n for n in walk(state["tree"]) if n["type"] == "download_button"]) == 2
    interact(page="meaning")
    # A quantity declaration changes the context and invalidates the old investigation.
    interact(widget_state={"meaning_field": "sales"})
    key = action("What kind of quantity?")
    interact(widget_state={key: "state"}, trigger={"key": action("Confirm quantity meaning")})
    interact(page="discover")
    assert "Run the local investigation" in text() and not any(
        n["type"] == "echarts_chart" for n in walk(state["tree"])
    )
    report = {
        "native_semantic_workspace": True,
        "named_metric_computation": True,
        "semantic_challenges": True,
        "evidence_download_controls": True,
        "semantic_edit_invalidates_results": True,
        "screenshots_video_traces": False,
        "live_provider_calls": False,
    }
    Path("reports/semantic-runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
