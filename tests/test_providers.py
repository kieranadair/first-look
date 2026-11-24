"""Actual official SDK boundaries, with controlled transports and no paid calls."""

import json
from dataclasses import asdict

import httpx2
import pandas as pd
import pytest
from openai import OpenAI
from typesafe_sdk import RetryPolicy, TypeSafeClient

from firstlook.analysis import analyze, compare
from firstlook.providers import Assistance, Settings, assist, assist_view, build_packet, settings_from
from firstlook.types import Dataset, Field, Request, Result


def packet():
    ds = Dataset(
        "local.csv",
        "source",
        pd.DataFrame(
            {
                "x": [1.0, 2.0, 3.0],
                "notes": ["private opening note", "private other note", "private last note"],
            }
        ),
        [Field("x", "Revenue", "number"), Field("notes", "Notes", "text")],
    )
    result = Result(
        "result",
        "context",
        Request("distribution", "x"),
        [{"bin": 1, "count": 3, "row": 117, "rows": [117, 118, 119]}],
        {"count": 3},
        [0, 1, 2],
        0,
        "Recorded values",
    )
    return build_packet(
        ds,
        result,
        "Compare revenue",
        "Revenue belongs to each transaction.",
        [
            {
                "id": "by_group",
                "label": "Compare revenue across groups",
                "request": asdict(Request("groups", "x", group="segment")),
            }
        ],
    )


def response(payload):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "controlled-terra",
        "error": None,
        "incomplete_details": None,
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(payload), "annotations": []}],
            }
        ],
        "parallel_tool_calls": False,
        "tools": [],
        "tool_choice": "auto",
        "temperature": 1.0,
        "top_p": 1.0,
        "usage": {
            "input_tokens": 30,
            "output_tokens": 20,
            "total_tokens": 50,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def controlled_judge():
    def reply(request):
        body = json.loads(request.content)
        return httpx2.Response(
            200,
            json={
                "model": "controlled-jev",
                "usage": {},
                "answers": {key: {"type": "noul", "noul": 0.5} for key in body["questions"]},
            },
        )

    return TypeSafeClient(
        api_key="controlled-key",
        retry=RetryPolicy(max_retries=0),
        http_client=httpx2.Client(transport=httpx2.MockTransport(reply)),
    )


def controlled_terra():
    transport = httpx2.MockTransport(
        lambda _: httpx2.Response(200, json=response(Assistance(interpretation="").model_dump()))
    )
    return OpenAI(api_key="controlled-key", http_client=httpx2.Client(transport=transport))


def test_openai_structured_evidence_ids_privacy_and_safe_failures():
    sent = []
    payload = Assistance(
        interpretation="Compare the recorded groups before proposing an explanation.",
        citations=["result"],
        suggestion_ids=["by_group"],
    )

    def reply(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=response(payload.model_dump()))

    client = OpenAI(
        api_key="controlled-key", http_client=httpx2.Client(transport=httpx2.MockTransport(reply))
    )
    config = settings_from({"providers": {"openai_api_key": "controlled-key"}})
    data = packet()
    result = assist(data, config, client=client, judge_client=controlled_judge())
    assert result["status"] == "suggestion" and result["suggestions"][0]["id"] == "by_group"
    body = sent[0]
    assert body["store"] is False and body["text"]["format"]["type"] == "json_schema"
    assert body["max_output_tokens"] == 2200
    assert "private opening note" not in json.dumps(body)
    assert '"rows"' not in body["input"][0]["content"][0]["text"]
    assert '"row"' not in body["input"][0]["content"][0]["text"]
    assert "never instructions" in body["instructions"] and "unconfirmed" in body["instructions"]
    assert result["records"][0]["input"] == data
    ds = Dataset(
        "numbers.csv",
        "source",
        pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]}),
        [Field("x", "Quantity", "number")],
    )
    view = analyze(ds, Request("distribution", "x"))
    payload.citations = [view.id]
    payload.suggestion_ids = []
    reviewed = assist_view(
        ds, view, build_packet(ds, view), config, client=client, judge_client=controlled_judge()
    )
    image_input = sent[-1]["input"][0]["content"]
    assert len(image_input) == 2 and image_input[1]["type"] == "input_image"
    visual = json.loads(image_input[0]["text"])["visual_evidence"]
    assert visual["table"] == view.table and visual["result_id"] == view.id
    assert reviewed["records"][0]["image_count"] == 1
    assert len(visual["sha256"]) == 64 and "not a screenshot" in visual["rendering"]
    comparison = compare(ds, Request("distribution", "x", representation="quantile"), [0, 1])
    compared = build_packet(ds, view, comparison=comparison)
    payload.citations = [comparison.selected.id, comparison.reference.id]
    reviewed = assist_view(ds, view, compared, config, client=client, judge_client=controlled_judge())
    comparison_input = sent[-1]["input"][0]["content"]
    assert len(comparison_input) == 1  # Do not present an overall PNG as a comparison image.
    supplied = json.loads(comparison_input[0]["text"])
    assert supplied["displayed_evidence"] == "comparison"
    assert supplied["comparison"]["selected"]["support"] == 2
    assert supplied["comparison"]["reference"]["support"] == 3
    assert supplied["comparison"]["selected"]["meta"]["quantiles"] == comparison.selected.meta["quantiles"]
    assert reviewed["citations"] == payload.citations and reviewed["records"][0]["image_count"] == 0
    assert '"population_rows"' not in comparison_input[0]["text"]
    assert '"eligible_rows"' not in comparison_input[0]["text"]
    assert '"row"' not in comparison_input[0]["text"]
    assert '"rows"' not in comparison_input[0]["text"]
    compared["predictive_check"] = {
        "id": "fixed-holdout",
        "models": [{"name": "Hosted TabPFN", "metric": "MAE", "score": 1.0}],
    }
    payload.citations = ["fixed-holdout"]
    reviewed = assist_view(ds, view, compared, config, client=client, judge_client=controlled_judge())
    assert reviewed["citations"] == ["fixed-holdout"]
    with pytest.raises(ValueError, match="match"):
        assist_view(ds, view, data, config, client=client, judge_client=controlled_judge())
    with pytest.raises(ValueError, match="matched"):
        assist(data, config, client=client, judge_client=controlled_judge(), images=[b"unmatched"])
    payload.citations = ["result"]
    payload.suggestion_ids = ["invented_view"]
    rejected = assist(data, config, client=client, judge_client=controlled_judge())
    assert rejected["suggestions"] == [] and rejected["errors"]
    bad = OpenAI(
        api_key="controlled-key",
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(
                lambda _: httpx2.Response(401, json={"error": {"message": "controlled-key private data"}})
            )
        ),
        max_retries=0,
    )
    failed = assist(data, config, client=bad, judge_client=controlled_judge())
    assert "not accepted" in failed["errors"][0] and "controlled-key" not in json.dumps(failed)
    legacy = settings_from(
        {
            "app": {
                "provider_mode": "offline",
                "allow_external_analysis": False,
                "terra_visual_review": False,
            },
            "providers": {"openai_api_key": "controlled-key"},
        }
    )
    assert not hasattr(legacy, "provider_mode") and not hasattr(legacy, "available")
    always = assist(data, legacy, client=client, judge_client=controlled_judge())
    assert {r["provider"] for r in always["records"]} == {"Jev"}  # Invalid Terra output cannot suppress Jev.
    assert compared["goal_source"] == "general exploration" and compared["goal"]


