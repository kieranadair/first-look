"""Portable, validated JSON artifacts. Importing a bundle never executes it."""

from __future__ import annotations

import hashlib
import io
import json
import platform
import stat
import zipfile
from typing import Any, cast
from importlib.metadata import PackageNotFoundError, version
from pathlib import PurePosixPath

from firstlook import __version__
from firstlook.contracts import (
    AnalysisContext,
    ChallengeResult,
    DatasetRecord,
    DecisionRecord,
    Finding,
    ModelRun,
    NarrativeSynthesis,
    ResultArtifact,
    clean,
    digest,
)
from firstlook.discovery import Investigation, analyze
from firstlook.ingest import Dataset, load_table
from firstlook.state import Workspace

MAX_EXPANDED = 100 * 1024**2
MAX_ENTRIES = 256


def json_bytes(value) -> bytes:
    return json.dumps(clean(value), indent=2, ensure_ascii=False, allow_nan=False).encode()


def environment() -> dict:
    versions = {}
    for name in [
        "streamlit",
        "pandas",
        "numpy",
        "scipy",
        "scikit-learn",
        "pydantic",
        "openai",
        "typesafe-sdk",
        "tabpfn-client",
        "matplotlib",
        "pint",
    ]:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "not installed"
    return {"python": platform.python_version(), "firstlook": __version__, "packages": versions}


def brief(workspace: Workspace) -> str:
    ds = workspace.dataset
    name = ds.record.name if ds else "Recorded investigation"
    lines = [
        f"# First Look · {name}",
        "",
        "An exploratory investigation, with recorded evidence and limitations.",
        "",
    ]
    if ds:
        lines += [f"Dataset fingerprint: {ds.record.fingerprint}", "", f"Source: {ds.record.source}", ""]
        if ds.record.semantic_model:
            model = ds.record.semantic_model
            lines += [
                "## Analytical meaning",
                "",
                model.grain,
                "",
                f"Semantic revision: {model.revision}",
                "",
                f"Open decisions: {len(model.clarifications)}. Confirmed declarations do not establish causal or universal domain validity.",
                "",
            ]
    for i, p in enumerate(workspace.pins, 1):
        f = p["finding"]
        lines += [
            f"## {i} {f['title']}",
            "",
            f["observation"],
            "",
            f"Evidence: {f['result_id']} · {f['claim_type']}",
            "",
        ]
        checks = {c["id"]: c for c in p.get("challenges", [])}
        if workspace.investigation:
            checks.update(
                {
                    c.id: c.model_dump(mode="json")
                    for c in workspace.investigation.challenges
                    if c.parent_id == f["id"]
                }
            )
        for c in checks.values():
            lines += [f"Check · {c['operation']} · {c['status']}: {c['summary']}", ""]
        for caveat in f.get("limitations", []):
            lines += ["Limitation: " + caveat, ""]
        if p.get("note"):
            lines += ["User interpretation: " + p["note"], ""]
    for i, bundle in enumerate(workspace.comparisons, 1):
        lines += [
            f"## Comparison {i}",
            "",
            f"Selected rows: {len(bundle.spec.selection.rows):,}; reference rows: {len(bundle.spec.reference_rows):,}. Reference: {bundle.spec.reference}; denominator: {bundle.spec.denominator}; selection unit: {bundle.spec.selection.policy}.",
            "",
            f"Recorded comparison: {bundle.id}",
            "",
        ]
        lines += [message + "\n" for message in bundle.exclusions]
        if bundle.interpretation.get("synthesis"):
            lines += ["Model interpretation: " + bundle.interpretation["synthesis"]["interpretation"], ""]
    if workspace.model:
        m = workspace.model
        lines += [
            "## Model protocol",
            "",
            f"Diagnostics: {m.provider} · {m.split} holdout",
            f"Training rows: {len(m.train_ids):,}; held-out rows: {len(m.test_ids):,}.",
            "",
        ]
        for warning in m.warnings:
            lines += [warning, ""]
    if workspace.investigation and workspace.investigation.terra.get("synthesis"):
        s = workspace.investigation.terra["synthesis"]
        lines += [
            "## Model interpretation",
            "",
            s["interpretation"],
            "",
            "This generated interpretation is distinct from computed observations.",
            "",
        ]
        lines += ["Next question: " + q for q in s.get("next_questions", [])]
    if not workspace.pins:
        lines += ["No findings were pinned. The bundle still contains the computed investigation.", ""]
    return "\n".join(lines)


