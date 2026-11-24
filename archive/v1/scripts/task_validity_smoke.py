"""Exercise real local task preparation/evaluation, recording coverage and export. No paid calls."""

import argparse
import json
import time
from pathlib import Path

import httpx

from firstlook import __version__
from scripts.runtime_smoke import walk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8768")
    args = parser.parse_args()
    state = {}
    client = httpx.Client(base_url=args.url, timeout=45)
    client.get("/_stcore/agent/openapi.json").raise_for_status()

    def interact(**kwargs):
        nonlocal state
        response = client.post(
            "/_stcore/agent/interact",
            json={**({"session_id": state["session_id"]} if state else {}), **kwargs},
        )
        if response.status_code >= 400:
            raise AssertionError(response.text)
        state = response.json()
        assert state["status"] == "ready", json.dumps(state)[-5000:]
        return state

    def text():
        return json.dumps(state["tree"])

    def click(key):
        assert any(a["key"] == key for a in state["actions"]), (key, state["actions"])
        interact(trigger={"key": key})

    def button(label):
        click(next(a["key"] for a in state["actions"] if a.get("label") == label))

    def wait_for(predicate):
        end = time.monotonic() + 45
        while time.monotonic() < end:
            interact()
            if predicate():
                return
            time.sleep(0.15)
        raise AssertionError(text()[-5000:])

    interact()
    assert f"First Look {__version__}" in text() and "Task policy: 2026-11-24.2" in text()
    click("example_events")
    interact(page="event_lab")
    interact(
        widget_state={
            "event_identity": "event_id",
            "event_known": "available_timestamp",
            "event_coverage": True,
        }
    )
    click("prepare_events")
    wait_for(lambda: any(a["key"] == "prepared_event" for a in state["actions"]))
    view = next(a["key"] for a in state["actions"] if a.get("label") == "Event task view")
    interact(widget_state={view: "Evaluate models"})
    assert "Before fitting: task readiness" in text()
    assert "ready for declared protocol" in text().lower()
    click("evaluate_events")
    wait_for(lambda: "Observed predictive comparison" in text())
    assert "Previous window" in text() and any(n["type"] == "echarts_chart" for n in walk(state["tree"]))
    interact(page="evidence")
    click("prepare_export")
    assert len([n for n in walk(state["tree"]) if n["type"] == "download_button"]) == 2
    interact(page="")
    button("Investigate this dataset")
    wait_for(lambda: any(n["type"] == "echarts_chart" for n in walk(state["tree"])))
    interact(page="challenge")
    interact(widget_state={"challenge_perspective": "Recording process"})
    assert any(n["type"] == "echarts_chart" for n in walk(state["tree"]))
    assert "recording" in text().lower() and "denominators" in text().lower()
    interact(page="meaning")
    assert any(a.get("label") == "Save analytical task" for a in state["actions"])
    assert any(a.get("label") == "Save availability rule" for a in state["actions"])
    interact(page="models")
    assert "Before fitting" in text()
    report = {
        "version": __version__,
        "event_preparation": True,
        "visible_readiness": True,
        "local_event_models": True,
        "heldout_diagnostic_chart": True,
        "recording_process": True,
        "task_availability_editor": True,
        "evidence_downloads": True,
        "live_provider_calls": False,
        "screenshots_video_traces": False,
    }
    output = Path("reports/task-validity-runtime.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
