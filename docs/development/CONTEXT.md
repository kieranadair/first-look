# Current implementation context

Updated 23 November 2026 after the UI refinement of First Look 0.3. Read [UI refinement](ui-uplift.md) for current presentation, review sources and validation.

## Product and architecture

First Look is a Python-only open-source visual investigation workbench. Eight visible native Streamlit work areas and a hidden linked Inspect finding detail route: Understand, Meaning, Explore, Findings, Compare, Models, Challenge, Evidence. The original `discover.py` path remains the Findings page. Python 3.12, Streamlit 1.67. Runtime requirements are pinned; Pint is the only added runtime dependency in this uplift. No SaaS/account/database layer, local foundation-model weights, authored frontend or data lineage system.

`firstlook/semantic_contracts.py` defines the scoped semantic model. `firstlook/semantic/profile.py` performs bounded exact structural discovery and heuristic proposals; `model.py` validates/commits/imports declarations; `policy.py` evaluates operation permissions; `planner.py` shares metric plans and bounded metadata packets; `engine.py` executes the typed algebra; `checks.py` compares definitions. Existing numerical discovery and diagnostic views remain available while business decisions are unresolved.

Dataset records include a semantic model scoped to the exact source fingerprint and parsing/physical-field layout. Meanings, metric definitions, entities, contextual hierarchy/membership evidence, time policies, assertions and focused clarifications participate in context identity. Changes invalidate dependent analyses and worker publication; source values are immutable. Pins retain the original context, field semantics and semantic-contract snapshot. Version 3 evidence bundles export the model, decision ledger, coverage, companion relationships and explicitly validated multi-context comparison boards. Version 1/2 bundles remain inspectable; plans without a recipe version report `legacy-recipe-inspection-only` instead of silently substituting the repaired algorithms.

Typed metrics: row and distinct-entity counts, sum, recorded/entity means and median, weighted mean, sum per distinct entity, ratios with explicit population scope, latest entity snapshots, cumulative-counter increments, degree-based circular means, and permitted post-aggregation transformations. Repeated entity values require constancy; overlapping entity totals need explicit full-credit/equal observed-membership attribution. Other and temporal summaries recompute source components. Sums of states/rates/counters and invalid log/unit domains are blocked.

Observed cadence is distinct from declared schedule. Structural zero requires confirmed event recording, coverage and last-complete date. Carry/interpolation is bounded and process-specific; explicit NULL is a barrier. Gap filling is disabled for arbitrary selected rows lacking scoped coverage. Counter resets remain missing and increments belong to the ending reading. No interval apportionment, holiday calendar or general missing-data imputation.

Jev receives the contract and ranks eligible views and clarification choices. Terra receives definitions, metadata, matched visual/table evidence and model protocol; it can propose typed semantic hypotheses for human selection and finite semantic checks for Python execution. Neither changes facts or permissions automatically. Models respect declared entity holdout and predictor availability, including post-outcome categories. No joint group/time protocol or causal interpretation.

A session-owned job manager runs expensive work outside reruns. Discovery retains twelve automatic findings; interactive working views are bounded at eighteen, with standalone pinned snapshots. Existing global/per-session worker limits and provider call budgets remain.

## Exploration and comparison layer

Read [exploration uplift report](exploration-uplift.md) and the linked design before extending it. The Section II chapter review is [research history](../research/few-part-ii-review.md); do not reimplement its completed suggestions.

`exploration_contracts.py` defines tasks, finite perspective coverage, separate numerical/display scope and cohort/reference contracts. `comparison.py` computes row/entity closure, explicit denominator/allocation populations, shared domains/category identities, full-source quantile/CDF effects and recorded-model slices. `exploration.py` owns seven finite recipes: group shape, density, influence, concentration, categorical facets, histogram sensitivity and temporal context. New calculations carry recipe version 2; no generated expressions/code execute.

Preview selection preserves the investigation, model and allowances. Compare computes two validated child contexts; only explicit filtering changes the working population. Return to reference restores the anchored investigation. Publication rejects stale cohort revisions even if the base context has not changed. Counter interval endpoints cannot be silently unioned into a row cohort. Comparison boards retain dataset/semantic snapshots and recorded model protocols across later meaning edits; original bytes and each saved parser/meaning scope govern recomputation. At most three saved boards plus an active board; comparison children share the 18-view working allowance.

