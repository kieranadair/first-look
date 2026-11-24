"""Bounded, frozen semantic text features with explicit unknowns and source rows."""

from __future__ import annotations

from collections import Counter
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from firstlook.contracts import Contract, Role, ModelRun, digest
from firstlook.judgments import JudgmentBatch, request_input_size
from firstlook.judgment_catalog import text_spec

MAX_TEXT_ROWS, MAX_FEATURES, MAX_TEXT_CHARS = 240, 6, 2000
TEXT_SCOPE = "Answer each frozen question about its named source text only; do not infer absent information from other records."


class TextFeatureSpec(Contract):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=8, max_length=220)
    yes: str = Field(min_length=8, max_length=300)
    no: str = Field(min_length=8, max_length=300)
    version: str = "1"


class FeatureProposal(Contract):
    features: list[TextFeatureSpec] = Field(min_length=1, max_length=6)


class TextFeatureRun(Contract):
    id: str
    context: str
    source_field: str
    source_rows: list[int] = Field(min_length=1, max_length=MAX_TEXT_ROWS)
    definitions: list[TextFeatureSpec] = Field(min_length=1, max_length=MAX_FEATURES)
    records: list[dict] = Field(max_length=MAX_TEXT_ROWS)
    judgments: list[JudgmentBatch] = Field(default_factory=list, max_length=64)
    source_population: int = Field(ge=1, le=50_000)
    selection: str
    hypothetical: Literal[True] = True
    evaluation: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def membership(self):
        if (
            len(set(self.source_rows)) != len(self.source_rows)
            or [r["row_id"] for r in self.records] != self.source_rows
        ):
            raise ValueError("Text feature records must retain each selected source row exactly once.")
        if len(self.source_rows) > self.source_population:
            raise ValueError("A selected text run cannot exceed its recorded source population.")
        keys = [f.key for f in self.definitions]
        if len(set(keys)) != len(keys) or len({f.label for f in self.definitions}) != len(keys):
            raise ValueError("Feature keys and labels must be distinct.")
        answers = {qid: answer for batch in self.judgments for qid, answer in batch.answers.items()}
        specifications = {s.id: s for batch in self.judgments for s in batch.definitions}
        for row in self.records:
            if set(row["features"]) != set(keys):
                raise ValueError("Every feature must retain an outcome for every selected row.")
            for item in row["features"].values():
                if item["status"] not in {"yes", "no", "unresolved", "missing", "too_long"}:
                    raise ValueError("Unknown text-coding status.")
                expected = True if item["status"] == "yes" else False if item["status"] == "no" else None
                if item["value"] is not expected:
                    raise ValueError("Unresolved or unobserved text cannot become a negative observation.")
            for key, item in row["features"].items():
                if item["status"] in {"yes", "no", "unresolved"}:
                    answer = answers.get("text_" + digest([row["input_hash"], key]))
                    if (
                        answer is None
                        or answer.kind != "noul"
                        or answer.status != item["status"]
                        or answer.value is not item["value"]
                        or answer.probabilities["yes"] != item["yes_probability"]
                    ):
                        raise ValueError("A coded feature does not match its recorded typed answer.")
                    feature = next(f for f in self.definitions if f.key == key)
                    expected_spec = text_spec(feature, row["input_hash"])
                    if specifications.get(expected_spec.id) != expected_spec:
                        raise ValueError(
                            "A frozen feature question differs from the recorded question actually asked."
                        )
        if any(batch.context != self.context for batch in self.judgments):
            raise ValueError("Text judgments belong to a different analytical context.")
        if self.id != digest(
            [self.context, self.source_field, [f.model_dump() for f in self.definitions], self.records]
        ):
            raise ValueError("The frozen feature identity does not match its definitions and records.")
        return self


