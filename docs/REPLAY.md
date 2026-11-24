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

Version 3 adds perspective coverage, explicit opened-view state, companion relationships and comparison boards. Each selected/reference result validates against its own recorded child context. Saved boards carry their own dataset/semantic snapshot and original predictive protocol when applicable, so a subsequent meaning edit does not rewrite them. Recompute uses each board's own parsing and semantic scope; it never relaxes the global context checks for ordinary findings.

The typed-judgment uplift adds optional version-3 files: `analysis/judgments.json`, `analysis/recommendations.json`, `analysis/question-history.json`, `analysis/workflow.json` and `analysis/text-features.json`. Older bundles without them remain readable. They retain exact state and question definitions, probability distributions, requested/resolved models, usage and measured request latency when available, policy thresholds, interpretation corrections, note passages, isolated assumptions, frozen text questions, row-level statuses and matched model protocols. Claim reviews remain with the recorded Terra synthesis or comparison interpretation.

Import validates hashes, question identities, distributions and code outcomes. Text coding reconciles row values with the frozen recorded questions and answers. With source bytes present, replay also checks original text and source membership. Derived modeling tables retain their own schema/fingerprint and a mapping to original row IDs; recorded held-out memberships must match and remain disjoint. These checks do not reclassify text, rejudge prose, refit models or establish that a model's answer was correct. A data-free bundle remains inspectable but cannot prove agreement with omitted original source values.

**Privacy:** exact model inputs, including coded text, supplied notes and text-only proposal examples, can be present even when original-file inclusion is off. Review the archive before sharing it. No key is included. Inspecting the Text lab or Judgments pages in a reopened bundle uses recorded outputs without a provider call.

Calculation plans now carry an explicit recipe version. Historical plans without one remain inspectable and are reported as `legacy-recipe-inspection-only`; the CLI does not silently substitute repaired ranking or ECDF algorithms and call that an identical replay. Stored model output is never presented as a fresh model evaluation.
