"""Prepare, inspect and validate an analytical intent before running it."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from firstlook.contracts import Role, digest
from firstlook.discovery import analyze, plan_for, validate_plan
from firstlook.judgment_catalog import TASKS, intent_specs
from firstlook.questions import QuestionIntent, local_intent
from firstlook.recommendations import descriptive_key
from firstlook.semantic.model import get_model
from firstlook.semantic.planner import metric_plan


def intent_plan(dataset, context, intent):
    if intent.operation == "unsupported":
        raise ValueError(intent.clarification or "Choose a supported interpretation.")
    if intent.operation == "metric":
        if not intent.metric_id:
            raise ValueError("Choose a named metric first.")
        plan = metric_plan(
            dataset, context, intent.metric_id, intent.group_by, intent.time_field, period=intent.period
        )
    elif intent.operation == "group_shape":
        plan = plan_for(
            context, "exploration", intent.fields, "Compare group shapes", {"recipe": "group_shape"}
        )
    else:
        plan = plan_for(context, intent.operation, intent.fields, "Inspect requested evidence")
    validate_plan(dataset, context, plan)
    return plan


def _field_options(dataset, question, roles):
    fields = [f for f in dataset.record.fields if f.role in roles and not f.excluded]
    normalized = re.sub(r"\W+", " ", question.casefold().replace("_", " "))
    fields.sort(
        key=lambda f: (
            -sum(w in normalized.split() for w in f.name.casefold().split("_")),
            -SequenceMatcher(None, normalized, f.name.casefold().replace("_", " ")).ratio(),
            f.position,
        )
    )
    return {
        descriptive_key(f.name, f.id): {"id": f.id, "name": f.name, "role": f.role.value, "unit": f.unit}
        for f in fields[:16]
    }


def prepare_question(dataset, context, question, jev=None):
    if not question.strip() or len(question) > 1000:
        raise ValueError("Enter an analytical question of at most 1,000 characters.")
    if context.id != dataset.context(context.row_ids, context.focus, context.assumption).id:
        raise ValueError("This interpretation has a stale analytical context.")
    intent = local_intent(dataset, question)
    record, group = None, None
    clarification = intent.clarification
    if jev is not None:
        measures = _field_options(dataset, question, {Role.MEASURE})
        groups = _field_options(dataset, question, {Role.CATEGORY, Role.ORDINAL, Role.BOOL})
        times = _field_options(dataset, question, {Role.TIME})
        metrics = {
            descriptive_key(m.label, m.id): {"id": m.id, "name": m.label, "definition": m.description}
            for m in get_model(dataset).metrics[:20]
        }
        state = {
            "goal": question,
            "candidates": TASKS,
            "measures": measures,
            "groups": groups,
            "timestamps": times,
            "metrics": metrics,
        }
        specs = intent_specs(state)
        record = jev.judge(state, specs, context=context.id, purpose="Prepare an analytical interpretation")
        answers = record.answers

        def identity(name, options):
            a = answers.get(name)
            return options[str(a.value)]["id"] if a and a.status == "selected" else None

        op = answers["task"].value
        measure, other = identity("measure", measures), identity("other_measure", measures)
        category, other_category = identity("group", groups), identity("other_group", groups)
        timestamp, metric = identity("timestamp", times), identity("metric", metrics)
        if answers["causal"].status != "no":
            clarification = "This request may require causal identification. Choose an explicit descriptive interpretation; this table alone cannot establish a cause."
            intent = QuestionIntent(operation="unsupported", fields=[], clarification=clarification)
        elif answers["applicable"].status != "yes" or answers["task"].status != "selected":
            intent = QuestionIntent(
                operation="unsupported",
                fields=[],
                clarification="The supplied catalog does not clearly cover this question. Select a concrete descriptive task and its fields.",
            )
        else:
            fields = {
                "relationship": [other, measure],
                "group_shape": [category, measure],
                "distribution": [measure],
                "frequency": [category],
                "category_relationship": [category, other_category],
                "time": [timestamp, measure],
                "missingness": [],
                "metric": [],
            }.get(str(op), [])
            if (
                any(f is None for f in fields)
                or len(set(fields)) != len(fields)
                or (op == "metric" and metric is None)
            ):
                intent = QuestionIntent(
                    operation="unsupported",
                    fields=[],
                    clarification="A required field is unresolved or the same field filled both comparison roles. Correct the interpretation below.",
                )
            else:
                intent = QuestionIntent(
                    operation=op, fields=fields, metric_id=metric if op == "metric" else None
                )
                if (
                    op == "relationship"
                    and answers.get("within_group")
                    and answers["within_group"].status == "yes"
                ):
                    group = category
                    if not group:
                        intent = QuestionIntent(
                            operation="unsupported",
                            fields=[],
                            clarification="The requested subgroup field is unresolved. Select it explicitly.",
                        )
    try:
        plan = intent_plan(dataset, context, intent)
        status, clarification = "ready for confirmation", ""
    except ValueError as exc:
        plan, status, clarification = None, "needs clarification", str(exc)
    return {
        "id": digest([context.id, question, intent.model_dump(), group]),
        "context": context.id,
        "question": question,
        "status": status,
        "clarification": clarification,
        "intent": intent.model_dump(mode="json"),
        "group_field": group,
        "plan": plan.model_dump(mode="json") if plan else None,
        "judgment": record.model_dump(mode="json") if record else None,
        "method": "Typed Jev judgments" if record else "Deterministic interpretation",
        "executed": False,
    }


def execute_prepared(dataset, inv, review, override=None, group_field=None):
    from firstlook.challenges import challenge

    if (
        review["context"] != inv.context.id
        or inv.context.id
        != dataset.context(inv.context.row_ids, inv.context.focus, inv.context.assumption).id
    ):
        raise ValueError("The prepared interpretation belongs to an earlier context.")
    intent = QuestionIntent.model_validate(override or review["intent"])
    plan = intent_plan(dataset, inv.context, intent).model_copy(update={"question": review["question"]})
    group = group_field if override else review.get("group_field")
    if group:
        if (
            intent.operation != "relationship"
            or group not in dataset.frame
            or dataset.field(group).role not in {Role.CATEGORY, Role.ORDINAL, Role.BOOL}
            or dataset.field(group).excluded
        ):
            raise ValueError(
                "A subgroup companion requires an eligible recorded category and numerical relationship."
            )
    result, finding = analyze(dataset, inv.context, plan)
    inv.add_view(result, finding)
    if group:
        inv.challenges.append(challenge(dataset, inv, finding, "subgroup", group))
    inv.goal = review["question"]
    inv.question_history = (
        inv.question_history
        + [
            {
                **review,
                "executed": True,
                "human_corrected": override is not None,
                "executed_intent": intent.model_dump(mode="json"),
                "result_id": result.id,
            }
        ]
    )[-20:]
    if review.get("judgment"):
        from firstlook.judgments import JudgmentBatch

        inv.judgments.append(JudgmentBatch.model_validate(review["judgment"]))
    return inv