def export_bundle(workspace: Workspace, include_data: bool = False) -> bytes:
    if workspace.dataset is None or workspace.investigation is None:
        raise ValueError("Run an investigation before exporting.")
    ds, inv = workspace.dataset, workspace.investigation
    files = {
        "dataset/schema.json": json_bytes(ds.record.model_dump(mode="json")),
        "profiles/dataset.json": json_bytes(workspace.profile),
        "profiles/semantics.json": json_bytes([f.model_dump(mode="json") for f in ds.record.fields]),
        "profiles/semantic-review.json": json_bytes(workspace.semantic_review),
        "semantics/contract.json": json_bytes(
            ds.record.semantic_model.model_dump(mode="json") if ds.record.semantic_model else None
        ),
        "semantics/decisions.json": json_bytes(inv.semantic_decisions),
        "analysis/context.json": json_bytes(inv.context.model_dump(mode="json")),
        "analysis/findings.json": json_bytes([f.model_dump(mode="json") for f in inv.findings]),
        "analysis/challenges.json": json_bytes([c.model_dump(mode="json") for c in inv.challenges]),
        "analysis/decisions.json": json_bytes([d.model_dump(mode="json") for d in inv.decisions]),
        "analysis/search.json": json_bytes(inv.candidate_log),
        "analysis/coverage.json": json_bytes(inv.coverage),
        "analysis/opened.json": json_bytes(sorted(workspace.opened)),
        "analysis/related.json": json_bytes(inv.related_views),
        "analysis/comparisons.json": json_bytes(
            {
                "saved": [b.model_dump(mode="json") for b in workspace.comparisons],
                "active": workspace.comparison.model_dump(mode="json") if workspace.comparison else None,
            }
        ),
        "analysis/terra.json": json_bytes(inv.terra),
        "notes.json": json_bytes(workspace.pins),
        "environment.json": json_bytes(environment()),
        "brief.md": brief(workspace).encode(),
        "REPLAY.md": (
            "Inspect: python -m firstlook.replay inspect investigation.zip\n"
            "Recompute: python -m firstlook.replay recompute investigation.zip --data original.csv\n"
            "Inspection makes no API calls. Model outputs are recorded, not freshly re-executed.\n"
            "A checksum detects a change; it does not establish authorship or scientific correctness.\n"
        ).encode(),
    }
    for rid, result in inv.results.items():
        files[f"tables/{rid}.json"] = json_bytes(result.model_dump(mode="json"))
    if workspace.model:
        files["model/run.json"] = json_bytes(workspace.model.model_dump(mode="json"))
    if inv.model_runs:
        files["model/history.json"] = json_bytes([m.model_dump(mode="json") for m in inv.model_runs])
    data_name = None
    if include_data:
        raw = ds.raw if ds.raw is not None else ds.frame.to_csv(index=False).encode()
        if hashlib.sha256(raw).hexdigest() != ds.record.fingerprint:
            raise ValueError("The original data bytes do not match the recorded fingerprint.")
        data_name = "dataset/original.parquet" if raw.startswith(b"PAR1") else "dataset/original.csv"
        files[data_name] = raw
    files["manifest.json"] = json_bytes(
        {
            "schema_version": 3,
            "app": "First Look",
            "data_file": data_name,
            "fingerprint": ds.record.fingerprint,
            "context": inv.context.id,
            "results": list(inv.results),
            "contains_private_data": bool(include_data),
        }
    )
    files["checksums.json"] = json_bytes(
        {name: hashlib.sha256(blob).hexdigest() for name, blob in files.items()}
    )
    if sum(map(len, files.values())) > MAX_EXPANDED:
        raise ValueError("The evidence bundle exceeds the expanded size budget.")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def read_bundle(data: bytes) -> dict[str, bytes]:
    if len(data) > 30 * 1024**2:
        raise ValueError("The compressed bundle exceeds 30 MiB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError("The archive exceeds its entry or expanded-size budget.")
            names = [i.filename for i in infos]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate archive paths are not allowed.")
            for i in infos:
                path = PurePosixPath(i.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in i.filename
                    or ":" in i.filename
                    or stat.S_ISLNK(i.external_attr >> 16)
                    or path.suffix not in {".json", ".csv", ".parquet", ".md"}
                ):
                    raise ValueError("Unsafe or unsupported archive entry.")
            files = {i.filename: z.read(i) for i in infos}
        checks = json.loads(files["checksums.json"])
        if not isinstance(checks, dict):
            raise ValueError("The checksum manifest must be an object.")
        if set(checks) != set(files) - {"checksums.json"}:
            raise ValueError("The checksum manifest does not cover all files.")
        for name, expected in checks.items():
            if hashlib.sha256(files[name]).hexdigest() != expected:
                raise ValueError("A bundle checksum does not match.")
        manifest = json.loads(files["manifest.json"])
        if not isinstance(manifest, dict):
            raise ValueError("The investigation manifest must be an object.")
        if manifest.get("schema_version") not in {1, 2, 3} or manifest.get("app") != "First Look":
            raise ValueError("Unsupported investigation format.")
        return files
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, RuntimeError, NotImplementedError) as exc:
        raise ValueError("This is not a complete First Look evidence bundle.") from exc