Metric top-K ranks the requested quantity before creating Other. Group comparisons freeze identities/remainder membership and compare by keys. ECDF compression respects tied mass and certifies vertical error; reported quantiles, CDF distances and threshold queries use source values. Native/review renderers share endpoint extensions with no invented source members. Scatter statistics, visible points and review reductions have separate scopes. Conditional center/spread renders existing quartiles and screens variance-only patterns. Geometry guards exclude unsupported scalar prediction targets.

Explore, Compare and Models are separate pages under the user's latest instruction. Keep related evidence together; use compact headers, adjacent panels, visible definitions/support and short workflow guidance. Configuration can move into a secondary control after computation. Essential analytical views do not live in expanders. Models displays related diagnostic pairs and reuses recorded holdouts; no brush triggers a model refit. Python-only and native Streamlit/ECharts remain requirements. The user authorized screenshots for UI review on 23 November 2026; the earlier screenshot prohibition is superseded. Automated browser smoke scripts still avoid image capture.

Jev can prioritize a missing eligible distribution task using its existing decision call. Terra receives coherent companions and can review one selected/reference board per investigation, propose bounded child-context checks and synthesize them. The deterministic core remains complete without keys. Live provider effectiveness, Cloud availability and human productivity are unmeasured.


## Current interface

Read [UI refinement](ui-uplift.md) before changing layout. Pages use compact navigation-matched headings and a shared dataset/population strip. Understand starts investigation near the top; settings and dataset switching are secondary controls. Field editing and a visible field inspector share a row. Meaning places one open decision beside the quantity editor. Explore hides construction controls after a result exists. Findings is a gallery; its Inspect actions navigate to hidden `app_pages/inspect.py` so the detail opens at the top without duplicate charts or retained gallery scroll. Compare/Challenge keep related evidence together. Evidence provides top exports and a selected-pin note editor; all pins and their notes remain in the brief. Native navigation `help` explains each work area. Theme configuration, static wordmarks and native layouts own presentation; no custom frontend.

## Accepted user decisions

- Host repository root `streamlit_app.py` on Streamlit Community Cloud with Python 3.12.
- Owner credentials belong in server-side Cloud Secrets/environment variables. The user considered BYO keys, then chose owner keys and provider caps. No frontend or session-state key entry.
- Owner supplies Jev/TypeSafe, hosted TabPFN and OpenAI Terra credentials later. Dedicated keys/provider hard limits remain owner setup.
- Screenshots are authorized for UI review as of 23 November 2026. No user-testing gate, custom CSS or JavaScript frontend. Keep captures of bundled examples under ignored reports. Automated checks use AppTest, a localhost-only development agent API and image-free browser assertions.
- Publish as the open-source GitHub repository `kieranadair/first-look`. Deployment, research and future-session notes are separated. Do not commit secrets, uploaded data or live provider transcripts.

## Validation

Current suite: 175 tests passed, lint/format/type checks passed after the UI refinement. Controlled official SDK checks passed with no live provider calls. Real agent API tests cover original navigation/export and semantic metric execution/context invalidation. Browser assertions cover native chart selection/apply/reset/download, responsive light/dark layout and the semantic metric workflow. The earlier functional checks captured no screenshots/video/traces. The later UI review uses screenshots of bundled examples.

The current 50,000-row/20-field measured workload recorded approximately 3.6 seconds for discovery and 360 MiB peak process RSS on the declared local machine. These are not Community Cloud guarantees or a productivity experiment. That earlier version-0.2 validation of 13 version-1 outputs is historical; version 0.3 explicitly separates legacy inspection from current-recipe recomputation. Current exploration artifacts are under `docs/development/validation/exploration-*`; older semantic artifacts remain historical.  regenerate new measurements in ignored `reports/`.

Two upstream pandas 2.3.3 / NumPy 2.5.5 resampling deprecation warnings remain in the replay fixture. They do not affect the checked values; do not hide them or infer future-version compatibility. Production deployment configuration keeps the agent API disabled.

## Next useful work

1. Configure owner secrets/provider caps and explicitly run small live preflight calls. Do not claim live provider success from controlled SDK tests.
2. Deploy/update Community Cloud from root `streamlit_app.py` with Python 3.12. Actual Cloud availability is not verified by a local run or GitHub push.
3. Run matched text/visual Terra evaluation before claiming incremental model benefit. No measured 100× productivity claim exists.
4. Preserve exact dataset/parse scope, semantic permissions, source memberships and deterministic replay when extending the algebra. Add independent numerical oracles for new operations.

See [exploration uplift report](exploration-uplift.md), [semantic uplift report](semantic-uplift.md), [research-to-pattern mapping](../research/semantic-contract.md), [development commands](README.md) and [deployment guide](../../deployment/README.md). The original long specification remains design history.
