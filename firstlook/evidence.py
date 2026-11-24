"""Small checksummed evidence, readable without a model and replayed only from exact source bytes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import html
import io
import json
from pathlib import PurePosixPath
import re
from typing import Any
import zipfile

import pandas as pd

from firstlook.types import Dataset, Field, Meaning, Request, Result, TimeRule, clean, digest

MAX_EXPANDED = 100 * 1024**2
FORMAT = "first-look-v2-evidence-1"


def _bytes(value) -> bytes:
    return json.dumps(clean(value), indent=2, ensure_ascii=False, allow_nan=False).encode()


def _working(session):
    if session.current is None:
        return None
    return clean(
        {
            "id": digest([session.current.id, clean(session.comparison)]),
            "context": session.context,
            "result": session.current,
            "comparison": session.comparison,
            "meanings": session.meanings,
            "time_rules": session.time_rules,
            "fields": session.ds.fields,
            "question": session.question,
            "note": "",
        }
    )


def _payload(session):
    ds = session.ds
    if ds is None:
        raise ValueError("Open your table before saving an investigation.")
    return clean(
        {
            "format": FORMAT,
            "dataset": {
                "name": ds.name,
                "fingerprint": ds.fingerprint,
                "rows": len(ds.frame),
                "fields": ds.fields,
                "parser": ds.parser,
            },
            "question": session.question,
            "notes": session.notes,
            "working": _working(session),
            "record": deepcopy(session.record),
            "provider_history": deepcopy(session.provider_history),
            "prediction": deepcopy(session.prediction),
        }
    )


def export(session, include_data: bool = False) -> bytes:
    payload = _payload(session)
    files = {"investigation.json": _bytes(payload), "record.md": readable_markdown(session).encode()}
    original = None
    if include_data:
        ds = session.ds
        if not ds.raw or hashlib.sha256(ds.raw).hexdigest() != ds.fingerprint:
            raise ValueError("The exact original source bytes are unavailable or have changed.")
        original = "source.parquet" if ds.raw.startswith(b"PAR1") else "source.csv"
        files[original] = ds.raw
    files["manifest.json"] = _bytes(
        {
            "format": FORMAT,
            "source": original,
            "fingerprint": session.ds.fingerprint,
            "contains_recorded_values": True,
            "contains_provider_inputs": bool(session.provider_history),
        }
    )
    if sum(map(len, files.values())) > MAX_EXPANDED:
        raise ValueError("This evidence exceeds the 100 MiB expanded size limit.")
    files["checksums.json"] = _bytes({name: hashlib.sha256(blob).hexdigest() for name, blob in files.items()})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, blob in files.items():
            archive.writestr(name, blob)
    return output.getvalue()


def _read(blob):
    if len(blob) > 35 * 1024**2:
        raise ValueError("Evidence archives are limited to 35 MiB compressed.")
    allowed = {
        "manifest.json",
        "checksums.json",
        "investigation.json",
        "record.md",
        "source.csv",
        "source.parquet",
    }
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            entries = archive.infolist()
            names = [f.filename for f in entries]
            if (
                len(names) != len(set(names))
                or not set(names) <= allowed
                or len(names) > 6
                or sum(f.file_size for f in entries) > MAX_EXPANDED
            ):
                raise ValueError("This archive contains unsupported files or exceeds its size limit.")
            if any(
                PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts or "\\" in n for n in names
            ):
                raise ValueError("Unsafe evidence archive path.")
            files = {name: archive.read(name) for name in names}
        checksums = json.loads(files["checksums.json"])
        if (
            not isinstance(checksums, dict)
            or set(checksums) != set(files) - {"checksums.json"}
            or any(checksums[name] != hashlib.sha256(files[name]).hexdigest() for name in checksums)
        ):
            raise ValueError("The evidence checksum does not match its contents.")
        manifest, payload = json.loads(files["manifest.json"]), json.loads(files["investigation.json"])
        if manifest.get("format") != FORMAT or payload.get("format") != FORMAT:
            raise ValueError(
                "This is not a First Look v2 investigation. Open v1 artifacts with the archived v1 app."
            )
        return files, manifest, payload
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("This evidence archive is incomplete or invalid.") from exc


def _fields(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 80:
        raise ValueError("Invalid recorded field definitions.")
    try:
        fields = [Field(**f) for f in raw]
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid recorded field definitions.") from exc
    if len({f.id for f in fields}) != len(fields) or any(
        f.kind not in {"number", "category", "time", "identifier", "text"} for f in fields
    ):
        raise ValueError("Invalid field identities or roles.")
    return fields


def _row_ids(rows, count):
    if (
        not isinstance(rows, list)
        or not rows
        or len(rows) != len(set(rows))
        or any(isinstance(r, bool) or not isinstance(r, int) or not 0 <= r < count for r in rows)
    ):
        raise ValueError("A recorded population contains invalid source memberships.")
    return rows


def _decode_result(raw, ds, meanings, rules):
    from firstlook.analysis import context_id

    try:
        details: dict[str, Any] = dict(raw)
        details["request"] = Request(**raw["request"])
        result = Result(**details)
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid recorded calculation.") from exc
    _row_ids(result.rows, len(ds.frame))
    if result.context != context_id(ds, meanings, result.rows, rules):
        raise ValueError("The result has a different source, meaning or population scope.")
    if result.request.view not in {
        "distribution",
        "categories",
        "groups",
        "relationship",
        "time",
        "missingness",
        "category_relationship",
        "spatial",
        "multivariate",
    }:
        raise ValueError("Unsupported recorded perspective.")
    for fid in [
        result.request.x,
        result.request.y,
        result.request.group,
        result.request.entity,
        result.request.weight,
        *result.request.fields,
    ]:
        if fid:
            ds.field(fid)
    if result.id != digest([result.context, result.request, result.table, result.meta]):
        raise ValueError("The recorded calculation identity does not match its contents.")
    return result


def _check_snapshot(raw, ds, verify):
    from firstlook.analysis import analyze, compare

    if not isinstance(raw, dict) or not set(raw) == {
        "id",
        "context",
        "result",
        "comparison",
        "meanings",
        "time_rules",
        "fields",
        "question",
        "note",
    }:
        raise ValueError("Invalid kept observation.")
    fields = _fields(raw["fields"])
    if [(f.id, f.name) for f in fields] != [(f.id, f.name) for f in ds.fields]:
        raise ValueError("Kept field identities differ from the uploaded source.")
    local = replace(ds, fields=fields)
    try:
        meanings = {fid: Meaning(**value) for fid, value in raw["meanings"].items()}
        rules = {fid: TimeRule(**value) for fid, value in raw["time_rules"].items()}
    except (TypeError, AttributeError) as exc:
        raise ValueError("Invalid recorded analytical meanings.") from exc
    for fid, meaning in meanings.items():
        if local.field(fid).kind != "number" or meaning.kind not in {"unknown", "additive", "nonadditive"}:
            raise ValueError("Recorded meaning does not identify a numerical quantity.")
        if meaning.entity:
            local.field(meaning.entity)
    for fid in rules:
        if local.field(fid).kind != "time":
            raise ValueError("Recorded time policy does not identify a timestamp.")
    result = _decode_result(raw["result"], local, meanings, rules)
    if raw["context"] != result.context:
        raise ValueError("The observation and result have different contexts.")
    companion = raw["comparison"]
    if companion is not None:
        if not isinstance(companion, dict) or set(companion) != {"selected", "reference", "definition"}:
            raise ValueError("Invalid recorded comparison.")
        left = _decode_result(companion["selected"], local, meanings, rules)
        right = _decode_result(companion["reference"], local, meanings, rules)
        if left.request != result.request or right.request != result.request:
            raise ValueError("Comparison definitions do not match the kept view.")
        if verify:
            actual = compare(local, result.request, left.rows, meanings, right.rows, rules)
            if clean(actual) != companion:
                raise ValueError("A comparison disagrees with the exact source data.")
    if raw["id"] != digest([result.id, companion]):
        raise ValueError("The kept observation identity does not match its result.")
    if verify:
        for f in fields:
            if f.kind == "number" and not pd.api.types.is_numeric_dtype(local.frame[f.id]):
                raise ValueError("A recorded numerical role contradicts the exact source data.")
            if f.kind == "time" and not pd.api.types.is_datetime64_any_dtype(local.frame[f.id]):
                raise ValueError("A recorded timestamp role contradicts the exact source data.")
        actual = analyze(local, result.request, meanings, result.rows, rules, edges=result.meta.get("edges"))
        if clean(actual) != raw["result"]:
            raise ValueError("A saved calculation disagrees with the exact source data.")


def inspect_bundle(blob: bytes, raw: bytes | None = None) -> dict:
    files, manifest, payload = _read(blob)
    try:
        schema = payload["dataset"]
        if not isinstance(schema, dict) or set(schema) != {"name", "fingerprint", "rows", "fields", "parser"}:
            raise ValueError("Invalid recorded source schema.")
        count = schema["rows"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 50000:
            raise ValueError("Invalid recorded source size.")
        fields = _fields(schema["fields"])
        if manifest.get("fingerprint") != schema["fingerprint"]:
            raise ValueError("Evidence source identities do not match.")
        source = manifest.get("source")
        if source is not None and source not in {"source.csv", "source.parquet"}:
            raise ValueError("Unsupported original source reference.")
        original = raw if raw is not None else files.get(source)
        verified = original is not None
        if verified:
            from firstlook.data import load_table

            if hashlib.sha256(original).hexdigest() != schema["fingerprint"]:
                raise ValueError("These bytes do not match the investigation's source fingerprint.")
            parser = schema["parser"]
            if not isinstance(parser, dict) or set(parser) - {"delimiter", "encoding", "missing_tokens"}:
                raise ValueError("Unsupported recorded parsing options.")
            ds = load_table(original, schema["name"], **parser)
            if len(ds.frame) != count or [(f.id, f.name) for f in ds.fields] != [
                (f.id, f.name) for f in fields
            ]:
                raise ValueError("The supplied source has a different recorded layout.")
            ds = replace(ds, fields=fields)
        else:
            # Scope inspection needs only the source size, identities and declarations.
            ds = Dataset(
                schema["name"],
                schema["fingerprint"],
                pd.DataFrame(index=range(count)),
                fields,
                schema["parser"],
            )
        records = payload["record"]
        if not isinstance(records, list) or len(records) > 24:
            raise ValueError("The investigation contains too many kept observations.")
        for entry in records + ([payload["working"]] if payload.get("working") else []):
            _check_snapshot(entry, ds, verified)
        if not isinstance(payload.get("provider_history"), list) or len(payload["provider_history"]) > 24:
            raise ValueError("Invalid recorded assistance history.")
        return {
            **payload,
            "verification": "Recomputed from matching source bytes"
            if verified
            else "Recorded evidence only; source bytes were not supplied",
            "source_verified": verified,
            "readable_markdown": files["record.md"].decode("utf-8"),
        }
    except (KeyError, TypeError, AttributeError, UnicodeDecodeError) as exc:
        raise ValueError("The recorded investigation is malformed.") from exc


def _plain(value):
    """Keep supplied prose/labels literal in Markdown, including links and raw HTML."""
    return re.sub(r"([\\`*_{}\[\]()#+!|])", r"\\\1", html.escape(str(value), quote=False))


def _labels(fields, meanings=None):
    names = [f["name"] for f in fields]
    output = {}
    for index, field in enumerate(fields):
        label = field["name"]
        if names.count(label) > 1:
            label += f" (column {index + 1})"
        meaning = (meanings or {}).get(field["id"], {})
        unit = meaning.get("unit") or field.get("unit")
        output[field["id"]] = label + (f" ({unit})" if unit else "")
    return output


def _displayed_table(result):
    """Choose the saved view's values, rather than a different underlying estimator."""
    request, meta = result["request"], result["meta"]
    if request["view"] == "time" and request.get("representation") == "calendar":
        return "Plotted weekday/hour cells", meta.get("calendar_cells", [])
    if request["view"] == "time" and "plotted_values" in meta:
        return "Plotted values", meta["plotted_values"]
    if request["view"] == "distribution" and request.get("representation") == "quantile":
        return "Plotted quantiles", meta.get("quantiles", [])
    if request.get("representation") == "box":
        return "Plotted box summaries", meta.get("group_stats", [result["summary"]])
    if meta.get("comparison_measure"):
        return "Common bins · plotted within-population shares and recorded counts", result["table"]
    return "Recorded view values", result["table"]