def selected_text_rows(dataset, context, field, limit=60):
    if context.id != dataset.context(context.row_ids, context.focus, context.assumption).id:
        raise ValueError("The text feature plan has a stale context.")
    spec = dataset.field(field)
    if (
        spec.excluded
        or spec.role not in {Role.TEXT, Role.CATEGORY}
        or not all(isinstance(v, str) for v in dataset.frame[field].dropna())
    ):
        raise ValueError("Select an included text or categorical string field.")
    if not 1 <= limit <= MAX_TEXT_ROWS:
        raise ValueError("Choose between one and 240 source rows.")
    ids = list(context.row_ids)
    if len(ids) > limit:
        ids = sorted(np.random.default_rng(20261124).choice(ids, limit, replace=False).tolist())
    return ids


def preview_text_cost(dataset, context, field, definitions, limit=60):
    ids = selected_text_rows(dataset, context, field, limit)
    texts = dataset.frame.loc[ids, field]
    unique = list(
        dict.fromkeys(str(v) for v in texts.dropna() if str(v).strip() and len(str(v)) <= MAX_TEXT_CHARS)
    )
    definitions = [TextFeatureSpec.model_validate(f) for f in definitions]
    sizes = []
    for start in range(0, len(unique), 4):
        part = {digest(t): t for t in unique[start : start + 4]}
        state = {"texts": {"text_" + k: v for k, v in part.items()}, "scope": TEXT_SCOPE}
        questions = [text_spec(f, k) for k in part for f in definitions]
        sizes.append(request_input_size(state, questions))
    return {
        "rows": len(ids),
        "source_population": len(context.row_ids),
        "features": len(definitions),
        "unique_codable_texts": len(unique),
        "questions": len(unique) * len(definitions),
        "max_requests": int(np.ceil(len(unique) / 4)),
        "source_characters": sum(len(t) for t in unique),
        "missing_or_empty": sum(pd.isna(v) or not str(v).strip() for v in texts),
        "overlong": sum(not pd.isna(v) and len(str(v)) > MAX_TEXT_CHARS for v in texts),
        "input_budget_bytes": sum(sizes),
        "largest_batch_bytes": max(sizes, default=0),
    }


def code_text(
    dataset, context, field, definitions, limit, jev, progress=lambda _: None, cancelled=lambda: False
):
    definitions = [TextFeatureSpec.model_validate(v) for v in definitions]
    if (
        not 1 <= len(definitions) <= MAX_FEATURES
        or len({f.key for f in definitions}) != len(definitions)
        or len({f.label for f in definitions}) != len(definitions)
    ):
        raise ValueError("Choose one to six distinct feature definitions.")
    cost = preview_text_cost(dataset, context, field, definitions, limit)
    if (
        cost["largest_batch_bytes"] > 48_000
        or cost["input_budget_bytes"]
        > getattr(jev, "max_input_bytes", 2_000_000) - getattr(jev, "input_bytes", 0)
        or cost["questions"] > getattr(jev, "max_questions", 1440) - getattr(jev, "questions", 0)
        or cost["max_requests"] > getattr(jev, "max_calls", 64) - getattr(jev, "calls", 0)
    ):
        raise ValueError(
            "This coding plan exceeds the bounded request, question or input budget. Reduce rows or shorten criteria before sending any text."
        )
    ids = selected_text_rows(dataset, context, field, limit)
    texts = {}
    inputs = {}
    for row in ids:
        value = dataset.frame.at[row, field]
        if pd.isna(value) or not str(value).strip():
            inputs[row] = (None, "missing")
        elif len(str(value)) > MAX_TEXT_CHARS:
            inputs[row] = (digest(str(value)), "too_long")
        else:
            key = digest(str(value))
            inputs[row] = (key, "coded")
            texts[key] = str(value)
    coded, batches = {}, []
    keys = list(texts)
    for start in range(0, len(keys), 4):
        if cancelled():
            raise ValueError("Text coding was cancelled; no partial result was published.")
        part = keys[start : start + 4]
        state = {
            "texts": {"text_" + key: texts[key] for key in part},
            "scope": TEXT_SCOPE,
        }
        specs = []
        for key in part:
            for feature in definitions:
                specs.append(text_spec(feature, key))
        progress(f"Coding text batch {start // 4 + 1} of {int(np.ceil(len(keys) / 4))}")
        batch = jev.judge(state, specs, context=context.id, purpose="Frozen text-feature coding")
        batches.append(batch)
        for key in part:
            coded[key] = {}
            for feature in definitions:
                answer = batch.answers["text_" + digest([key, feature.key])]
                coded[key][feature.key] = {
                    "value": answer.value,
                    "status": answer.status,
                    "yes_probability": answer.probabilities["yes"],
                }
    records = []
    for row in ids:
        key, status = inputs[row]
        features = (
            coded[key]
            if status == "coded"
            else {f.key: {"value": None, "status": status, "yes_probability": None} for f in definitions}
        )
        records.append({"row_id": row, "input_hash": key, "features": features})
    identity = digest([context.id, field, [f.model_dump() for f in definitions], records])
    return TextFeatureRun(
        id=identity,
        context=context.id,
        source_field=field,
        source_rows=ids,
        definitions=definitions,
        records=records,
        judgments=batches,
        source_population=len(context.row_ids),
        selection="All active rows"
        if len(ids) == len(context.row_ids)
        else "Seeded sample of active rows; seed 20261124",
    )


