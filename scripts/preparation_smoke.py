"""Exercise native preparation, confirmation, undo, context, prepared views and export. No paid calls."""

import argparse
import json
import time
from pathlib import Path

import httpx

from firstlook import __version__
from scripts.runtime_smoke import walk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8770")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.url, timeout=45)
    schema = client.get("/_stcore/agent/openapi.json").raise_for_status().json()
    assert "/_stcore/agent/interact" in schema["paths"]
    state = {}

    def interact(**kwargs):
        nonlocal state
        body = {"session_id": state["session_id"]} if state else {}
        response = client.post("/_stcore/agent/interact", json={**body, **kwargs})
        assert response.status_code < 400, response.text
        state = response.json()
        assert state["status"] == "ready", json.dumps(state)[-5000:]
        return state

    def click(key):
        assert any(a["key"] == key for a in state["actions"]), (key, state["actions"])
        interact(trigger={"key": key})

    def text():
        return json.dumps(state["tree"])

    interact()
    assert f"First Look {__version__}" in text()
    click("example_reversal")
    assert "Your analytical preparation" in text()
    interact(page="preparation")
    assert "Review related definitions together" in text()
    click("check_prepared_bundle")
    assert "This bundle is valid" in text()
    click("apply_prepared_bundle")
    assert any(a["key"] == "undo_preparation" for a in state["actions"])
    click("undo_preparation")
    interact(widget_state={"preparation_mode": "Context & documents"})
    submit = next(a["key"] for a in state["actions"] if a.get("label") == "Prepare this understanding")
    interact(
        widget_state={
            "preparation_goal": "Compare x",
            "preparation_notes": "Each row is a recorded observation.",
            "preparation_context_connected": False,
        },
        trigger={"key": submit},
    )
    interact(widget_state={"preparation_mode": "Review"})
    click("open_prepared_view")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        interact()
        if any(n["type"] == "echarts_chart" for n in walk(state["tree"])):
            break
        time.sleep(0.15)
    else:
        raise AssertionError("The prepared metric view did not publish.")
    interact(page="evidence")
    assert "Preparation definitions" in text()
    click("prepare_export")
    assert len([n for n in walk(state["tree"]) if n["type"] == "download_button"]) == 2
    interact(page="preparation")
    interact(widget_state={"preparation_mode": "Reuse & record"})
    click("remember_semantic_template")
    assert "Remembered in this session" in text()
    assert len([n for n in walk(state["tree"]) if n["type"] == "download_button"]) == 2
    report = {
        "version": __version__,
        "local_draft": True,
        "atomic_confirmation": True,
        "undo": True,
        "plain_context": True,
        "prepared_metric_view": True,
        "evidence_downloads": True,
        "session_template": True,
        "provider_calls": 0,
        "screenshots": 0,
    }
    output = Path("reports/preparation-runtime.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
