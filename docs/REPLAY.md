# V2 records and evidence inspection

In **Investigate**, deliberately keep a view that matters. In **Record**, add an interpretation or next question and prepare the download. Saved observations retain the original field roles, meanings, time policy, source memberships, request, result and comparison. Later changes to working meanings do not rewrite them.

Two downloads serve different needs:

- **Readable Markdown:** the question, supplied context, chosen definitions, bounded table excerpts, limitations and human notes.
- **Evidence ZIP:** complete recorded tables and definitions, the most recent twenty-four model-review records and the predictive record when one has been run and optionally the exact original file. Its manifest and checksums detect changed bytes.

A bundle contains `investigation.json`, `record.md`, `manifest.json`, `checksums.json` and optionally `source.csv` or `source.parquet`. The format identifier is `first-look-v2-evidence-1`; no executable artifacts, pickle or arbitrary archive paths are accepted. Import is bounded to 35 MiB compressed and 100 MiB expanded.

## Inspecting a saved investigation

Use the saved-investigation inspection control in **Record**. Inspection does not replace the active working table or call any providers.

Without original source bytes, the app checks the bundle's integrity, scope identities and recorded definitions, then identifies it as **recorded evidence only**. It cannot establish agreement with omitted source values. With matching original bytes included—or supplied to the Python inspection function—the app reparses the exact source, checks its SHA-256 fingerprint and independently recomputes deterministic saved analyses and comparisons. Recorded provider judgments and model predictions are inspected as recorded output; they are never regenerated or refitted.

For a Python workflow:

```python
from pathlib import Path
from firstlook.evidence import inspect_bundle

recorded = inspect_bundle(Path("investigation.zip").read_bytes())
print(recorded["verification"])

# Supply exact original bytes for an export that omitted them:
verified = inspect_bundle(
    Path("investigation.zip").read_bytes(),
    raw=Path("original.csv").read_bytes(),
)
print(verified["source_verified"])
```

There is no V2 replay CLI. Historical commands and V1 bundle formats belong to [the archived V1 app](../archive/v1/REFERENCE.md); V2 does not silently reinterpret them.

## Sharing

Omitting the original file does **not** make an export anonymous. Result labels, calculated values, exact memberships, supplied context, model packets and held-out outcomes can disclose information about the original data. Review the contents before sharing. Credentials are excluded. A checksum proves neither who made a declaration nor whether it is true in the domain.

Community Cloud sessions are temporary. Download work you want to preserve before a reboot or release change.
