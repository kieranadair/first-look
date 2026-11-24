"""Recorded model judgments and a labelled deterministic baseline, without auto calls."""

from __future__ import annotations

from firstlook.judgments import JudgmentBatch

CASES = [
    {"id": "distribution", "question": "Show bill_length_mm", "expected": "distribution"},
    {"id": "association", "question": "Compare bill_length_mm and body_mass_g", "expected": "relationship"},
    {
        "id": "group_shape",
        "question": "Compare distributions of body_mass_g by species",
        "expected": "group_shape",
    },
    {"id": "unsupported_field", "question": "Compare customer revenue with churn", "expected": "unsupported"},
    {"id": "causal", "question": "Prove species causes body_mass_g", "expected": "unsupported"},
    {"id": "missingness", "question": "Show missing values", "expected": "missingness"},
    {"id": "ambiguous_language", "question": "Are the larger ones different?", "expected": "unsupported"},
]


def evaluate_cases(jev=None):
    from firstlook.examples import load_example
    from firstlook.question_workflow import prepare_question

    ds = load_example("penguins")
    rows, records = [], []
    for case in CASES:
        review = prepare_question(ds, ds.context(), case["question"], jev)
        observed = (
            review["intent"]["operation"] if review["status"] == "ready for confirmation" else "unsupported"
        )
        rows.append(
            {**case, "observed": observed, "match": observed == case["expected"], "status": review["status"]}
        )
        if review.get("judgment"):
            records.append(review["judgment"])
    return {
        "mode": "Live Jev" if jev else "Deterministic routing baseline; no model calls",
        "cases": rows,
        "accuracy": sum(r["match"] for r in rows) / len(rows),
        "coverage": sum(r["observed"] != "unsupported" for r in rows) / len(rows),
        "judgments": records,
        "limits": "Seven developer-labelled routing cases, not a general benchmark, calibration estimate or productivity study.",
    }


def recorded_judgments(workspace):
    records = list(workspace.investigation.judgments) if workspace.investigation else []
    preparations = [workspace.preparation] + workspace.preparation_history
    for preparation in preparations:
        records.extend(
            JudgmentBatch.model_validate(r)
            for r in preparation.get("records", [])
            if "definitions" in r and "answers" in r
        )
    for raw in [workspace.question_review.get("judgment"), workspace.note_review.get("record")]:
        if raw:
            records.append(JudgmentBatch.model_validate(raw))
    for run in workspace.text_runs:
        records.extend(JudgmentBatch.model_validate(r) for r in run.get("judgments", []))
    comparisons = list(workspace.comparisons)
    if workspace.comparison:
        comparisons.append(workspace.comparison)
    for comparison in comparisons:
        records.extend(
            JudgmentBatch.model_validate(r) for r in comparison.interpretation.get("judgments", [])
        )
    return list({record.id: record for record in records}.values())


def compare_records(first, second):
    first = JudgmentBatch.model_validate(first)
    second = JudgmentBatch.model_validate(second)
    common = sorted(set(first.answers) & set(second.answers))
    a = {s.id: s for s in first.definitions}
    b = {s.id: s for s in second.definitions}
    return [
        {
            "Question": k,
            "Definition changed": a[k] != b[k],
            "First status": first.answers[k].status,
            "Second status": second.answers[k].status,
            "First value": str(first.answers[k].value),
            "Second value": str(second.answers[k].value),
            "Outcome changed": first.answers[k].status != second.answers[k].status
            or first.answers[k].value != second.answers[k].value,
            "Same supplied state": first.state_hash == second.state_hash,
            "Same resolved model": first.resolved_model == second.resolved_model,
        }
        for k in common
    ]
