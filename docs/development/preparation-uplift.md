# Automatic analytical preparation · First Look 0.6.0

Uploads now produce an analytical draft before asking the analyst to populate forms. Local evidence is immediate; connected interpretation is an explicit per-upload option. Confirming meanings remains an explicit, atomic review action. This release adds no dependencies, generated code, database or key-entry mechanism.

## Workflow

1. Open CSV/Parquet in **Understand**. The preparation overview shows proposed definitions and available operations alongside field evidence. Descriptive exploration is already available.
2. Optionally enable **Automatically prepare with connected models**. This also grants dataset sharing permission. One background request enriches the local draft; reruns never repeat it. Local overview computation remains available while preparation owns the worker slot.
3. Open **Preparation → Review**. Select related definitions and inspect their reasons/evidence. Required components are listed before confirmation. **Check the selected bundle** validates an isolated copy; **Confirm selected definitions** commits once. Detailed Meaning controls remain available.
4. For repeated additive values, compare explicit numerical interpretations and illustrative source records. A direct clarification can establish the quantity, entity and metric together. Equality alone never selects an interpretation.
5. In **Context & documents**, optionally supply a question, a recording-process explanation and a UTF-8 dictionary (`md`, `txt`, `csv`, `json`). Terra proposes a coherent bundle for review. Literal Parquet description/unit/currency metadata is retained automatically as supplied dictionary evidence.
6. Open a prepared metric view or broad overview. Accepted meanings govern existing planning, calculation, chart, evidence and model paths. Declared prediction target/timing prefill Models; preparation never fits a foundation model or searches its final holdout.
7. Under **Reuse & record**, download approved definitions or explicitly remember them for matching uploads in this session. A matching new upload receives a fresh template-based draft. Download templates to survive Cloud restarts. Investigation exports include preparation evidence.

The last confirmed bundle can be undone while its resulting contract is current. Undo is recorded and invalidates dependent work. A later manual edit disables automatic undo. Pending background proposals cannot overwrite conflicting manual changes; unrelated declarations survive.

## Architecture and responsibilities

| Module | Responsibility |
|---|---|
| `preparation_contracts.py` | Bounded drafts, changes, literal citations and structured connected interpretations |
| `preparation.py` | Composite key candidates, finite metric bundles, exact source witnesses, interpretation comparisons, dependency closure, atomic validation/application, readiness and evidence inspection |
| `preparation_connected.py` | Source bounds, compact packets, coherent-response reconciliation, optional matched diagnostic charts/tables, Jev support/scope/relevance |
| `preparation_templates.py` | Portable definitions, exact unambiguous name/type-family matching, identity/component remapping, equivalent-metric reuse and structural drift |
| `ui/preparation.py`, `app_pages/preparation.py` | Prepared overview, adjacent review/evidence, context input, reuse and record |
| `ui/runtime.py`, `state.py` | Session-owned workers, request deduplication/budgets, stale guards, one invalidation per bundle, undo, readiness cache and session templates |

Python owns arithmetic, memberships and eligibility. Terra synthesizes cross-field evidence and supplied definitions. With visual review enabled, it receives up to two finite diagnostic charts and matched renderer tables/manifests. These are offscreen analytical assets, not screenshots of the app. Jev answers independent source-support, applicability and relevance questions in a bounded batch. Neither provider confirms a business meaning or grants an operation permission. Preparation judgments also appear in Judgments.

TabPFN stays downstream of a suitable task and the existing shared model protocol. Predictive performance cannot establish business meaning, units, completeness or historical availability. Preparation does not automatically fit models or use final-test performance to select interpretations.

## Contract rules