def _table_lines(table, labels, request=None):
    if not table:
        return ["No eligible recorded values for this view.", ""]
    request = request or {}
    keys = [k for k in table[0] if k not in {"rows", "row", "eligible_rows", "population_rows"}]
    if not keys:
        return ["No numerical or categorical display values.", ""]
    headers = {
        "low": "Interval start",
        "high": "Interval end",
        "count": "Recorded observations",
        "share": "Share",
        "probability": "Cumulative fraction",
        "value": "Value",
        "n": "Support",
        "missing": "Missing",
        "q1": "First quartile",
        "q3": "Third quartile",
        "min": "Minimum",
        "max": "Maximum",
        "mean": "Mean",
        "median": "Median",
        "field": "Field",
        "denominator": "Denominator",
        "observed": "Recorded interval",
        "date": labels.get(request.get("x"), "Date"),
        "hour": "Recorded hour",
        "weekday": "Weekday",
        "x": labels.get(request.get("x"), "X"),
        "y": labels.get(request.get("y"), "Y"),
        "latitude": labels.get(request.get("x"), "Latitude"),
        "longitude": labels.get(request.get("y"), "Longitude"),
    }

    def cell(row, key):
        value = row.get(key)
        if key == "field":
            value = labels.get(value, value)
        if key == "weekday" and isinstance(value, int) and 0 <= value < 7:
            value = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][value]
        if value is None:
            value = "Unknown"
        elif isinstance(value, float):
            value = format(value, ".8g")
        return _plain(value).replace("\n", " ")

    lines = [
        "| " + " | ".join(_plain(labels.get(k, headers.get(k, k))) for k in keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    lines += ["| " + " | ".join(cell(row, key) for key in keys) + " |" for row in table[:20]]
    lines += [""]
    if len(table) > 20:
        lines += [
            f"Showing the first 20 of {len(table):,} rows. The evidence JSON retains the complete saved values.",
            "",
        ]
    return lines


def _result_lines(result, labels):
    heading, table = _displayed_table(result)
    lines = [
        _plain(result["definition"]),
        "",
        f"Population: {len(result['rows']):,} recorded rows. Omitted from the required calculation: {result['omitted']:,}.",
        "",
        "**" + heading + "**",
        "",
    ]
    if result["request"]["view"] == "relationship":
        correlation = result["summary"].get("correlation")
        lines += [
            "Complete recorded pairs: "
            + str(result["summary"].get("n", 0))
            + ". Pearson correlation: "
            + ("not defined" if correlation is None else format(correlation, ".8g"))
            + ".",
            "",
        ]
    lines += _table_lines(table, labels, result["request"])
    lines += ["Caution: " + _plain(w) for w in result.get("warnings", [])] + [""]
    return lines


def readable_markdown(session) -> str:
    ds = session.ds
    lines = [
        "# My First Look",
        "",
        "A visual investigation, with definitions and questions worth keeping.",
        "",
    ]
    if ds:
        lines += ["Table: " + _plain(ds.name), "", "Source fingerprint: " + _plain(ds.fingerprint), ""]
    if session.question:
        lines += ["## My question", "", _plain(session.question), ""]
    if session.notes:
        lines += ["## Context I supplied", "", _plain(session.notes), ""]
    if not session.record:
        lines += ["No observations have been kept yet.", ""]
    for i, entry in enumerate(session.record, 1):
        labels = _labels(entry["fields"], entry["meanings"])
        lines += [f"## Observation {i}", ""]
        if entry.get("question"):
            lines += ["Question when kept: " + _plain(entry["question"]), ""]
        comparison = entry.get("comparison")
        if comparison:
            lines += ["Comparison: " + _plain(comparison["definition"]), "", "### Selected population", ""]
            lines += _result_lines(comparison["selected"], labels)
            lines += ["### Reference population", ""]
            lines += _result_lines(comparison["reference"], labels)
        else:
            lines += _result_lines(entry["result"], labels)
        if entry.get("note"):
            lines += ["### My interpretation or next question", "", _plain(entry["note"]), ""]
    if session.prediction:
        prediction = session.prediction
        labels = _labels(clean(ds.fields)) if ds else {}
        lines += [
            "## Predictive check",
            "",
            "Recorded predictions describe a fixed retrospective evaluation, not a cause or a guarantee about future data.",
            "",
            _plain(prediction.get("definition", "")),
            "",
            "Target: " + _plain(labels.get(prediction.get("target"), prediction.get("target", "Unknown"))),
            "",
            "Permitted predictors: "
            + ", ".join(_plain(labels.get(fid, fid)) for fid in prediction.get("predictors", [])),
            "",
            "Holdout: "
            + _plain(prediction.get("split", "Recorded split"))
            + (
                " by " + _plain(labels.get(prediction["split_field"], prediction["split_field"]))
                if prediction.get("split_field")
                else ""
            )
            + f" · {len(prediction.get('train_ids', [])):,} training records · {len(prediction.get('test_ids', [])):,} held-out records.",
            "",
        ]
        scores = [
            {"Model": m["name"], "Metric": m["metric"], "Score": m["score"]}
            for m in prediction.get("models", [])
        ]
        lines += _table_lines(scores, {})
        lines += [
            "MAE: lower is better. Balanced accuracy: higher is better. Interpret model differences against the recorded reference and holdout design.",
            "",
        ]
        lines += ["Caution: " + _plain(w) for w in prediction.get("warnings", [])] + [""]
    lines += [
        "The evidence archive retains complete recorded tables and definitions. A checksum detects modification; it does not establish authorship or business truth.",
        "",
    ]
    return "\n".join(lines)
