"""Question-directed analysis resolves only known fields and catalog operations."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from firstlook.contracts import Contract
from firstlook.discovery import Investigation, analyze, plan_for
from firstlook.ingest import Dataset
from firstlook.semantics import dimensions, measures


class QuestionIntent(Contract):
    operation: Literal[
        "distribution",
        "frequency",
        "relationship",
        "group_distribution",
        "missingness",
        "quantile_bin_summary",
        "time",
        "metric",
        "unsupported",
    ]
    fields: list[str] = Field(max_length=2)
    clarification: str = Field(default="", max_length=800)
    metric_id: str | None = None
    group_by: list[str] = Field(default_factory=list, max_length=2)
    time_field: str | None = None


def local_intent(dataset: Dataset, question: str) -> QuestionIntent:
    q = question.casefold()
    if re.search(r"\b(cause|caused|causal|prove|why)\b", q):
        return QuestionIntent(
            operation="unsupported",
            fields=[],
            clarification="This table cannot establish a cause. Try a relationship or group comparison.",
        )
    hits = [
        f.id
        for f in dataset.record.fields
        if re.search(r"(?<!\w)" + re.escape(f.name.casefold()) + r"(?!\w)", q)
        or re.search(r"\b" + f.id + r"\b", q)
    ]
    nums = [f for f in hits if f in measures(dataset)]
    cats = [f for f in hits if f in dimensions(dataset)]
    from firstlook.semantic.model import get_model

    named = [
        m
        for m in get_model(dataset).metrics
        if m.label.casefold() in q or re.search(r"\b" + re.escape(m.id) + r"\b", q)
    ]
    if named:
        metric = max(named, key=lambda m: len(m.label))
        times = [f for f in hits if dataset.field(f).role.value == "timestamp"]
        return QuestionIntent(
            operation="metric",
            fields=[],
            metric_id=metric.id,
            group_by=cats[:2] if not times else [],
            time_field=times[0] if times else None,
        )
    if (
        re.search(r"\b(total|sum|average|weighted|share|percentage|percent|per order|per customer)\b", q)
        and hits
    ):
        return QuestionIntent(
            operation="unsupported",
            fields=[],
            clarification="Choose or define a named metric in Meaning first. Totals, row averages, entity averages and shares need an explicit value grain and denominator. Use that metric's name in your question.",
        )
    if "missing" in q:
        return QuestionIntent(operation="missingness", fields=[])
    if cats and nums:
        return QuestionIntent(operation="group_distribution", fields=[cats[0], nums[0]])
    if len(nums) >= 2:
        return QuestionIntent(
            operation="quantile_bin_summary" if "shape" in q else "relationship", fields=nums[:2]
        )
    if nums:
        return QuestionIntent(operation="distribution", fields=nums[:1])
    if cats:
        return QuestionIntent(operation="frequency", fields=cats[:1])
    return QuestionIntent(
        operation="unsupported",
        fields=[],
        clarification="Name a field, two measures, or a measure and a group. You can also use the suggested questions.",
    )


def run_question(dataset: Dataset, inv: Investigation, question: str, terra=None) -> Investigation:
    if not question.strip() or len(question) > 1000:
        raise ValueError("Enter a question of at most 1,000 characters.")
    intent = local_intent(dataset, question)
    if (
        terra is not None
        and intent.operation == "unsupported"
        and not re.search(r"\b(cause|causal|prove)\b", question, re.I)
    ):
        intent = terra.question(dataset, question)
    if intent.operation == "unsupported":
        raise ValueError(intent.clarification or "This request is outside the supported analytical catalog.")
    if intent.operation == "metric":
        from firstlook.semantic.planner import metric_plan

        if not intent.metric_id:
            raise ValueError("Choose a recorded metric definition in Meaning.")
        result, finding = analyze(
            dataset,
            inv.context,
            metric_plan(
                dataset,
                inv.context,
                intent.metric_id,
                intent.group_by,
                intent.time_field,
                question=question.strip(),
            ),
        )
        inv.add_view(result, finding)
        return inv
    sizes = {
        "distribution": 1,
        "frequency": 1,
        "relationship": 2,
        "group_distribution": 2,
        "missingness": 0,
        "quantile_bin_summary": 2,
        "time": 2,
    }
    if len(intent.fields) != sizes[intent.operation]:
        raise ValueError("This question did not resolve to a complete supported analysis.")
    result, finding = analyze(
        dataset, inv.context, plan_for(inv.context, intent.operation, intent.fields, question.strip())
    )
    inv.add_view(result, finding)
    return inv
