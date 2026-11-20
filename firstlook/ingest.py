"""Bounded table ingestion. Internal column and row identities never depend on labels."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from firstlook.contracts import AnalysisContext, DatasetRecord, FieldSpec, Role, digest

MAX_BYTES = 25 * 1024**2
MAX_ROWS = 50_000
MAX_COLS = 80
MAX_FRAME = 80 * 1024**2


class InputError(ValueError):
    pass


@dataclass
class Dataset:
    record: DatasetRecord
    frame: pd.DataFrame
    raw: bytes | None = None

    def field(self, field_id: str) -> FieldSpec:
        return next(f for f in self.record.fields if f.id == field_id)

    def label(self, field_id: str) -> str:
        return self.field(field_id).name

    def context(
        self, rows: list[int] | None = None, focus: str | None = None, assumption: str = "unknown"
    ) -> AnalysisContext:
        return AnalysisContext(
            dataset=self.record.fingerprint,
            semantics=digest(
                {
                    "fields": [f.model_dump() for f in self.record.fields],
                    "description": self.record.description,
                    "parser": self.record.parser,
                }
            ),
            row_ids=list(self.frame.index) if rows is None else rows,
            focus=focus,
            assumption=assumption,
        )


def _role(name: str, series: pd.Series) -> tuple[Role, str]:
    lower = name.lower()
    if re.search(r"(^id$|(^|[ _])id$|_id$|identifier|^index$|^record$|_code$)", lower):
        return Role.ID, "The field name suggests an identifier or code."
    if pd.api.types.is_datetime64_any_dtype(series):
        return Role.TIME, "Values parse as timestamps."
    if pd.api.types.is_bool_dtype(series):
        return Role.BOOL, "Recorded boolean values."
    n = series.nunique()
    if pd.api.types.is_numeric_dtype(series):
        finite = pd.to_numeric(series, errors="coerce").dropna()
        if n <= 2:
            return Role.BOOL, "Two or fewer numeric values; review their meaning."
        if len(finite) > 20 and finite.is_unique and np.allclose(np.diff(finite), 1):
            return Role.ID, "Unique consecutive numbers resemble a row identifier."
        if n <= 12 and (re.search(r"year|month|day|rank|level|season", lower)):
            return Role.ORDINAL, "A small numeric scale; order is explicit in its values."
        return Role.MEASURE, "Numeric values; confirm that arithmetic has a meaningful interpretation."
    if n <= 50 or n / max(len(series), 1) < 0.2:
        return Role.CATEGORY, "Repeated labels form a candidate dimension."
    return Role.TEXT, "High-cardinality text is excluded from numerical analysis."


def from_frame(
    frame: pd.DataFrame,
    name: str,
    raw: bytes | None = None,
    source: str = "Uploaded file",
    parser: dict | None = None,
) -> Dataset:
    if not 0 < len(frame) <= MAX_ROWS:
        raise InputError(f"Use a nonempty table with at most {MAX_ROWS:,} rows.")
    if not 0 < len(frame.columns) <= MAX_COLS:
        raise InputError(f"Use a table with at most {MAX_COLS} fields.")
    if frame.memory_usage(deep=True).sum() > MAX_FRAME:
        raise InputError("The decoded table exceeds the 80 MiB memory budget.")
    frame = frame.copy().reset_index(drop=True)
    original_names = [str(c) for c in frame.columns]
    frame.columns = [f"f{i:03}" for i in range(len(frame.columns))]
    fields = []
    for position, (field_id, original) in enumerate(zip(frame.columns, original_names)):
        s = frame[field_id]
        failures = 0
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            if s.dropna().map(lambda v: isinstance(v, (list, dict, tuple, bytes))).any():
                raise InputError(f"Nested values in {original!r} are unsupported.")
            s = s.mask(s.eq(""))
            numeric = pd.to_numeric(s, errors="coerce")
            valid = int(s.notna().sum())
            leading_codes = s.dropna().astype(str).str.match(r"^[+-]?0\d+$").any()
            if valid and not leading_codes and numeric.notna().sum() / valid >= 0.95:
                failures = int((s.notna() & numeric.isna()).sum())
                s = numeric
            elif (
                re.search(r"date|time|timestamp|dteday|(^|_)day$", original, re.I)
                and valid
                and not leading_codes
            ):
                parsed = pd.to_datetime(s, errors="coerce", format="mixed")
                if parsed.notna().sum() / valid >= 0.95:
                    failures = int((s.notna() & parsed.isna()).sum())
                    s = parsed
        if pd.api.types.is_numeric_dtype(s):
            nonfinite = s.notna() & ~np.isfinite(s.astype(float))
            failures += int(nonfinite.sum())
            s = s.mask(nonfinite)
        frame[field_id] = s
        role, evidence = _role(original, s)
        unit_match = re.search(r"_(mm|cm|kg|g|ms|seconds|percent)$", original, re.I)
        order = [str(v) for v in sorted(s.dropna().unique())] if role == Role.ORDINAL else []
        fields.append(
            FieldSpec(
                id=field_id,
                name=original,
                position=position,
                physical_type=str(s.dtype),
                role=role,
                proposed_role=role,
                unit=unit_match.group(1) if unit_match else "",
                order=order,
                evidence=evidence,
                parse_failures=failures,
            )
        )
    source_bytes = raw if raw is not None else frame.to_csv(index=False).encode()
    fingerprint = hashlib.sha256(source_bytes).hexdigest()
    return Dataset(
        DatasetRecord(
            fingerprint=fingerprint,
            name=name,
            rows=len(frame),
            columns=len(frame.columns),
            fields=fields,
            source=source,
            parser=parser or {"missing_tokens": [""]},
        ),
        frame,
        raw,
    )


def load_table(
    data: bytes,
    name: str,
    delimiter: str = ",",
    encoding: str = "utf-8-sig",
    missing_tokens: list[str] | None = None,
) -> Dataset:
    if len(data) > MAX_BYTES:
        raise InputError("The file exceeds the 25 MiB upload limit.")
    try:
        if name.lower().endswith(".parquet"):
            import pyarrow.parquet as pq

            table = pq.ParquetFile(io.BytesIO(data))
            if table.metadata.num_rows > MAX_ROWS or len(table.schema_arrow) > MAX_COLS:
                raise InputError("Parquet dimensions exceed the supported envelope.")
            decoded = sum(
                table.metadata.row_group(i).total_byte_size for i in range(table.metadata.num_row_groups)
            )
            if decoded > MAX_FRAME:
                raise InputError("Parquet decoded size exceeds the memory budget.")
            frame = table.read().to_pandas()
        elif name.lower().endswith(".csv"):
            text = data.decode(encoding)
            names = next(csv.reader(io.StringIO(text), delimiter=delimiter))
            if len(names) > MAX_COLS:
                raise InputError("Too many columns.")
            chunks = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                header=None,
                skiprows=1,
                dtype=str,
                keep_default_na=False,
                nrows=MAX_ROWS + 1,
                on_bad_lines="error",
                chunksize=5000,
            )
            parts, decoded = [], 0
            for chunk in chunks:
                decoded += int(chunk.memory_usage(deep=True).sum())
                if decoded > MAX_FRAME:
                    raise InputError("The decoded CSV exceeds the 80 MiB memory budget.")
                parts.append(chunk)
            frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
            if len(names) != len(frame.columns):
                raise InputError("Header width does not match the data.")
            frame.columns = names
            frame = frame.mask(frame.isin(missing_tokens or [""]))
        else:
            raise InputError("Choose a CSV or Parquet file.")
        return from_frame(
            frame,
            name,
            data,
            parser={
                "delimiter": delimiter,
                "encoding": encoding,
                "missing_tokens": missing_tokens or [""],
            },
        )
    except InputError:
        raise
    except (ValueError, UnicodeError, StopIteration, OSError, csv.Error) as exc:
        raise InputError(f"Could not parse this table: {str(exc)[:180]}") from exc
