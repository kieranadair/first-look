"""Portable reviewed definitions. Data-dependent facts and timing attestations never transfer."""

import pandas as pd
from pydantic import Field, model_validator

from firstlook.contracts import Contract, clean, digest
from firstlook.preparation import build_preparation, link_dependencies, make_change
from firstlook.semantic.model import get_model
from firstlook.semantic.profile import inspect_relationship
from firstlook.semantic_contracts import FieldMeaning, Entity, Metric, Relationship


class SemanticTemplate(Contract):
    format: str = "first-look-semantic-template-1"
    name: str = Field(min_length=1, max_length=150)
    fields: list[dict[str, str]] = Field(max_length=80)
    declarations: list[dict] = Field(max_length=140)

    @model_validator(mode="after")
    def valid_declarations(self):
        seen = set()
        for declaration in self.declarations:
            if (
                set(declaration) != {"kind", "subject", "payload"}
                or not isinstance(declaration["kind"], str)
                or not isinstance(declaration["subject"], str)
                or not isinstance(declaration["payload"], dict)
            ):
                raise ValueError("Invalid template declaration.")
            key = (declaration["kind"], declaration["subject"])
            if key in seen:
                raise ValueError("Template declarations must be unique.")
            seen.add(key)
        return self


def physical_family(series):
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    return "text"


def export_template(dataset, name="Reusable analytical definitions"):
    model = get_model(dataset)
    declarations = []
    for meaning in model.meanings:
        if meaning.confirmed:
            payload = meaning.model_dump(mode="json")
            payload["available_at_prediction"] = True
            payload["composition"] = None
            declarations.append({"kind": "quantity", "subject": meaning.field, "payload": payload})
    for f in dataset.record.fields:
        if f.confirmed:
            declarations.append(
                {
                    "kind": "role",
                    "subject": f.id,
                    "payload": {"role": f.role.value, "order": f.order, "excluded": f.excluded},
                }
            )
    for entity in model.entities:
        if entity.confirmed:
            declarations.append(
                {
                    "kind": "entity",
                    "subject": entity.id,
                    "payload": {"id": entity.id, "label": entity.label, "keys": entity.keys},
                }
            )
    if model.grain_confirmed:
        declarations.append(
            {
                "kind": "grain",
                "subject": "table",
                "payload": {"description": model.grain, "entity": model.grain_entity},
            }
        )
    for metric in model.metrics:
        if (
            metric.confirmed
            and metric.aggregation not in {"snapshot_last", "delta"}
            and not metric.time_policy
        ):
            declarations.append(
                {"kind": "metric", "subject": metric.id, "payload": metric.model_dump(mode="json")}
            )
    for rel in model.relationships:
        if rel.confirmed:
            declarations.append(
                {
                    "kind": "relationship",
                    "subject": rel.id,
                    "payload": {
                        "child": rel.child,
                        "parent": rel.parent,
                        "within": rel.within,
                        "relation": rel.relation,
                    },
                }
            )
    referenced = {f.id for f in dataset.record.fields}
    template = SemanticTemplate(
        name=name,
        fields=[
            {"ref": f.id, "name": f.name, "family": physical_family(dataset.frame[f.id])}
            for f in dataset.record.fields
            if f.id in referenced
        ],
        declarations=declarations[:140],
    )
    return template.model_dump_json(indent=2).encode()


