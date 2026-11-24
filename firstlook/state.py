"""Session-scoped workspace; widget state is not the analytical record."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from firstlook.contracts import ModelRun
from firstlook.discovery import Investigation
from firstlook.ingest import Dataset
from firstlook.exploration_contracts import CohortSelection, ComparisonBundle


@dataclass
class Workspace:
    owner: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    dataset: Dataset | None = None
    profile: dict = field(default_factory=dict)
    investigation: Investigation | None = None
    model: ModelRun | None = None
    focus: str | None = None
    rows: list[int] | None = None
    assumption: str = "unknown"
    pins: list[dict] = field(default_factory=list)
    job_id: str | None = None
    job_kind: str = ""
    job_context: str = ""
    message: str = ""
    inspect_id: str | None = None
    challenge_id: str | None = None
    replay: bool = False
    model_count: int = 0
    followups: int = 0
    semantic_review: dict = field(default_factory=dict)
    semantic_review_count: int = 0
    selection: CohortSelection | None = None
    comparison: ComparisonBundle | None = None
    comparisons: list[ComparisonBundle] = field(default_factory=list)
    cohort_revision: int = 0
    opened: set[str] = field(default_factory=set)
    job_revision: int = 0
    comparison_review_count: int = 0
    return_state: dict = field(default_factory=dict)
    explore_id: str | None = None
    question_review: dict = field(default_factory=dict)
    text_proposal: dict = field(default_factory=dict)
    text_runs: list[dict] = field(default_factory=list)
    text_run_count: int = 0
    text_proposal_count: int = 0
    text_model_count: int = 0
    note_review: dict = field(default_factory=dict)
    note_review_count: int = 0
    semantic_scenarios: list[dict] = field(default_factory=list)
    event_runs: list[dict] = field(default_factory=list)
    event_prepare_count: int = 0
    event_model_count: int = 0

    def context(self):
        if self.dataset is None:
            raise ValueError("Load a dataset first.")
        return self.dataset.context(self.rows, self.focus, self.assumption)

    def invalidate(self):
        self.investigation, self.model = None, None
        self.model_count = 0
        self.followups = 0
        self.inspect_id = self.challenge_id = None
        self.selection, self.comparison = None, None
        self.opened = set()
        self.cohort_revision += 1
        self.comparison_review_count = 0
        self.return_state = {}
        self.explore_id = None
        self.question_review, self.text_proposal, self.note_review = {}, {}, {}
        self.text_runs, self.semantic_scenarios = [], []
        self.text_run_count = self.text_proposal_count = self.text_model_count = self.note_review_count = 0
        self.event_runs = []
        self.event_prepare_count = self.event_model_count = 0

    def begin_filtered(self):
        if self.selection is None or self.selection.base.id != self.context().id:
            raise ValueError("Preview a cohort in the current reference first.")
        saved = {
            name: getattr(self, name)
            for name in [
                "rows",
                "focus",
                "assumption",
                "investigation",
                "model",
                "model_count",
                "followups",
                "comparisons",
                "comparison",
                "selection",
                "opened",
                "cohort_revision",
                "comparison_review_count",
                "question_review",
                "text_proposal",
                "text_runs",
                "text_run_count",
                "text_proposal_count",
                "text_model_count",
                "note_review",
                "note_review_count",
                "semantic_scenarios",
                "event_runs",
                "event_prepare_count",
                "event_model_count",
            ]
        }
        saved["context"] = self.context().id
        rows = list(self.selection.rows)
        self.rows = rows
        self.invalidate()
        self.return_state = saved

    def return_to_anchor(self):
        saved = self.return_state
        if not saved or self.dataset is None:
            raise ValueError("No anchored investigation is available.")
        if self.dataset.context(saved["rows"], saved["focus"], saved["assumption"]).id != saved["context"]:
            self.return_state = {}
            raise ValueError("The anchored meanings changed. Run a new investigation.")
        for name, value in saved.items():
            if name != "context":
                setattr(self, name, value)
        self.return_state = {}

    def bound_views(self):
        ids = {b.id for b in self.comparisons}
        if self.comparison:
            ids.add(self.comparison.id)
        allowance = max(1, 18 - 2 * len(ids))
        if self.investigation and len(self.investigation.findings) > allowance:
            self.investigation.findings = self.investigation.findings[:allowance]
            retained = {f.id for f in self.investigation.findings}
            results = {f.result_id for f in self.investigation.findings}
            self.investigation.results = {k: v for k, v in self.investigation.results.items() if k in results}
            self.investigation.challenges = [
                c for c in self.investigation.challenges if c.parent_id in retained
            ]
            self.investigation.related_views = {
                k: v
                for k, v in self.investigation.related_views.items()
                if k in results and v["companion"] in results
            }

    def load(self, dataset: Dataset):
        from firstlook.profiling import profile

        self.dataset = dataset
        self.profile = profile(dataset)
        self.focus, self.rows = None, None
        self.assumption = "unknown"
        self.invalidate()
        self.pins = []
        self.comparisons = []
        self.inspect_id = self.challenge_id = None
        self.replay = False
        self.semantic_review = {}
        self.semantic_review_count = 0


def pin(workspace: Workspace, finding_id: str) -> None:
    inv = workspace.investigation
    if inv is None:
        return
    f = next(f for f in inv.findings if f.id == finding_id)
    if any(p["finding"]["id"] == finding_id for p in workspace.pins):
        return
    workspace.pins.append(
        {
            "finding": f.model_dump(mode="json"),
            "result": inv.results[f.result_id].model_dump(mode="json"),
            "challenges": [c.model_dump(mode="json") for c in inv.challenges if c.parent_id == finding_id],
            "note": "",
            "context": inv.context.model_dump(mode="json"),
            "semantics": [field.model_dump(mode="json") for field in workspace.dataset.record.fields]
            if workspace.dataset
            else [],
            "semantic_contract": workspace.dataset.record.semantic_model.model_dump(mode="json")
            if workspace.dataset and workspace.dataset.record.semantic_model
            else None,
        }
    )
