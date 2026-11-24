"""Purpose and time-of-knowledge contracts; unknown business facts stay unknown."""

from __future__ import annotations

from typing import Literal
import pandas as pd
from pydantic import Field, model_validator

from firstlook.contracts import Contract, Role, digest
from firstlook.semantic.model import get_model, commit_model

TASK_POLICY = "2026-11-24.2"


class TaskDefinition(Contract):
    dataset: str
    question: str = Field(default="Explore the recorded population", min_length=1, max_length=1000)
    purpose: Literal["descriptive", "diagnostic", "prediction"] = "descriptive"
    unit: str = Field(default="Recorded row", max_length=200)
    population: str = Field(default="The explicitly selected source population", max_length=600)
    target: str | None = None
    decision_time: str = Field(default="Not specified", max_length=300)
    anchor_field: str | None = None
    outcome_known_field: str | None = None
    horizon_days: int = Field(default=0, ge=0, le=365)
    complete_through: str = Field(default="", max_length=40)
    primary_metric: Literal["auto", "MAE", "RMSE", "Balanced accuracy", "Macro F1", "Log loss"] = "auto"

    @model_validator(mode="after")
    def valid_task(self):
        if self.purpose == "prediction" and not self.target:
            raise ValueError("A prospective task needs a recorded target or an Event lab recipe.")
        if (
            self.purpose == "prediction"
            and not self.anchor_field
            and self.decision_time.strip() in {"", "Not specified"}
        ):
            raise ValueError(
                "Define when a prospective prediction would be made, or select an anchor timestamp."
            )
        if self.complete_through:
            pd.Timestamp(self.complete_through)
        if self.horizon_days and (not self.anchor_field or not self.complete_through):
            raise ValueError(
                "A forward horizon requires an anchor timestamp and a declared complete-through date."
            )
        return self

    @property
    def id(self):
        return digest(self.model_dump())


class AvailabilityRule(Contract):
    field: str
    status: Literal["unreviewed", "known_at_anchor", "after_timestamp", "unavailable"] = "unreviewed"
    timestamp: str | None = None
    lag_hours: float = Field(default=0, ge=0, le=8760)
    mutable: bool = False
    history_available: bool = False
    evidence: str = Field(default="", max_length=1200)
    basis: str = Field(default="", max_length=64)
    timestamp_role: Literal["unspecified", "event", "recorded", "known", "scheduled"] = "unspecified"

    @model_validator(mode="after")
    def valid_rule(self):
        if self.status == "after_timestamp" and not self.timestamp:
            raise ValueError("Timestamp-based availability needs its timestamp field.")
        return self


def current_task(dataset):
    raw = get_model(dataset).search.get("analytical_task")
    return TaskDefinition.model_validate(raw) if raw else TaskDefinition(dataset=dataset.record.fingerprint)


def availability_rules(dataset):
    raw = get_model(dataset).search.get("availability", {})
    if not isinstance(raw, dict):
        raise ValueError("Invalid availability declarations.")
    return {fid: AvailabilityRule.model_validate(value) for fid, value in raw.items()}


def validate_task_metadata(dataset, model):
    fields = {f.id for f in dataset.record.fields}
    task_raw = model.search.get("analytical_task")
    if task_raw:
        task = TaskDefinition.model_validate(task_raw)
        if task.dataset != dataset.record.fingerprint:
            raise ValueError("Task definition belongs to a different dataset.")
        if task.target and task.target not in fields:
            raise ValueError("Task target is unknown.")
        for fid in [task.anchor_field, task.outcome_known_field]:
            if fid and (fid not in fields or dataset.field(fid).role != Role.TIME):
                raise ValueError("Task timing requires a parsed timestamp field.")
    raw_rules = model.search.get("availability", {})
    if not isinstance(raw_rules, dict) or len(raw_rules) > 80:
        raise ValueError("Invalid availability declaration collection.")
    for fid, raw in raw_rules.items():
        rule = AvailabilityRule.model_validate(raw)
        if rule.field != fid or fid not in fields:
            raise ValueError("Availability refers to an unknown field.")
        if rule.timestamp_role != "unspecified" and dataset.field(fid).role != Role.TIME:
            raise ValueError("Timestamp roles apply only to parsed timestamp fields.")
        if rule.timestamp and (
            rule.timestamp not in fields or dataset.field(rule.timestamp).role != Role.TIME
        ):
            raise ValueError("Availability requires a parsed timestamp reference.")