- Drafts bind to exact bytes and parsing/physical layout. A bundle validates roles, quantities, entities, metric components, temporal definitions and task/availability rules on a copy before replacing the active record. Failure changes nothing.
- Per-subject preconditions prevent background or cached proposals overwriting conflicting edits. Receiving a draft changes no active meaning. Different source/parser results are discarded.
- New model-supplied units, currencies and measurement bases require verbatim supporting passages. Fabricated citations block application. Quantity proposals cannot smuggle availability or transform permissions into the contract.
- Schedules, gap zeros, completeness and historical availability cannot be inferred from patterns. Connected proposals require supplied evidence and explicit review; existing validators still enforce schedule/coverage/task-basis requirements.
- Weighted averages and component ratios use finite recipes. Nonnegative weights alone do not establish the desired estimator. Incompatible metric bundles are blocked.
- Repeated-value alternatives use full-upload complete identifier/value records. Totals are hypothetical additive interpretations, with omissions and source memberships retained. Agreement on this upload never proves equivalence.
- Clarification priority combines engineered task relevance, affected definitions and alternative differences; optional Jev relevance augments it. This is not a learned information-gain estimate. Unrelated time policies are deferred; prediction configuration is unnecessary for descriptive exploration.
- Templates transfer definitions, not source rows, provider transcripts, training splits, coverage or availability attestations. Imports remain proposals. Ambiguous/missing/type-changed fields never bind by old column position. Hierarchy and value-grain exceptions are rechecked and blocked. Equivalent metrics reuse identities.
- Readiness describes executable operations, not ontology completion or exhaustive understanding. Session-owned caching avoids repeating eligibility work on every widget rerun.

## Bounds, privacy and replay

At most three distinct connected requests per upload; failed attempts count and completed exact requests are cached in that session. Each uses at most one Terra interpretation and one Jev batch. Jev reviews up to eight supplied definitions with separate support/scope questions, plus eight task-relevance questions. These limits are not a global owner spending cap.

Sources are at most 12,000 characters each and 16,000 total. Metadata packets are bounded to 42,000 serialized characters before wrapper/guidance. Optional candidates/witnesses are reduced explicitly. Up to two images use existing renderer budgets and matched records. Free-text column values are omitted from preparation; permitted summaries, selected identifiers/categories/numerical witnesses and explicitly supplied notes can be shared.

Drafts have at most 140 changes, 24 witnesses and 24 prioritized clarifications. Composite search tests at most twelve pairs of candidate identifier fields. Existing bounded relationship discovery remains; discovery is not exhaustive.

Evidence version 3 adds optional checksummed `profiles/preparation.json`. Source-backed import verifies illustrative values and numerical interpretation comparisons. Data-free import inspects records without providers. Preparation can contain private notes/source examples even without the original table; the export UI and privacy manifest state this. Replay never enables automatic preparation or restores a spending permission.

## Research and validation

Design foundations: contextual annotation in [Sato](https://arxiv.org/abs/1911.06311), ambiguity exposed at its point of consequence in [DataTone](https://cond.org/datatone.html), constraints versus preferences in [Draco](https://idl.uw.edu/papers/draco), the existing [summarizability framework](../research/semantic-contract.md), [task validity](../research/task-validity.md), and TypeSafe's [software-control guidance](https://docs.typesafe.ai/concepts/how-to-build-with-system-one). These motivate patterns; they do not validate this combined workflow or a productivity multiplier.

Regression coverage includes independent numerical alternatives; dependency expansion/rollback; stale edits; source/parser scope; literal citation/unit boundaries; provider failure/cancellation; request deduplication/budgets; reordered/type-changed template fields; hierarchy drift; temporal-attestation exclusions; undo; embedded metadata; temporal metrics; matched visual assets; source/data-free evidence; native review/context/reuse controls; and local exploration during preparation. Controlled official SDK transports check actual outgoing requests and structured responses without paid calls.

Run `python -m scripts.preparation_smoke --url http://127.0.0.1:8770` against a development-only Streamlit agent server. It exercises actual confirmation, undo, context input, prepared metric execution, evidence exports and session templates without screenshots or paid calls. Final results are in the current implementation context.

Future evaluation should measure human answers, time to a useful view, correction rates, valid analytical coverage and provider cost/latency. No user study or measured 10× gain was performed.