def import_template(dataset, blob, goal=""):
    if len(blob) > 2_000_000:
        raise ValueError("Semantic templates are limited to 2 MB.")
    template = SemanticTemplate.model_validate_json(blob)
    if template.format != "first-look-semantic-template-1":
        raise ValueError("Unsupported semantic template format.")
    if len({f.get("ref") for f in template.fields}) != len(template.fields) or any(
        set(f) != {"ref", "name", "family"} for f in template.fields
    ):
        raise ValueError("Template fields require unique references, names and physical families.")
    draft = build_preparation(dataset, goal)
    draft.summary = (
        "Review reused definitions from “"
        + template.name
        + "”. Matching uses exact unambiguous names and physical families; structural evidence is recomputed. Coverage and availability attestations are excluded."
    )
    mapping, issues = {}, []
    names = [f["name"] for f in template.fields]
    for field in template.fields:
        matches = [f for f in dataset.record.fields if f.name == field["name"]]
        if len(matches) != 1 or names.count(field["name"]) != 1:
            issues.append("Missing or ambiguous field: " + field["name"])
        elif physical_family(dataset.frame[matches[0].id]) != field["family"]:
            issues.append("Physical type changed: " + field["name"])
        else:
            mapping[field["ref"]] = matches[0].id
    # Entity and metric identities are remapped separately from physical column positions.
    model = get_model(dataset)
    for d in template.declarations:
        if d.get("kind") == "entity":
            keys = [mapping.get(k) for k in d["payload"].get("keys", [])]
            if keys and all(keys):
                existing = next((e for e in model.entities if e.keys == keys), None)
                mapping[d["subject"]] = existing.id if existing else "e_reuse_" + digest(keys)
        elif d.get("kind") == "metric":
            mapping[d["subject"]] = "m_reuse_" + digest([template.name, d["subject"]])

    def mapped(value):
        if isinstance(value, str):
            return mapping.get(value, value)
        if isinstance(value, list):
            return [mapped(v) for v in value]
        if isinstance(value, dict):
            # Only identity-bearing properties may be rewritten; labels and units stay literal.
            identities = {
                "id",
                "field",
                "keys",
                "entity",
                "weight",
                "numerator",
                "denominator",
                "child",
                "parent",
                "within",
            }
            return {k: mapped(v) if k in identities else v for k, v in value.items()}
        return value

    # Preserve equivalent metric identities, including component references, across exports.
    from graphlib import TopologicalSorter, CycleError
    from firstlook.preparation import _metric_identity

    definitions = {d["subject"]: d["payload"] for d in template.declarations if d["kind"] == "metric"}
    graph = {
        mid: {p[k] for k in ["numerator", "denominator"] if p.get(k) in definitions}
        for mid, p in definitions.items()
    }
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ValueError("Template metric definitions cannot be circular.") from exc
    for mid in order:
        try:
            prototype = Metric.model_validate(mapped(definitions[mid]))
            existing = next(
                (m for m in model.metrics if _metric_identity(m) == _metric_identity(prototype)), None
            )
            if existing:
                mapping[mid] = existing.id
        except ValueError:
            continue
    changes = {c.id: c for c in draft.changes}
    for d in template.declarations:
        if set(d) != {"kind", "subject", "payload"}:
            raise ValueError("Invalid template declaration.")
        kind = d["kind"]
        if kind not in {"quantity", "role", "entity", "grain", "metric", "relationship"}:
            raise ValueError("Templates cannot transfer observation coverage or prediction availability.")
        p = mapped(d["payload"])
        subject = mapping.get(d["subject"], d["subject"])
        try:
            issue = ""
            original = d["payload"]
            required = [
                original.get(k)
                for k in ["field", "weight", "entity", "numerator", "denominator", "child", "parent"]
                if original.get(k)
            ]
            required += original.get("keys", []) + original.get("within", [])
            if any(ref not in mapping for ref in required):
                issues.append(
                    "Skipped a definition with a missing, ambiguous or changed field/reference: "
                    + str(d["subject"])
                )
                continue
            if kind == "quantity":
                if d["subject"] not in mapping:
                    continue
                p = FieldMeaning.model_validate(p).model_dump(mode="json")
                p["field"] = subject
                label = dataset.label(subject) + " · reused quantity meaning"
            elif kind == "role":
                if d["subject"] not in mapping:
                    continue
                label = dataset.label(subject) + " · reused field role/order"
            elif kind == "entity":
                if d["subject"] not in mapping or not set(p.get("keys", [])) <= set(dataset.frame):
                    continue
                p = Entity.model_validate(p).model_dump(mode="json")
                label = "Reused identity · " + p["label"]
            elif kind == "grain":
                if p.get("entity") and p["entity"] not in set(mapping.values()):
                    continue
                label = "Reused row meaning · " + str(p["description"])[:180]
            elif kind == "metric":
                if any(
                    p.get(k) and p[k] not in set(mapping.values())
                    for k in ["field", "weight", "entity", "numerator", "denominator"]
                ):
                    continue
                p = Metric.model_validate(p).model_dump(mode="json")
                label = "Reused metric · " + p["label"]
                if p.get("entity"):
                    old_entity = next(
                        (
                            e
                            for e in template.declarations
                            if e["kind"] == "entity" and mapping.get(e["subject"]) == p["entity"]
                        ),
                        None,
                    )
                    if old_entity and p.get("field"):
                        keys = mapped(old_entity["payload"])["keys"]
                        if dataset.frame.groupby(keys, dropna=False)[p["field"]].nunique(
                            dropna=False
                        ).max() > 1 and p["aggregation"] in {"sum", "mean", "median", "weighted_mean"}:
                            issue = "Values now vary within the declared value entity; this reused definition needs revision."
            else:
                if not {p.get("child"), p.get("parent"), *p.get("within", [])} <= set(dataset.frame):
                    continue
                actual = inspect_relationship(dataset, p["child"], p["parent"], p.get("within", []))
                if p["relation"] == "hierarchy" and (not actual.strict or not actual.complete):
                    issue = "New data violates the reused hierarchy. Review recorded exceptions in Meaning."
                p = Relationship.model_validate(
                    {**actual.model_dump(mode="json"), "relation": p["relation"]}
                ).model_dump(mode="json")
                subject = actual.id
                label = (
                    "Reused relationship · "
                    + dataset.label(actual.child)
                    + " → "
                    + dataset.label(actual.parent)
                )
            c = make_change(
                dataset,
                kind,
                subject,
                p,
                label,
                "Definition from an explicitly imported template; review its applicability to this upload.",
                "template",
                suggested=True,
            )
            c.issue = issue
            if c.before == c.payload:
                continue
            changes[c.id] = c
        except (ValueError, KeyError, StopIteration) as exc:
            issues.append("Skipped an incompatible template declaration: " + str(exc)[:180])
    draft.changes = list(changes.values())[:140]
    draft.errors = issues[:8]
    draft.telemetry["template"] = clean(
        {
            "name": template.name,
            "matched_fields": len([f for f in template.fields if f["ref"] in mapping]),
            "source_fields": len(template.fields),
            "drift": issues,
            "coverage_transferred": False,
            "availability_transferred": False,
        }
    )
    return link_dependencies(dataset, draft)