def save_task(dataset, task):
    candidate = get_model(dataset).model_copy(deep=True)
    candidate.search["analytical_task"] = task.model_dump(mode="json")
    validate_task_metadata(dataset, candidate)
    commit_model(dataset, candidate, "table", "analytical_task", task.model_dump(mode="json"))


def save_availability(dataset, rule):
    if rule.status == "known_at_anchor":
        rule = rule.model_copy(update={"basis": availability_basis(current_task(dataset))})
    candidate = get_model(dataset).model_copy(deep=True)
    existing = candidate.search.get("availability", {})
    if not isinstance(existing, dict):
        raise ValueError("Invalid availability declarations.")
    rules = dict(existing)
    rules[rule.field] = rule.model_dump(mode="json")
    candidate.search["availability"] = rules
    validate_task_metadata(dataset, candidate)
    commit_model(dataset, candidate, rule.field, "availability", rule.model_dump(mode="json"))


def resolved_task(dataset, target):
    task = current_task(dataset)
    if task.purpose == "prediction" and task.target != target:
        raise ValueError(
            "The chosen target differs from the declared prospective task. Edit the task in Meaning."
        )
    return task.model_copy(
        update={"target": target, "purpose": "diagnostic" if task.purpose == "descriptive" else task.purpose}
    )


def availability_basis(task):
    return digest({"decision_time": task.decision_time, "anchor_field": task.anchor_field})


def availability_decision(dataset, fid, frame, task=None):
    task = task or current_task(dataset)
    rule = availability_rules(dataset).get(fid, AvailabilityRule(field=fid))
    if not get_model(dataset).meaning(fid).available_at_prediction or rule.status == "unavailable":
        return "excluded", "Declared unavailable at prediction time"
    if rule.mutable and not rule.history_available:
        return (
            "excluded" if task.purpose == "prediction" else "assumption"
        ), "Latest mutable values have no declared historical versions"
    if rule.status == "known_at_anchor":
        if rule.basis != availability_basis(task):
            return (
                "excluded" if task.purpose == "prediction" else "assumption"
            ), "The availability declaration has a different decision-time basis; review it for this task"
        return "allowed", "Declared known at the task's decision time"
    if rule.status == "after_timestamp":
        if not task.anchor_field:
            return (
                "excluded" if task.purpose == "prediction" else "assumption"
            ), "No anchor field to evaluate availability"
        anchor = pd.to_datetime(frame[task.anchor_field], utc=True, errors="coerce")
        known = pd.to_datetime(frame[rule.timestamp], utc=True, errors="coerce") + pd.Timedelta(
            rule.lag_hours, unit="h"
        )
        present = frame[fid].notna()
        late = int((present & known.gt(anchor)).sum())
        unknown = int((present & (known.isna() | anchor.isna())).sum())
        if late or unknown:
            return (
                "excluded",
                f"Availability later than anchor on {late} rows; timing unknown on {unknown}. Whole predictor excluded consistently",
            )
        return "allowed", "All recorded values are available by their row's anchor"
    return (
        "excluded" if task.purpose == "prediction" else "assumption"
    ), "Prediction-time availability is unreviewed"


def task_packet(dataset):
    task = current_task(dataset)
    return {
        "policy": TASK_POLICY,
        "definition": task.model_dump(mode="json"),
        "id": task.id,
        "availability": [r.model_dump(mode="json") for r in availability_rules(dataset).values()],
        "boundary": "Population descriptions document intent, not executable filters. Actual row membership remains authoritative. Timing and collection facts require explicit declarations.",
    }
