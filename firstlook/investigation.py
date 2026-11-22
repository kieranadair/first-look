"""A finite propose–validate–compute–synthesize loop over existing analysis artifacts."""

from __future__ import annotations

import re
import json

from firstlook.challenges import challenge, eligible
from firstlook.contracts import EvidencePacket, HypothesisProposal, clean, digest
from firstlook.discovery import Investigation
from firstlook.ingest import Dataset
from firstlook.semantics import dimensions
from firstlook.providers.base import ProviderError
from firstlook.visualization.review_assets import render_asset
from firstlook.semantic.planner import semantic_packet


def prioritize(inv: Investigation, jev, dataset: Dataset | None = None) -> None:
    options = {f.id: f.title for f in inv.findings[:12]}
    options["none"] = "No view is useful for the stated focus"
    state = {
        "focus": inv.context.focus,
        "candidates": [
            {
                "id": f.id,
                "question": f.title,
                "metrics": inv.results[f.result_id].metrics,
                "support": inv.results[f.result_id].support,
                "limitations": f.limitations,
                "fields": inv.results[f.result_id].plan.fields,
                "axis_labels": {"x": f.chart.x_label, "y": f.chart.y_label},
            }
            for f in inv.findings[:12]
        ],
    }
    if dataset is not None:
        state["semantic_contract"] = semantic_packet(dataset, 8)
    record = jev.choose(state, options, "Choose the most useful next view given the focus and evidence.")
    inv.decisions.append(record)
    if record.accepted:
        inv.findings.sort(key=lambda f: f.id != record.choice)
    if dataset is not None:
        from firstlook.semantic.model import get_model

        questions = get_model(dataset).clarifications[:8]
        if questions:
            options = {q.id: q.question for q in questions}
            options["none"] = "No clarification is useful yet"
            record = jev.choose(
                {"focus": inv.context.focus, "questions": [q.model_dump(mode="json") for q in questions]},
                options,
                "Choose the clarification that unlocks the most useful valid analyses. Do not answer it or treat likelihood as truth.",
            )
            inv.decisions.append(record)
            if record.accepted:
                inv.semantic_decisions.append(
                    {
                        "stage": "clarification_priority",
                        "question": record.choice,
                        "provider": "jev",
                        "semantic_revision": get_model(dataset).revision,
                    }
                )


def valid_proposal(dataset: Dataset, inv: Investigation, proposal: HypothesisProposal) -> tuple[bool, str]:
    if proposal.operation == "none":
        return False, "Abstained"
    finding = next((f for f in inv.findings if f.id == proposal.finding_id), None)
    if finding is None or not set(proposal.fields).issubset(dataset.frame.columns):
        return False, "Unknown evidence or field identity"
    if proposal.operation not in eligible(dataset, inv, finding):
        return False, "Operation is ineligible for this evidence"
    additional = [f for f in proposal.fields if f not in inv.results[finding.result_id].plan.fields]
    if proposal.operation in {"subgroup", "missingness"}:
        if len(additional) > 1 or any(f not in dimensions(dataset) for f in additional):
            return False, "A group check requires one eligible grouping dimension"
    elif additional and proposal.operation != "residual_spread_by_bin":
        return False, "The proposed fields do not match the recorded analysis"
    if any(c.parent_id == finding.id and c.operation == proposal.operation for c in inv.challenges):
        return False, "An existing check already answers this proposal"
    return True, "Eligible"