def import_bundle(
    data: bytes, original: bytes | None = None, original_name: str = "original.csv"
) -> Workspace:
    files = read_bundle(data)
    manifest = json.loads(files["manifest.json"])
    record = DatasetRecord.model_validate_json(files["dataset/schema.json"])
    ctx = AnalysisContext.model_validate_json(files["analysis/context.json"])
    if ctx.dataset != record.fingerprint or ctx.id != manifest["context"]:
        raise ValueError("Dataset/context identity mismatch.")
    if len(set(ctx.row_ids)) != len(ctx.row_ids) or any(i < 0 or i >= record.rows for i in ctx.row_ids):
        raise ValueError("Invalid recorded row membership.")
    raw_name = manifest.get("data_file")
    raw = files[raw_name] if raw_name else original
    ds = None
    if raw is not None:
        if hashlib.sha256(raw).hexdigest() != record.fingerprint:
            raise ValueError("Supply the exact original data; its fingerprint does not match.")
        ds = load_table(
            raw,
            raw_name or original_name,
            delimiter=str(record.parser.get("delimiter", ",")),
            encoding=str(record.parser.get("encoding", "utf-8-sig")),
            missing_tokens=cast(Any, record.parser.get("missing_tokens")),
        )
        if ds.record.rows != record.rows or ds.record.columns != record.columns:
            raise ValueError("Recorded dimensions do not match the supplied data.")
        ds.record = record
        if record.semantic_model:
            from firstlook.semantic.model import validate_model

            validate_model(ds, record.semantic_model)
        if ds.context(ctx.row_ids, ctx.focus, ctx.assumption).id != ctx.id:
            raise ValueError("The recorded semantic contract does not match the analytical context.")
    else:
        # A data-free bundle supports saved-result inspection, not computational replay.
        import pandas as pd

        ds = Dataset(record, pd.DataFrame(columns=pd.Index([f.id for f in record.fields])), None)
    inv = Investigation(ctx)
    inv.coverage = json.loads(files.get("analysis/coverage.json", b"[]"))
    inv.related_views = json.loads(files.get("analysis/related.json", b"{}"))
    if (
        not isinstance(inv.coverage, list)
        or len(inv.coverage) > 20
        or not isinstance(inv.related_views, dict)
        or len(inv.related_views) > 18
    ):
        raise ValueError("Invalid recorded exploration scope.")
    from firstlook.exploration_contracts import PerspectiveCoverage

    for item in inv.coverage:
        PerspectiveCoverage.model_validate(item)
    inv.semantic_decisions = json.loads(files.get("semantics/decisions.json", b"[]"))
    if not isinstance(inv.semantic_decisions, list) or len(inv.semantic_decisions) > 2000:
        raise ValueError("Invalid semantic decision ledger.")
    if "semantics/contract.json" in files:
        expected = record.semantic_model.model_dump(mode="json") if record.semantic_model else None
        if json.loads(files["semantics/contract.json"]) != expected:
            raise ValueError("The exported semantic contract and dataset record disagree.")
    inv.findings = [Finding.model_validate(v) for v in json.loads(files["analysis/findings.json"])]
    inv.challenges = [
        ChallengeResult.model_validate(v) for v in json.loads(files["analysis/challenges.json"])
    ]
    inv.decisions = [DecisionRecord.model_validate(v) for v in json.loads(files["analysis/decisions.json"])]
    inv.terra = json.loads(files["analysis/terra.json"])
    if not isinstance(inv.terra, dict):
        raise ValueError("Invalid recorded interpretation.")
    if inv.terra.get("synthesis"):
        NarrativeSynthesis.model_validate(inv.terra["synthesis"])
    inv.candidate_log = json.loads(files.get("analysis/search.json", b"[]"))
    if not isinstance(inv.candidate_log, list) or len(inv.candidate_log) > 2000:
        raise ValueError("Invalid candidate search log.")
    for rid in manifest["results"]:
        if not isinstance(rid, str) or not rid.isalnum():
            raise ValueError("Invalid result identity.")
        result = ResultArtifact.model_validate_json(files[f"tables/{rid}.json"])
        if result.id != rid or result.plan.context != ctx.id:
            raise ValueError("A result reference has a different context.")
        inv.results[rid] = result
    for f in inv.findings:
        if f.result_id not in inv.results:
            raise ValueError("A finding refers to a missing result.")
        if f.chart.result_id != f.result_id or f.chart.context != ctx.id:
            raise ValueError("A chart refers to mismatched evidence.")
    for primary, link in inv.related_views.items():
        if (
            not isinstance(link, dict)
            or primary not in inv.results
            or link.get("companion") not in inv.results
            or set(link) - {"companion", "intent"}
        ):
            raise ValueError("A companion refers to missing or unsupported evidence.")
    pins = json.loads(files["notes.json"])
    if not isinstance(pins, list) or len(pins) > 100:
        raise ValueError("Invalid pinned evidence.")
    for item in pins:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("note", ""), str)
            or len(item.get("note", "")) > 4000
        ):
            raise ValueError("Invalid evidence note.")
        f = Finding.model_validate(item["finding"])
        r = ResultArtifact.model_validate(item["result"])
        if f.result_id != r.id or f.chart.result_id != r.id or f.chart.context != r.plan.context:
            raise ValueError("Pinned evidence has mismatched references.")
        for c in item.get("challenges", []):
            if ChallengeResult.model_validate(c).parent_id != f.id:
                raise ValueError("Pinned check belongs to another finding.")
        if "context" in item and AnalysisContext.model_validate(item["context"]).id != r.plan.context:
            raise ValueError("Pinned context does not match its result.")
    ws = Workspace(
        dataset=ds,
        investigation=inv,
        profile=json.loads(files["profiles/dataset.json"]),
        pins=pins,
        focus=ctx.focus,
        rows=ctx.row_ids,
        assumption=ctx.assumption,
        replay=True,
        semantic_review=json.loads(files.get("profiles/semantic-review.json", b"{}")),
    )
    from firstlook.comparison import validate_bundle, dataset_for_bundle
    from firstlook.exploration_contracts import ComparisonBundle

    comparisons = json.loads(files.get("analysis/comparisons.json", b'{"saved":[],"active":null}'))
    if (
        not isinstance(comparisons, dict)
        or set(comparisons) != {"saved", "active"}
        or not isinstance(comparisons["saved"], list)
        or len(comparisons["saved"]) > 3
    ):
        raise ValueError("Invalid comparison board collection.")
    ws.comparisons = [ComparisonBundle.model_validate(item) for item in comparisons["saved"]]
    ws.comparison = ComparisonBundle.model_validate(comparisons["active"]) if comparisons["active"] else None
    for item in ws.comparisons + ([ws.comparison] if ws.comparison else []):
        if item is ws.comparison and item.spec.selection.base.id != ctx.id:
            raise ValueError("The active comparison belongs to another anchored context.")
        own_dataset = dataset_for_bundle(item, ds)
        validate_bundle(item, own_dataset if raw is not None else None)
    if ws.comparison:
        ws.selection = ws.comparison.spec.selection
        ws.cohort_revision = ws.selection.revision
    opened = json.loads(files.get("analysis/opened.json", b"[]"))
    if not isinstance(opened, list) or len(opened) > 2000 or not all(isinstance(i, str) for i in opened):
        raise ValueError("Invalid recorded opened-view state.")
    ws.opened = set(opened)
    if "model/run.json" in files:
        ws.model = ModelRun.model_validate_json(files["model/run.json"])
        if ws.model.context != ctx.id or set(ws.model.train_ids) & set(ws.model.test_ids):
            raise ValueError("Model evaluation has mismatched context or overlapping memberships.")
    if "model/history.json" in files:
        inv.model_runs = [ModelRun.model_validate(m) for m in json.loads(files["model/history.json"])]
    elif ws.model:
        inv.model_runs = [ws.model]
    from firstlook.comparison import validate_model_slice

    for bundle in ws.comparisons + ([ws.comparison] if ws.comparison else []):
        validate_model_slice(bundle, inv.model_runs)
    return ws


