"""Finite investigation tasks and explicit multi-context comparison boundaries."""

from typing import Literal

from pydantic import Field

from firstlook.contracts import (
    AnalysisContext,
    ChallengeResult,
    Contract,
    DecisionRecord,
    Finding,
    ResultArtifact,
    DatasetRecord,
    ModelRun,
    digest,
)


class ExplorationTask(Contract):
    family: str
    question: str
    fields: list[str]
    base_context: str
    operation: str
    recipe_version: int = 2
    budget: str = "bounded local catalog"


class PerspectiveCoverage(Contract):
    family: str
    status: Literal["available", "blocked", "outside_budget", "screened", "computed", "opened", "checked"]
    scope: str
    reason: str = ""
    screened: int = 0
    computed: int = 0
    opened: int = 0
    checked: int = 0
    outside_budget: int = 0


class AnalysisScope(Contract):
    context: str
    eligible_rows: int
    statistical_rows: int
    displayed_marks: int
    missing_rows: int = 0
    statistical_sample: bool = False
    display_sample: bool = False
    seed: int | None = None
    statistical_membership_hash: str = ""
    display_membership_hash: str = ""
    selection: str = "Explicit source members of displayed marks"


class ReferenceSpec(Contract):
    kind: Literal[
        "population", "remainder", "target", "empirical_range", "confidence_interval", "prediction_interval"
    ]
    label: str
    population: str
    method: str
    unit: str = ""


class CohortSelection(Contract):
    base: AnalysisContext
    source_result: str
    mapping_hash: str
    selected_rows: list[int]
    rows: list[int]
    policy: Literal["rows", "entities"] = "rows"
    entity: str | None = None
    revision: int
    selection_scope: str = "Displayed mark members only"

    @property
    def id(self) -> str:
        return digest(self.model_dump())


class ComparisonSpec(Contract):
    selection: CohortSelection
    reference: Literal["remainder", "whole"] = "remainder"
    denominator: Literal["cohort", "anchored"] = "cohort"
    allocation: Literal["anchored"] = "anchored"
    metric: str | None = None
    group_by: list[str] = Field(default_factory=list, max_length=1)
    measure: str | None = None
    operation: Literal["metric", "ecdf", "frequency"]
    reference_rows: list[int]
    entity_overlap: int | None = None
    row_overlap: int = 0


class ComparisonManifest(Contract):
    category_keys: list[str] = Field(default_factory=list)
    category_labels: list[str] = Field(default_factory=list)
    omitted_keys: list[str] = Field(default_factory=list)
    domains: dict[str, tuple[float, float]] = Field(default_factory=dict)
    colors: dict[str, str] = Field(default_factory=lambda: {"Selected": "#4169D8", "Reference": "#C67049"})
    quantile_grid: list[float] = Field(default_factory=lambda: [0.1, 0.25, 0.5, 0.75, 0.9])
    transformation: str = "Recorded metric; identity or explicitly supported fixed transform"
    approximation: str = "Statistics from source values; each display records its own approximation"


class ComparisonView(Contract):
    role: Literal["Selected", "Reference"]
    context: AnalysisContext
    result: ResultArtifact
    finding: Finding


class ComparisonBundle(Contract):
    id: str
    spec: ComparisonSpec
    manifest: ComparisonManifest
    views: list[ComparisonView] = Field(min_length=2, max_length=2)
    summary: list[dict] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    model_slice: dict = Field(default_factory=dict)
    interpretation: dict = Field(default_factory=dict)
    checks: list[ChallengeResult] = Field(default_factory=list, max_length=2)
    decisions: list[DecisionRecord] = Field(default_factory=list, max_length=2)
    dataset_record: DatasetRecord | None = None
    recorded_model: ModelRun | None = None
