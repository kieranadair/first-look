"""Exercise a real Streamlit session through the development-only agent API."""

import argparse
import json
import time
from pathlib import Path

import httpx


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.url, timeout=45)
    schema = client.get("/_stcore/agent/openapi.json").raise_for_status().json()
    assert "/_stcore/agent/interact" in schema["paths"]
    state = {}

    def interact(**kw):
        nonlocal state
        body = {"session_id": state["session_id"]} if state else {}
        state = client.post("/_stcore/agent/interact", json={**body, **kw}).raise_for_status().json()
        assert state["status"] == "ready", json.dumps(state)[-5000:]
        return state

    def action(label):
        return next(a["key"] for a in state["actions"] if a.get("label") == label)

    def click(label):
        interact(trigger={"key": action(label)})

    interact()
    interact(trigger={"key": "example_reversal"})
    click("Investigate this dataset")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        interact()
        if any(n["type"] == "echarts_chart" for n in walk(state["tree"])):
            break
        time.sleep(0.25)
    else:
        raise AssertionError("Investigation did not publish charts")
    checks = {"landing_and_discovery": True}
    interact(page="discover")
    pin = next(a["key"] for a in state["actions"] if a.get("label") == "Pin")
    interact(trigger={"key": pin})
    for page in ["challenge", "evidence"]:
        interact(page=page)
        checks[page] = True
    click("Prepare downloads")
    downloads = [n for n in walk(state["tree"]) if n["type"] == "download_button"]
    assert len(downloads) == 2
    checks["exports"] = True
    checks["download_bytes"] = [n.get("props", {}).get("label") for n in downloads]
    Path("reports/runtime.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