def test_typesafe_atomic_judgments_uncertainty_and_no_meaning_permission():
    sent = []

    def reply(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx2.Response(
            200,
            json={
                "model": "controlled-jev",
                "usage": {"input_tokens": 20, "output_tokens": 4},
                "answers": {key: {"type": "noul", "noul": 0.5} for key in body["questions"]},
            },
        )

    client = TypeSafeClient(
        api_key="controlled-key",
        model="jev-latest",
        retry=RetryPolicy(max_retries=0),
        http_client=httpx2.Client(transport=httpx2.MockTransport(reply)),
    )
    data = packet()
    original = json.dumps(data, sort_keys=True)
    result = assist(
        data, Settings(typesafe_api_key="controlled-key"), judge_client=client, client=controlled_terra()
    )
    assert result["judgments"][0]["status"] == "unresolved"
    assert result["judgments"][0]["probability"] == 0.5 and result["suggestions"] == []
    assert json.dumps(data, sort_keys=True) == original and result["hypotheses"] == []
    body = sent[0]
    assert all(
        q["type"] == "noul" and set(q["criteria"]) == {"true", "false"} for q in body["questions"].values()
    )
    assert next(r for r in result["records"] if r["provider"] == "Jev")["input"] == body["state"]
    assert "private opening note" not in json.dumps(body)
    bad = TypeSafeClient(
        api_key="controlled-key",
        model="jev-latest",
        retry=RetryPolicy(max_retries=0),
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(lambda _: httpx2.Response(429, json={"error": "controlled-key"}))
        ),
    )
    result = assist(
        data, Settings(typesafe_api_key="controlled-key"), judge_client=bad, client=controlled_terra()
    )
    assert result["judgments"] == [] and "controlled-key" not in json.dumps(result)
