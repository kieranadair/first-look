# Evidence replay

In **Evidence**, choose whether to include the exact original file. Saved result tables and packets can contain sensitive values even when original-file inclusion is off. API keys are excluded. The ZIP uses bounded, checksummed JSON/data artifacts; importing it never executes Python, pickle, notebooks or queries. A checksum detects modification, not authorship.

```bash
python -m firstlook.replay inspect investigation.zip
python -m firstlook.replay recompute investigation.zip
# For an export without original data:
python -m firstlook.replay recompute investigation.zip --data exact-original.csv
```

Inspection reuses recorded model output. Deterministic recomputation compares analytical results and completed checks; it does not call hosted models. Pinned observations retain their original context and semantics when later work changes direction.

Version 2 bundles include `semantics/contract.json` and `semantics/decisions.json`, plus the contract inside the dataset schema. They retain quantity meanings, metric algebra, entities, relationships, schedules, assertions and open decisions. Source-backed imports validate structural declarations and context identity. Version 1 bundles remain readable. Imported machine facts in standalone contracts are recomputed; human declarations are attestations, not authenticated authorship.