def feature_summary(run):
    rows = []
    for feature in run.definitions:
        counts = Counter(row["features"][feature.key]["status"] for row in run.records)
        known = counts["yes"] + counts["no"]
        rows.append(
            {
                "Feature": feature.label,
                "Yes": counts["yes"],
                "No": counts["no"],
                "Unresolved": counts["unresolved"],
                "Missing": counts["missing"],
                "Too long": counts["too_long"],
                "Classified coverage": known / len(run.records),
                "Yes share among classified": counts["yes"] / known if known else None,
            }
        )
    return rows


def feature_table(run):
    return pd.DataFrame(
        [
            {
                "source_row_id": row["row_id"],
                **{f.label: row["features"][f.key]["status"] for f in run.definitions},
            }
            for row in run.records
        ]
    )


def validate_text_source(dataset, context, run):
    if run.context != context.id or not set(run.source_rows) <= set(context.row_ids):
        raise ValueError("This text run belongs to another context or source population.")
    for row in run.records:
        value = dataset.frame.at[row["row_id"], run.source_field]
        expected = None if pd.isna(value) or not str(value).strip() else digest(str(value))
        if expected != row["input_hash"]:
            raise ValueError("The text run does not match the exact source text.")


def derived_model_table(dataset, context, run, target, split_field, available_confirmed):
    from firstlook.ingest import from_frame
    from firstlook.semantic.model import get_model, validate_model
    from firstlook.semantic.profile import build_model

    validate_text_source(dataset, context, run)
    original = get_model(dataset)
    from firstlook.analytical_tasks import (
        current_task,
        availability_rules,
        availability_decision,
        availability_basis,
    )

    source_task = current_task(dataset)
    timing, reason = availability_decision(
        dataset, run.source_field, dataset.frame.loc[run.source_rows], source_task
    )
    if timing == "excluded":
        raise ValueError("Source text is ineligible: " + reason)
    if not available_confirmed or not original.meaning(run.source_field).available_at_prediction:
        raise ValueError(
            "Confirm pre-outcome text availability; a declared unavailable source cannot become a predictor."
        )
    if target == run.source_field or target not in dataset.frame:
        raise ValueError("Choose an independent recorded predictive target.")
    essential = {f for f in [target, split_field, original.model_group] if f is not None}
    essential.update(f for f in [source_task.anchor_field, source_task.outcome_known_field] if f)
    rules = availability_rules(dataset)
    essential.update(r.timestamp for r in rules.values() if r.timestamp)
    essential.update(k for e in original.entities for k in e.keys)
    allowed = [
        f.id
        for f in dataset.record.fields
        if not f.excluded and f.role not in {Role.TEXT, Role.UNKNOWN} and f.id != run.source_field
    ]
    selected = list(dict.fromkeys([*sorted(essential), *allowed]))[:50]
    selected = [f for f in selected if f in dataset.frame]
    frame = dataset.frame.loc[run.source_rows, selected].copy()
    frame.columns = [dataset.label(f) for f in selected]
    feature_names = []
    for feature in run.definitions:
        name = "Model-coded " + feature.label
        while name in frame:
            name += " (coded)"
        frame[name] = [row["features"][feature.key]["status"] for row in run.records]
        feature_names.append(name)
    raw = frame.to_csv(index=False).encode()
    derived = from_frame(
        frame, "coded-model-table.csv", raw=raw, source="Frozen model-coded text feature table"
    )
    mapping = {src: derived.record.fields[i].id for i, src in enumerate(selected)}
    for src, dst in mapping.items():
        old, new = dataset.field(src), derived.field(dst)
        new.role, new.unit, new.excluded = old.role, old.unit, old.excluded
    feature_ids = [derived.record.fields[len(selected) + i].id for i in range(len(feature_names))]
    for fid in feature_ids:
        derived.field(fid).role = Role.CATEGORY
        derived.field(
            fid
        ).evidence = (
            "Model-coded interpretation; unresolved/missing/overlong remain distinct categorical states."
        )
    model = build_model(derived)
    model.entities = [
        e.model_copy(update={"keys": [mapping[k] for k in e.keys]}, deep=True)
        for e in original.entities
        if set(e.keys) <= set(mapping)
    ]
    model.model_group = mapping.get(original.model_group) if original.model_group else None
    for src, dst in mapping.items():
        model.meaning(dst).available_at_prediction = original.meaning(src).available_at_prediction
    inherited = {}
    for src, dst in mapping.items():
        if src in rules:
            inherited[dst] = (
                rules[src]
                .model_copy(update={"field": dst, "timestamp": mapping.get(rules[src].timestamp)})
                .model_dump(mode="json")
            )
    for fid in feature_ids:
        if run.source_field in rules:
            inherited[fid] = (
                rules[run.source_field]
                .model_copy(
                    update={"field": fid, "timestamp": mapping.get(rules[run.source_field].timestamp)}
                )
                .model_dump(mode="json")
            )
    if inherited:
        model.search["availability"] = inherited
    if original.search.get("analytical_task"):
        model.search["analytical_task"] = source_task.model_copy(
            update={
                "dataset": derived.record.fingerprint,
                "target": mapping.get(source_task.target),
                "anchor_field": mapping.get(source_task.anchor_field),
                "outcome_known_field": mapping.get(source_task.outcome_known_field),
            }
        ).model_dump(mode="json")
    if original.search.get("analytical_task"):
        from firstlook.analytical_tasks import TaskDefinition

        derived_task = TaskDefinition.model_validate(model.search["analytical_task"])
        for raw in inherited.values():
            if raw["status"] == "known_at_anchor" and raw["basis"] == availability_basis(source_task):
                raw["basis"] = availability_basis(derived_task)
        model.search["availability"] = inherited
    derived.record.semantic_model = validate_model(derived, model)
    derived.record.description = f"Frozen text run {run.id}; parent context {context.id}. Source row mapping is saved separately. Questions were fixed without target values or held-out errors."
    return derived, mapping[target], mapping.get(split_field), feature_ids, mapping