def run_terra(
    dataset: Dataset,
    inv: Investigation,
    terra,
    jev=None,
    visual: bool = True,
    progress=lambda _: None,
    cancelled=lambda: False,
) -> dict:
    assets, images, views = [], [], []
    for f in inv.findings[:6]:
        result = inv.results[f.result_id]
        if len(assets) >= 3:
            break
        try:
            point_budget = min(
                600,
                max(30, int(len(result.records) * 10_000 / max(len(json.dumps(clean(result.records))), 1))),
            )
            asset = render_asset(result, f.chart, point_budget)
        except ValueError:
            continue
        records = clean(asset.records)
        view = {
            "id": f.id,
            "question": f.title,
            "observation": f.observation,
            "metrics": result.metrics,
            "plotting_data": records,
            "context": result.plan.context,
            "support": result.support,
            "limitations": f.limitations,
            "chart": f.chart.model_dump(mode="json"),
            "eligible_checks": eligible(dataset, inv, f),
            "definition": result.metadata.get("definition"),
            "completed_checks": [
                {"operation": c.operation, "status": c.status, "summary": c.summary}
                for c in inv.challenges
                if c.parent_id == f.id
            ],
        }
        # Keep both conditions exactly matched. Reduce complete views, never truncate JSON.
        candidate = views + [view]
        if len(str(candidate)) > 25_000:
            continue
        views.append(view)
        assets.append(clean(asset.manifest))
        if visual:
            images.append(asset.png)
    if not views:
        raise ProviderError("No supported, bounded evidence packet is available.")
    packet = EvidencePacket(
        context=inv.context.id,
        focus=inv.context.focus,
        fields=[
            {"id": f.id, "name": f.name, "role": f.role.value, "unit": f.unit} for f in dataset.record.fields
        ],
        findings=views,
        assets=assets,
        metadata=clean(
            {
                "description": dataset.record.description,
                "assumption": inv.context.assumption,
                "semantics_revision": inv.context.semantics,
                "active_rows": len(inv.context.row_ids),
                "remaining_checks": 2,
                "semantic_contract": semantic_packet(dataset, 8),
                "models": [
                    {
                        "id": m.id,
                        "target": m.target,
                        "provider": m.provider,
                        "split": m.split,
                        "train_rows": len(m.train_ids),
                        "heldout_rows": len(m.test_ids),
                        "baseline_metrics": m.metrics,
                        "warnings": m.warnings,
                    }
                    for m in inv.model_runs[-1:]
                ],
            }
        ),
        allowed_operations=[
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
            "none",
        ],
    )
    progress("Terra is proposing evidence-linked questions")
    inv.terra.update(
        packet=packet.model_dump(mode="json"), packet_hash=digest(packet.model_dump()), status="proposing"
    )
    batch = terra.propose(packet, images)
    log, accepted = [], []
    for p in batch.proposals:
        valid, reason = valid_proposal(dataset, inv, p)
        log.append({"proposal": p.model_dump(), "accepted": valid, "reason": reason})
        if valid:
            accepted.append(p)
    if jev and accepted:
        try:
            options = {str(i): p.question for i, p in enumerate(accepted)}
            options["none"] = "No additional check is useful"
            decision = jev.choose(
                {"proposals": [p.model_dump() for p in accepted]},
                options,
                "Choose the most useful eligible additional check.",
            )
            inv.decisions.append(decision)
            if decision.accepted:
                chosen = accepted[int(decision.choice)]
                accepted = [chosen] + [p for p in accepted if p != chosen]
            elif decision.choice == "none":
                accepted = []
        except ProviderError:
            pass
    new_checks = []
    for proposal in accepted[:2]:
        if cancelled():
            return {"status": "cancelled"}
        f = next(f for f in inv.findings if f.id == proposal.finding_id)
        progress("Computing: " + proposal.question)
        additional = [fid for fid in proposal.fields if fid not in inv.results[f.result_id].plan.fields]
        group = additional[0] if additional and proposal.operation in {"subgroup", "missingness"} else None
        check = challenge(dataset, inv, f, proposal.operation, group_field=group)
        inv.challenges.append(check)
        new_checks.append(check.model_dump(mode="json"))
    inv.terra.update(proposals=log, provider_records=terra.records, status="checks_completed")
    if cancelled():
        inv.terra["status"] = "cancelled"
        return inv.terra
    progress("Terra is reconciling the checked evidence")
    synthesis = terra.synthesize(
        {
            "evidence": packet.model_dump(mode="json"),
            "checks": [
                {
                    "id": c["id"],
                    "parent_id": c["parent_id"],
                    "operation": c["operation"],
                    "status": c["status"],
                    "summary": c["summary"],
                    "result": {k: c["result"][k] for k in ["id", "metrics", "support", "warnings"]}
                    if c["result"]
                    else None,
                }
                for c in new_checks
            ],
            "task": "Explain what remains an interpretation. Cite only supplied evidence IDs.",
        }
    )
    if re.search(
        r"\b\d+(?:[.,]\d+)?%?\b|\b(caused|causes|proves|statistically significant)\b",
        synthesis.interpretation,
        re.I,
    ):
        synthesis.interpretation = "The generated interpretation added an unverified quantity or causal assertion and was omitted. Use the measured observations and completed checks."
    ids = {f.id for f in inv.findings} | {c.id for c in inv.challenges}
    if not set(synthesis.evidence_ids).issubset(ids):
        raise ProviderError("Terra cited unknown evidence; its synthesis was rejected.")
    result = {
        "provider_note": inv.terra.get("provider_note", ""),
        "model_note": inv.terra.get("model_note", ""),
        "status": "completed",
        "packet": packet.model_dump(mode="json"),
        "packet_hash": digest(packet.model_dump()),
        "proposals": log,
        "synthesis": synthesis.model_dump(mode="json"),
        "provider_records": terra.records,
        "relations": [
            {
                "source_id": c["parent_id"],
                "target_id": c["id"],
                "relation": {"changed": "changed_under_check", "similar": "similar_under_check"}.get(
                    c["status"], "unresolved"
                ),
            }
            for c in new_checks
        ],
    }
    inv.terra = result
    return result
