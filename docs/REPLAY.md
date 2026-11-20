# Evidence replay

In **Evidence**, choose whether to include the exact original file. Saved result tables and packets can contain sensitive values even when original-file inclusion is off. API keys are excluded. The ZIP uses bounded, checksummed JSON/data artifacts; importing it never executes Python, pickle, notebooks or queries. A checksum detects modification, not authorship.

```bash
python -m firstlook.replay inspect investigation.zip
python -m firstlook.replay recompute investigation.zip
# For an export without original data:
python -m firstlook.replay recompute investigation.zip --data exact-original.csv
```

Inspection reuses recorded model output. Deterministic recomputation compares analytical results and completed checks; it does not call hosted models. Pinned observations retain their original context and semantics when later work changes direction.