def evaluate_features(
    dataset,
    context,
    run,
    target,
    split,
    split_field,
    available_confirmed,
    provider=None,
    progress=lambda _: None,
    cancelled=lambda: False,
):
    from firstlook.modeling import run_model
    from firstlook.model_protocol import prepare_model

    derived, y, group, features, mapping = derived_model_table(
        dataset, context, run, target, split_field, available_confirmed
    )
    ctx = derived.context()
    allowed = prepare_model(derived, ctx, y, split, group).predictors
    base = [f for f in allowed if f not in features and f != group][:34]
    augmented = list(dict.fromkeys(base + [f for f in features if f in allowed]))[:40]
    if not base or augmented == base:
        raise ValueError(
            "The comparison needs original permitted predictors and at least one varying, non-leaking coded feature."
        )
    baseline = run_model(derived, ctx, y, split, group, base, progress=progress, cancelled=cancelled)
    enhanced = run_model(derived, ctx, y, split, group, augmented, provider, progress, cancelled)
    enhanced.warnings.append(
        "Coded predictors retain unresolved, missing and overlong as separate states. A predictive gain can reflect the recording process as well as text meaning; it is not a causal effect."
    )
    if baseline.train_ids != enhanced.train_ids or baseline.test_ids != enhanced.test_ids:
        raise ValueError("Predictive feature comparisons must use exactly matched held-out memberships.")
    return {
        "parent_context": context.id,
        "feature_run": run.id,
        "derived_schema": derived.record.model_dump(mode="json"),
        "derived_context": ctx.model_dump(mode="json"),
        "source_rows": run.source_rows,
        "source_field_mapping": mapping,
        "feature_fields": features,
        "baseline": baseline.model_dump(mode="json"),
        "augmented": enhanced.model_dump(mode="json"),
        "protocol": "Frozen questions; matched final holdout; no feature-search or held-out feedback loop",
        "availability_confirmed": available_confirmed,
        "matched_comparisons": matched_feature_comparisons(baseline, enhanced),
    }


