"""Session-scoped workspace; widget state is not the analytical record."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from firstlook.contracts import ModelRun
from firstlook.discovery import Investigation
from firstlook.ingest import Dataset


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

    def context(self):
        if self.dataset is None:
            raise ValueError("Load a dataset first.")
        return self.dataset.context(self.rows, self.focus, self.assumption)

    def invalidate(self):
        self.investigation, self.model = None, None
        self.model_count = 0
        self.followups = 0
        self.inspect_id = self.challenge_id = None

    def load(self, dataset: Dataset):
        from firstlook.profiling import profile

        self.dataset = dataset
        self.profile = profile(dataset)
        self.focus, self.rows = None, None
        self.assumption = "unknown"
        self.invalidate()
        self.pins = []
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
