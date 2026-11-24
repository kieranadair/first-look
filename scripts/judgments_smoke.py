"""Real local runtime: prepare/confirm a question, inspect new pages and export. No paid calls."""

import argparse
import json
import time
from pathlib import Path

import httpx

from scripts.runtime_smoke import walk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8767")
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
        assert state["status"] == "ready", json.dumps(state)[-4000:]
        return state

    def click(key):
        assert any(a["key"] == key for a in state["actions"]), key
        interact(trigger={"key": key})

    def button(label):
        click(next(a["key"] for a in state["actions"] if a.get("label") == label))

    def text():
        return json.dumps(state["tree"])

    def wait_for(predicate):
        end = time.monotonic() + 40
        while time.monotonic() < end:
            interact()
            if predicate():
                return
            time.sleep(0.15)
        raise AssertionError(text()[-5000:])

    interact()
    assert "First Look 0.4.0" in text() and "Judgment policy: 2026-11-24.1" in text()
    click("example_penguins")
    button("Investigate this dataset")
    wait_for(lambda: any(n["type"] == "echarts_chart" for n in walk(state["tree"])))
    interact(page="discover")
    submit = next(a["key"] for a in state["actions"] if a.get("label") == "Investigate question")
    interact(widget_state={"question": "Compare flipper_length_mm and body_mass_g"}, trigger={"key": submit})
    wait_for(lambda: any(a.get("label") == "Run this interpretation" for a in state["actions"]))
    assert "Check the interpretation before running it" in text()
    button("Run this interpretation")
    wait_for(lambda: "This interpretation was executed" in text())
    interact(page="text_lab")
    assert any(n["type"] == "data_editor" for n in walk(state["tree"]))
    assert "model" in text().lower() and "selected text" in text()
    interact(page="judgments")
    interact(widget_state={"judgments_mode": "Question library"})
    assert "Download question definitions" in text()
    interact(widget_state={"judgments_mode": "Evaluation cases"})
    assert "no model calls" in text() and "Developer" in text()
    interact(page="evidence")
    click("prepare_export")
    assert len([n for n in walk(state["tree"]) if n["type"] == "download_button"]) == 2
    report = {
        "version": "0.4.0",
        "prepared_before_execution": True,
        "explicit_confirmation": True,
        "text_lab": True,
        "question_library": True,
        "labelled_baseline": True,
        "evidence_export": True,
        "live_provider_calls": False,
        "screenshots_video_traces": False,
    }
    Path("reports/judgments-runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