def matched_feature_comparisons(baseline, augmented):
    """Hold the estimator and memberships fixed when assessing coded representation."""
    if baseline.train_ids != augmented.train_ids or baseline.test_ids != augmented.test_ids:
        raise ValueError("Feature ablations need exactly matched memberships.")
    rows = []
    for name in sorted(set(baseline.metrics) & set(augmented.metrics)):
        for metric in sorted(set(baseline.metrics[name]) & set(augmented.metrics[name])):
            before, after = baseline.metrics[name][metric], augmented.metrics[name][metric]
            rows.append(
                {
                    "Model held fixed": name,
                    "Metric": metric,
                    "Original": before,
                    "Original + coded": after,
                    "Difference": after - before,
                    "Direction": "Lower is better"
                    if metric in {"MAE", "RMSE", "Log loss"}
                    else "Higher is better",
                }
            )
    return rows


def validate_feature_evaluation(run):
    if not run.evaluation:
        return
    evaluation = run.evaluation
    baseline = ModelRun.model_validate(evaluation["baseline"])
    augmented = ModelRun.model_validate(evaluation["augmented"])
    from firstlook.model_protocol import validate_recorded_protocol

    validate_recorded_protocol(baseline)
    validate_recorded_protocol(augmented)
    if evaluation.get("matched_comparisons") is not None and evaluation[
        "matched_comparisons"
    ] != matched_feature_comparisons(baseline, augmented):
        raise ValueError("Recorded feature ablation differences disagree with the matched model metrics.")
    if (
        evaluation["parent_context"] != run.context
        or evaluation["feature_run"] != run.id
        or evaluation["source_rows"] != run.source_rows
        or baseline.context != augmented.context
        or baseline.train_ids != augmented.train_ids
        or baseline.test_ids != augmented.test_ids
    ):
        raise ValueError("The saved text-feature evaluation has mismatched context or holdout memberships.")
    from firstlook.contracts import AnalysisContext, DatasetRecord

    ctx = AnalysisContext.model_validate(evaluation["derived_context"])
    schema = DatasetRecord.model_validate(evaluation["derived_schema"])
    if (
        ctx.id != baseline.context
        or ctx.dataset != schema.fingerprint
        or schema.rows != len(run.source_rows)
        or baseline.target != augmented.target
        or set(baseline.train_ids) & set(baseline.test_ids)
        or not set(baseline.train_ids + baseline.test_ids) <= set(range(len(run.source_rows)))
    ):
        raise ValueError("The saved derived table and predictive memberships disagree.")
