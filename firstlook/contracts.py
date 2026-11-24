"""Versioned, JSON-safe boundaries between analysis, models and presentation."""

from __future__ import annotations

import hashlib
import json
from functools import cached_property
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

import numpy as np
import pandas as pd
from firstlook.semantic_contracts import SemanticModel, MetadataProposal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return clean(value.item())
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(clean(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()[:24]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1


class Role(StrEnum):
    MEASURE = "measure"
    CATEGORY = "category"
    ORDINAL = "ordinal"
    TIME = "timestamp"
    ID = "identifier"
    TEXT = "text"
    BOOL = "boolean"
    UNKNOWN = "unknown"


class FieldSpec(Contract):
    id: str
    name: str
    position: int
    physical_type: str
    role: Role
    proposed_role: Role
    unit: str = ""
    order: list[str] = Field(default_factory=list)
    excluded: bool = False
    confirmed: bool = False
    evidence: str = ""
    parse_failures: int = 0


class DatasetRecord(Contract):
    fingerprint: str
    name: str
    rows: int
    columns: int
    fields: list[FieldSpec]
    source: str = "Uploaded file"
    description: str = ""
    parser: dict[str, JsonValue] = Field(default_factory=dict)
    semantic_model: SemanticModel | None = None
    source_profile: dict[str, JsonValue] = Field(default_factory=dict)


class AnalysisContext(Contract):
    dataset: str
    semantics: str
    row_ids: list[int]
    focus: str | None = None
    assumption: str = "unknown"

    @cached_property
    def id(self) -> str:
        return digest(self.model_dump())


class AnalysisPlan(Contract):
    id: str
    operation: str
    fields: list[str]
    context: str
    question: str
    params: dict[str, JsonValue] = Field(default_factory=dict)


class ResultArtifact(Contract):
    id: str
    plan: AnalysisPlan
    records: list[dict[str, Any]]
    metrics: dict[str, Any] = Field(default_factory=dict)
    support: int
    missing: int = 0
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def json_values(self) -> ResultArtifact:
        json.dumps([self.records, self.metrics, self.metadata], allow_nan=False)
        return self

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)


class ChartSpec(Contract):
    id: str
    result_id: str
    context: str
    template: Literal[
        "bar",
        "dot",
        "histogram",
        "frequency_polygon",
        "ecdf",
        "scatter",
        "box",
        "line",
        "heatmap",
        "density",
        "facet",
        "quantile_difference",
        "treemap",
    ]
    x_label: str
    y_label: str
    units: str = ""
    scale: Literal["linear", "log"] = "linear"
    zero_baseline: bool = False
    value_field: Literal["value", "amount"] = "value"
    rules: list[str] = Field(default_factory=list)
    alt: str


class Finding(Contract):
    id: str
    title: str
    observation: str
    result_id: str
    chart: ChartSpec
    family: str
    score: float
    claim_type: Literal["descriptive", "model-derived"] = "descriptive"
    limitations: list[str] = Field(default_factory=list)


class ChallengeResult(Contract):
    id: str
    parent_id: str
    operation: str
    status: Literal["changed", "similar", "insufficient", "not_checked"]
    summary: str
    result: ResultArtifact | None = None
    chart: ChartSpec | None = None


class DecisionRecord(Contract):
    provider: str
    requested_model: str
    resolved_model: str | None = None
    state_hash: str
    options: list[str]
    choice: str | None
    probabilities: dict[str, float] = Field(default_factory=dict)
    accepted: bool
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    note: str = ""
    state: dict[str, JsonValue] = Field(default_factory=dict)
    criteria: dict[str, str] = Field(default_factory=dict)
    instructions: str = ""

    @model_validator(mode="after")
    def distribution(self) -> DecisionRecord:
        if self.probabilities:
            if set(self.probabilities) != set(self.options):
                raise ValueError("Probability identities do not match the supplied alternatives.")
            if any(v < 0 or v > 1 for v in self.probabilities.values()):
                raise ValueError("Invalid probability.")
            if abs(sum(self.probabilities.values()) - 1) > 0.01:
                raise ValueError("Probabilities must sum to one.")
        if self.choice is not None and self.choice not in self.options:
            raise ValueError("Unknown decision option.")
        return self


class ModelRun(Contract):
    id: str
    context: str
    target: str
    predictors: list[str]
    task: Literal["regression", "classification"]
    split: str
    train_ids: list[int]
    test_ids: list[int]
    metrics: dict[str, dict[str, float]]
    predictions: list[dict[str, JsonValue]]
    warnings: list[str] = Field(default_factory=list)
    excluded: dict[str, str] = Field(default_factory=dict)
    provider: str
    model_record: dict[str, JsonValue] = Field(default_factory=dict)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class HypothesisProposal(Contract):
    question: str = Field(max_length=500)
    operation: Literal[
        "recording_process",
        "subgroup",
        "extremes",
        "rank",
        "distribution",
        "missingness",
        "quantile_bin_summary",
        "residual_spread_by_bin",
        "semantic_reconciliation",
        "semantic_unit",
        "semantic_denominator",
        "semantic_gaps",
        "semantic_time_aggregation",
        "group_shape",
        "density",
        "influence",
        "binning",
        "none",
    ]
    finding_id: str
    fields: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(max_length=1000)


class ProposalBatch(Contract):
    proposals: list[HypothesisProposal] = Field(default_factory=list, max_length=3)
    abstain_reason: str = Field(default="", max_length=1000)


class SemanticSuggestion(Contract):
    field_id: str
    role: Role
    reason: str = Field(max_length=600)
    clarification: str = Field(default="", max_length=300)
    ordered_levels: list[str] = Field(default_factory=list, max_length=50)


class SemanticReview(Contract):
    metadata_proposals: list[MetadataProposal] = Field(default_factory=list, max_length=12)
    suggestions: list[SemanticSuggestion] = Field(default_factory=list, max_length=12)
    dataset_note: str = Field(default="", max_length=1000)


class NarrativeClaim(Contract):
    text: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class NarrativeSynthesis(Contract):
    interpretation: str = Field(max_length=4000)
    evidence_ids: list[str] = Field(max_length=20)
    next_questions: list[str] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    claims: list[NarrativeClaim] = Field(default_factory=list, max_length=6)


class EvidencePacket(Contract):
    context: str
    focus: str | None
    fields: list[dict[str, JsonValue]]
    findings: list[dict[str, JsonValue]]
    assets: list[dict[str, JsonValue]]
    allowed_operations: list[str]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceRelation(Contract):
    source_id: str
    target_id: str
    relation: Literal["qualifies", "changed_under_check", "similar_under_check", "unresolved"]
