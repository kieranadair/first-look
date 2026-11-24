"""A finite propose–validate–compute–synthesize loop over existing analysis artifacts."""

from __future__ import annotations

import re
import json

from firstlook.challenges import challenge, eligible
from firstlook.contracts import EvidencePacket, HypothesisProposal, clean, digest
from firstlook.discovery import Investigation, analyze, plan_for, validate_plan
from firstlook.ingest import Dataset
from firstlook.semantics import dimensions
from firstlook.providers.base import ProviderError
from firstlook.visualization.review_assets import render_asset
from firstlook.recording_process import compact_packet
from firstlook.semantic.planner import semantic_packet


def prioritize(inv: Investigation, jev, dataset: Dataset | None = None) -> None:
    if dataset is not None and hasattr(jev, "judge"):
        from firstlook.recommendations import prioritize_typed

        prioritize_typed(inv, jev, dataset)
        return
    task_plans = {}
    if dataset is not None:
        from firstlook.exploration import perspective_coverage

        inv.coverage = perspective_coverage(dataset, inv)
        from firstlook.semantics import measures

        nums = sorted(measures(dataset), key=lambda f: f != inv.context.focus)
        focus = nums[0] if nums else None
        if (
            focus
            and dataset.frame.loc[inv.context.row_ids, focus].notna().any()
            and not any(r.plan.operation == "ecdf" and r.plan.fields == [focus] for r in inv.results.values())
        ):
            candidate = plan_for(
                inv.context, "ecdf", [focus], "Inspect the cumulative distribution of " + dataset.label(focus)
            )
            try:
                validate_plan(dataset, inv.context, candidate)
                task_plans["task:" + candidate.id] = candidate
            except ValueError:
                pass
    options = {f.id: f.title for f in inv.findings[:12]}
    options.update({key: p.question for key, p in task_plans.items()})
    options["none"] = "No view is useful for the stated focus"
    state = {
        "focus": inv.context.focus,
        "perspective_coverage": inv.coverage,
        "recording_process": compact_packet(dataset, inv.context) if dataset is not None else {},
        "selection_policy": "Eligible tasks only; prefer complementary evidence over redundant winners",
        "additional_tasks": [
            {
                "id": key,
                "operation": p.operation,
                "fields": p.fields,
                "question": p.question,
                "cost": "One bounded local distribution; no paid request",
            }
            for key, p in task_plans.items()
        ],
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
    if record.accepted and record.choice in task_plans:
        assert dataset is not None
        result, finding = analyze(dataset, inv.context, task_plans[record.choice])
        companion = next(
            (
                r
                for r in inv.results.values()
                if r.plan.operation == "distribution" and r.plan.fields == result.plan.fields
            ),
            None,
        )
        inv.add_view(result, finding)
        if companion and companion.id in inv.results:
            inv.related_views[result.id] = {
                "companion": companion.id,
                "intent": "Cumulative shape beside counts of the same source measure",
            }
        inv.semantic_decisions.append(
            {"stage": "task_priority", "task": record.choice, "computed_result": result.id}
        )
        inv.coverage = perspective_coverage(dataset, inv)
    elif record.accepted:
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
    if proposal.operation == "recording_process" and any(
        c.operation == "recording_process" for c in inv.challenges
    ):
        return False, "An existing recording-process check already covers this source context"
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
    from firstlook.exploration import display_result

    pair = next(
        (
            (primary, link["companion"])
            for primary, link in inv.related_views.items()
            if primary in inv.results and link["companion"] in inv.results
        ),
        None,
    )
    ordered = list(inv.findings)
    if pair:
        ordered.sort(key=lambda f: 0 if f.result_id == pair[0] else 1 if f.result_id == pair[1] else 2)
    for f in ordered[:6]:
        result = display_result(inv, f.result_id)
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
                "perspective_coverage": inv.coverage,
                "recording_process": compact_packet(dataset, inv.context) if dataset is not None else {},
                "models": [
                    {
                        "id": m.id,
                        "target": m.target,
                        "provider": m.provider,
                        "split": m.split,
                        "train_rows": len(m.train_ids),
                        "heldout_rows": len(m.test_ids),
                        "baseline_metrics": m.metrics,
                        "task_definition": m.parameters.get("task_definition"),
                        "readiness": {
                            k: v
                            for k, v in m.parameters.get("readiness", {}).items()
                            if k not in {"train_ids", "test_ids"}
                        },
                        "warnings": m.warnings,
                    }
                    for m in inv.model_runs[-1:]
                ],
            }
        ),
        allowed_operations=[
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
    if jev and accepted and hasattr(jev, "judge"):
        from firstlook.recommendations import rank_proposals

        try:
            accepted, ranking = rank_proposals(
                accepted,
                inv.goal or "Challenge the supplied interpretations with complementary eligible evidence.",
                inv.context.id,
                jev,
                {f.id: inv.results[f.result_id].support for f in inv.findings},
            )
            if ranking:
                inv.judgments.append(ranking)
        except ProviderError as exc:
            inv.terra["ranking_note"] = str(exc)
    elif jev and accepted:
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
    from firstlook.claim_review import evidence_items, review_synthesis

    audit = review_synthesis(
        synthesis, evidence_items(inv), inv.context.id, jev if hasattr(jev, "judge") else None
    )
    synthesis.interpretation = audit["display_text"]
    if audit["record"]:
        from firstlook.judgments import JudgmentBatch

        inv.judgments.append(JudgmentBatch.model_validate(audit["record"]))
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
        "claim_review": audit,
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


def review_comparison(
    dataset, bundle, terra, jev=None, visual=True, progress=lambda _: None, cancelled=lambda: False
):
    """One bounded review of coherent companions, with checks in each child's own context."""
    from firstlook.comparison import validate_bundle

    validate_bundle(bundle, dataset)
    assets, images, views, children = [], [], [], {}
    for view in bundle.views:
        child = Investigation(view.context, findings=[view.finding], results={view.result.id: view.result})
        children[view.finding.id] = child
        asset = render_asset(view.result, view.finding.chart, max_points=80)
        assets.append(clean(asset.manifest))
        if visual:
            images.append(asset.png)
        views.append(
            {
                "id": view.finding.id,
                "role": view.role,
                "context": view.context.id,
                "question": view.finding.title,
                "plotting_data": clean(asset.records),
                "metrics": view.result.metrics,
                "definition": view.result.metadata.get("definition"),
                "support": view.result.support,
                "missing": view.result.missing,
                "eligible_checks": [
                    op
                    for op in eligible(dataset, child, view.finding)
                    if op not in {"extremes", "resampling"}
                ],
                "limitations": view.finding.limitations,
            }
        )
    allowed = sorted({op for v in views for op in v["eligible_checks"]} | {"none"})
    packet = EvidencePacket(
        context=bundle.spec.selection.base.id,
        focus=bundle.spec.selection.base.focus,
        fields=[{"id": f.id, "name": f.name, "role": f.role.value} for f in dataset.record.fields],
        findings=views,
        assets=assets,
        allowed_operations=allowed,
        metadata=clean(
            {
                "task": "Compare these related views. Explain alternative hypotheses; propose only an eligible check or abstain.",
                "reference": bundle.spec.reference,
                "denominator": bundle.spec.denominator,
                "selection_policy": bundle.spec.selection.policy,
                "selected_rows": len(bundle.spec.selection.rows),
                "reference_rows": len(bundle.spec.reference_rows),
                "row_overlap": bundle.spec.row_overlap,
                "entity_overlap": bundle.spec.entity_overlap,
                "quantile_or_metric_differences": bundle.summary,
                "shared_domains": bundle.manifest.domains,
                "exclusions": bundle.exclusions,
                "model_slice": {
                    k: ({a: b for a, b in v.items() if a != "row_ids"} if isinstance(v, dict) else v)
                    for k, v in bundle.model_slice.items()
                },
            }
        ),
    )
    progress("Reviewing the selected and reference evidence together")
    batch = terra.propose(packet, images)
    accepted, log = [], []
    for proposal in batch.proposals:
        child = children.get(proposal.finding_id)
        valid, reason = (
            valid_proposal(dataset, child, proposal) if child else (False, "Unknown child evidence")
        )
        permitted = next((v["eligible_checks"] for v in views if v["id"] == proposal.finding_id), [])
        valid = valid and proposal.operation in permitted
        log.append({"proposal": proposal.model_dump(), "accepted": valid, "reason": reason})
        if valid and (proposal.finding_id, proposal.operation) not in {
            (p.finding_id, p.operation) for p in accepted
        }:
            accepted.append(proposal)
    typed_records = []
    if jev and accepted and hasattr(jev, "judge"):
        from firstlook.recommendations import rank_proposals

        accepted, ranking = rank_proposals(
            accepted,
            "Compare the selected and reference populations using complementary eligible checks.",
            bundle.spec.selection.base.id,
            jev,
            {v.finding.id: v.result.support for v in bundle.views},
        )
        if ranking:
            typed_records.append(ranking.model_dump(mode="json"))
    elif jev and accepted:
        options = {str(i): p.question for i, p in enumerate(accepted)} | {
            "none": "No further comparison check is useful"
        }
        decision = jev.choose(
            {"comparison": packet.metadata, "proposals": [p.model_dump() for p in accepted]},
            options,
            "Prefer a complementary executable check; abstain rather than repeat evidence. Preference is not truth.",
        )
        bundle.decisions.append(decision)
        if decision.choice == "none":
            accepted = []
        elif decision.accepted:
            chosen = accepted[int(decision.choice)]
            accepted = [chosen] + [p for p in accepted if p != chosen]
    for proposal in accepted[:2]:
        if cancelled():
            return bundle
        child = children[proposal.finding_id]
        finding = child.findings[0]
        additional = [f for f in proposal.fields if f not in child.results[finding.result_id].plan.fields]
        group = additional[0] if additional and proposal.operation in {"subgroup", "missingness"} else None
        bundle.checks.append(challenge(dataset, child, finding, proposal.operation, group))
    synthesis = terra.synthesize(
        {
            "evidence": packet.model_dump(mode="json"),
            "checks": [
                {
                    "id": c.id,
                    "summary": c.summary,
                    "status": c.status,
                    "metrics": c.result.metrics if c.result else {},
                }
                for c in bundle.checks
            ],
            "task": "Connect the views and checks; keep causes as hypotheses; no generated numerical assertions.",
        }
    )
    known = {v.finding.id for v in bundle.views} | {c.id for c in bundle.checks}
    if not set(synthesis.evidence_ids) <= known:
        raise ProviderError("Comparison interpretation cited unknown evidence.")
    from firstlook.claim_review import review_synthesis

    items = {
        v.finding.id: {
            "context": v.result.plan.context,
            "observation": v.finding.observation,
            "scope": {
                "support": v.result.support,
                "missing": v.result.missing,
                "reference": bundle.spec.reference,
                "denominator": bundle.spec.denominator,
            },
            "checks": [
                {"operation": c.operation, "status": c.status, "summary": c.summary}
                for c in bundle.checks
                if c.parent_id == v.finding.id
            ],
        }
        for v in bundle.views
    }
    items.update(
        {
            c.id: {
                "context": bundle.spec.selection.base.id,
                "status": c.status,
                "observation": c.summary,
                "operation": c.operation,
            }
            for c in bundle.checks
        }
    )
    audit = review_synthesis(
        synthesis, items, bundle.spec.selection.base.id, jev if hasattr(jev, "judge") else None
    )
    synthesis.interpretation = audit["display_text"]
    if audit["record"]:
        typed_records.append(audit["record"])
    if re.search(
        r"\b\d+(?:[.,]\d+)?%?\b|\b(caused|causes|proves|statistically significant)\b",
        synthesis.interpretation,
        re.I,
    ):
        synthesis.interpretation = "The proposed interpretation contained an unverified number or causal assertion. Refer to computed differences and completed checks."
    bundle.interpretation = {
        "synthesis": synthesis.model_dump(mode="json"),
        "claim_review": audit,
        "judgments": typed_records,
        "proposals": log,
        "packet": packet.model_dump(mode="json"),
        "provider_records": terra.records,
    }
    validate_bundle(bundle, dataset)
    return bundle
