"""Evidence-linked prose checks; model support is never numerical validation."""

from __future__ import annotations

import re
from typing import Any

from firstlook.contracts import digest
from firstlook.judgment_catalog import claim_specs

UNVERIFIED = re.compile(r"\b\d+(?:[.,]\d+)?%?\b|\b(caused|causes|proves|statistically significant)\b", re.I)


def evidence_items(inv):
    items = {}
    for f in inv.findings:
        r = inv.results[f.result_id]
        items[f.id] = {
            "context": r.plan.context,
            "observation": f.observation,
            "definition": r.plan.question,
            "operation": r.plan.operation,
            "support": r.support,
            "missing": r.missing,
            "limitations": f.limitations,
            "scope": r.metadata.get("analysis_scope", {}),
            "checks": [
                {"operation": c.operation, "status": c.status, "summary": c.summary}
                for c in inv.challenges
                if c.parent_id == f.id
            ],
        }
    for c in inv.challenges:
        items[c.id] = {
            "context": inv.context.id,
            "operation": c.operation,
            "status": c.status,
            "observation": c.summary,
            "parent_id": c.parent_id,
        }
    return items


def review_synthesis(synthesis, items, context, jev=None):
    from firstlook.providers.base import ProviderError

    original = synthesis.model_dump(mode="json")
    if not set(synthesis.evidence_ids) <= set(items):
        raise ProviderError("Terra cited unknown evidence; its synthesis was rejected.")
    if synthesis.claims:
        claims = [c.model_dump(mode="json") for c in synthesis.claims]
        if synthesis.interpretation.strip() != " ".join(c["text"] for c in claims).strip():
            raise ProviderError("Terra's interpretation and evidence-linked claim text disagree.")
    else:
        sentences = re.split(r"(?<=[.!?])\s+", synthesis.interpretation.strip())
        if len(sentences) > 6:
            raise ProviderError("The synthesis exceeds the six-claim review budget.")
        claims = [{"text": s, "evidence_ids": list(synthesis.evidence_ids)} for s in sentences if s]
    audited: list[dict[str, Any]] = []
    state, specs = {"claims": {}}, []
    for i, claim in enumerate(claims):
        ids = claim["evidence_ids"]
        if not set(ids) <= set(items):
            raise ProviderError("A claim cited unknown evidence.")
        reason = ""
        if not ids:
            reason = "No evidence was cited."
        elif UNVERIFIED.search(str(claim["text"])):
            reason = "An unverified numerical or causal assertion was omitted."
        elif any(items[k].get("status") in {"not_checked", "insufficient"} for k in ids):
            reason = "The claim cites an incomplete or insufficient check; it needs review."
        row = {
            "id": digest([context, claim]),
            **claim,
            "status": "flagged" if reason else "pending_review",
            "reason": reason or "Semantic support has not been reviewed by Jev.",
            "numerical_validation": "Generated numerical assertions are not accepted; Python results remain authoritative.",
        }
        audited.append(row)
        if reason:
            continue
        alias = "claim_" + str(i + 1)
        state["claims"][alias] = {"text": claim["text"], "evidence": {k: items[k] for k in ids}}
        specs += claim_specs(alias)
    batch, provider_note = None, ""
    if jev is not None and specs:
        try:
            batch = jev.judge(state, specs, context=context, purpose="Semantic claim and scope review")
            for i, row in enumerate(audited):
                if row["status"] != "pending_review":
                    continue
                alias = "claim_" + str(i + 1)
                answers = [batch.answers[alias + "_support"], batch.answers[alias + "_scope"]]
                row["status"] = (
                    "supported_by_model"
                    if all(a.status == "yes" for a in answers)
                    else "flagged"
                    if any(a.status == "no" for a in answers)
                    else "unresolved"
                )
                row["reason"] = {
                    "supported_by_model": "Jev found semantic support and matching scope; this is a model review signal, not proof.",
                    "flagged": "Jev found missing support or a scope mismatch; the claim is withheld pending review.",
                    "unresolved": "The evidence does not settle the semantic support or scope judgment.",
                }[row["status"]]
        except ProviderError as exc:
            provider_note = str(exc)
    displayed = [r["text"] for r in audited if r["status"] in {"pending_review", "supported_by_model"}]
    display = (
        " ".join(displayed)
        or "The generated interpretation was omitted or remains unresolved. Use the measured observations and completed checks."
    )
    return {
        "id": digest([context, original]),
        "context": context,
        "original": original,
        "claims": audited,
        "display_text": display,
        "record": batch.model_dump(mode="json") if batch else None,
        "provider_note": provider_note,
    }