def recompute(workspace: Workspace) -> list[dict]:
    if workspace.dataset is None or workspace.dataset.frame.empty:
        raise ValueError("Recomputation requires the exact original dataset.")
    inv = workspace.investigation
    if inv is None:
        raise ValueError("No recorded investigation.")
    checks = []
    for rid, saved in inv.results.items():
        if saved.plan.operation == "model_diagnostic":
            checks.append({"result": rid, "status": "recorded-model-output"})
            continue
        if "recipe_version" not in saved.plan.params:
            checks.append({"result": rid, "status": "legacy-recipe-inspection-only"})
            continue
        actual, _ = analyze(workspace.dataset, inv.context, saved.plan)
        same = actual.model_dump(mode="json") == saved.model_dump(mode="json")
        checks.append({"result": rid, "status": "match" if same else "different"})
    from firstlook.challenges import challenge

    for saved in inv.challenges:
        finding = next((f for f in inv.findings if f.id == saved.parent_id), None)
        if finding is None or (saved.result and saved.result.plan.operation == "model_diagnostic"):
            checks.append({"result": saved.id, "status": "recorded-model-output"})
            continue
        if "recipe_version" not in inv.results[finding.result_id].plan.params:
            checks.append({"result": saved.id, "status": "legacy-recipe-inspection-only"})
            continue
        # Explicit group choice is encoded in the check ID and retained in its metadata.
        group = saved.result.metadata.get("group_field") if saved.result else None
        if saved.id == digest([finding.id, saved.operation, None]):
            group = None
        actual = challenge(workspace.dataset, inv, finding, saved.operation, group)
        same = actual.model_dump(mode="json") == saved.model_dump(mode="json")
        checks.append({"result": saved.id, "status": "match" if same else "different"})
    from firstlook.comparison import build_comparison, dataset_for_bundle

    unique = {b.id: b for b in workspace.comparisons}
    if workspace.comparison:
        unique[workspace.comparison.id] = workspace.comparison
    for bundle in unique.values():
        own_dataset = dataset_for_bundle(bundle, workspace.dataset)
        spec = bundle.spec
        recorded_model = bundle.recorded_model or (
            next((m for m in inv.model_runs if m.id == bundle.model_slice.get("model_run")), None)
            if bundle.model_slice
            else None
        )
        actual = build_comparison(
            own_dataset,
            spec.selection,
            spec.operation,
            measure=spec.measure,
            metric=spec.metric,
            groups=spec.group_by,
            reference=spec.reference,
            denominator=spec.denominator,
            model=recorded_model,
        )
        before = bundle.model_dump(mode="json", exclude={"interpretation", "checks", "decisions"})
        after = actual.model_dump(mode="json", exclude={"interpretation", "checks", "decisions"})
        checks.append({"result": bundle.id, "status": "match" if before == after else "different"})
        for saved in bundle.checks:
            view = next(v for v in bundle.views if v.finding.id == saved.parent_id)
            child = Investigation(
                view.context, findings=[view.finding], results={view.result.id: view.result}
            )
            group = saved.result.metadata.get("group_field") if saved.result else None
            if saved.id == digest([view.finding.id, saved.operation, None]):
                group = None
            actual_check = challenge(own_dataset, child, view.finding, saved.operation, group)
            checks.append(
                {
                    "result": saved.id,
                    "status": "match"
                    if actual_check.model_dump(mode="json") == saved.model_dump(mode="json")
                    else "different",
                }
            )
    return checks
