# Semantic-contract uplift — First Look 0.2

Completed 22 November 2026. The request was to make the existing utility substantially more powerful through semantic automation. This release replaces isolated tags with an executable contract shared across profiling, metric algebra, visual analysis, clarification, model evaluation and replay. The requested 100× ambition is not presented as a measured result.

## What changed

- Added Meaning, a native workspace with a focused decision queue; quantity/unit/transform and prediction-availability declarations; composite entity/row grain; contextual hierarchy and overlapping membership inspection; typed metric builder; observation policies; exact-dataset contract exchange; optional Terra semantic hypotheses with explicit batch confirmation.
- Added bounded automatic entity, dependency, overlap, repeated-value, composition and cadence checks. Observed properties and naming heuristics remain distinguishable from explicit business declarations. Repeated entity values can propose a deduplicated total, without declaring equality to be business meaning.
- Added a conditional metric compiler. Unconfirmed totals and entity averages wait for meaning/definition; invalid role, state/rate arithmetic, entity constancy, overlapping attribution, weight, unit and transform domains block execution.
- Added reusable sums, distinct counts, weighted means, entity averages, ratios, snapshots, counter increments, circular means and post-aggregation transformations. Ratios use original components and positive recorded denominators; missing/zero denominators remain undefined. Other recomputes from source memberships rather than averaging displayed statistics.
- Added event/instant/state/cumulative observation policies with schedule, series grain, coverage and bounded gap handling. Explicit NULL does not become a synthetic observation. Arbitrary selected rows do not inherit whole-upload fill coverage. Missing meters are not zero consumption; counter resets remain unknown.
- Integrated semantic metric candidates with the diverse shortlist and named-metric question resolution. Ambiguous business averages request a definition. Added automatic/manual reconciliation, averaging-unit, denominator and gap-policy challenges. Active interactive views are bounded without discarding pinned snapshots.
- Shared the contract with Jev and Terra. Jev prioritizes valid views and unresolved questions; Terra proposes typed metadata and evidence-linked semantic checks. Python executes and validates. Existing budgets and no-generated-code boundaries remain.
- Enforced declared repeated-entity predictive holdout and prediction-time availability for both local baselines and hosted TabPFN. Protocols record semantic revision and group constraint.
- Added version 2 portable evidence, contract and decision ledgers, historical pin snapshots and saved-evidence inspection after current analysis invalidation. Genuine version 1 replay was tested against the previous committed build.
- Added the retail example **Orders aren’t rows**. The seeded generator supplies known declarations so the app demonstrates several analytical units, repeated totals, overlapping groups, weighted prices, recomposed margin and complete event coverage without keys.

## Architecture and research

Runtime module responsibilities are in [CONTEXT.md](CONTEXT.md). [Semantic research synthesis](../research/semantic-contract.md) maps academic findings and industry practice to implemented patterns, tests and limits. The in-app rule registry links semantic constraints to primary sources and real test functions. Runtime remains Python-only; native ECharts, grids, forms, tabs, fragments, navigation, download controls, IBM Plex and dual themes preserve the existing visual language. Pint 0.25.3 adds unit/offset checking; no heavyweight profiling engine or local model weights were added.

Source raw bytes, parser options and physical field layout scope the contract. A change in meanings, grain, metric definition, time policy or predictor boundary changes context identity. Numerical artifacts, charts, model decisions and replay consume the same definitions. There is no lineage feature.

## Verification

- 125 tests passed, including independent known-answer semantic oracles, AppTest and controlled official SDK integrations. Lint, formatting and static type checks passed; resolved dependencies have no broken requirements.
- Agent API runs exercised the original workflow and the semantic workspace, computation, checks, export and invalidation. Browser tests exercised real chart marks/selection, responsive light/dark layout, semantic controls and downloadable evidence. No live-app screenshots, video or traces were produced.
- Genuine version 1 bundle generated with commit 6a94bdc: all 13 recorded outputs/checks recomputed identically in version 0.2.
- Measured representative 50,000 × 20 workload: about 3.5 seconds for discovery; about 358 MiB peak process RSS. Consult the checked-in report for exact machine, workload, timings and scope. This is not a Cloud capacity guarantee or a user productivity result.
- Runtime deployment ZIP uses the existing allowlist and includes new semantic modules, page, rules and Pint requirements. Context/research notes and tests remain outside the runtime bundle.

Reports use synthetic/public fixtures and contain no owner credentials or uploaded user data. Two upstream pandas/NumPy resampling deprecation warnings remain visible in replay tests. Paid endpoints and actual Community Cloud availability remain unverified pending owner setup; controlled transports are not represented as live calls.

## Intentional boundaries

One table; no joins/entity resolution/lineage, general ontology reasoning, SQL/expression execution, causal inference, interval allocation, holiday calendars, joint group/time holdout or currency conversion. Exact dependencies describe this upload. Equal attribution is a declared convention. Human declarations do not constitute authenticated authorship. Ratios compose untransformed components and do not nest temporal snapshot/counter metrics. Arbitrary dimensional transformations still require an appropriate known reference interpretation. Supported algebra can be extended with independent oracles; no inferred probability can bypass validity.
