# Next uplift proposal: accurate, comparative and continuous exploration

Implementation status: delivered in First Look 0.3; see [build report](exploration-uplift.md) and [current context](CONTEXT.md). The user subsequently requested separate pages and compact comparison boards; that instruction supersedes the earlier placement recommendation. This document remains the detailed design history.

Design proposal, 22 November 2026. Baseline: First Look 0.2, commit `6f151db`. This document specifies a future build; none of the following runtime changes has been implemented in this review.

Research rationale and chapter assessment: [Few Part II synthesis](../research/few-part-ii-review.md). Verified synthetic audit results: [probes](../research/few-part-ii-probes.json).

## Product outcome and scope

An analyst should be able to obtain a useful overview, select something interesting, compare it with an explicit reference, inspect a complementary perspective and return to the original population without reconstructing the investigation. Every view must expose its actual population, estimand, support, approximation and search scope.

The change is a comparison-oriented experience **inside Discover**, not another application or a sixth mandatory setup page. Keep the existing shortlist and Model lens. Add an Overview organized by analytical perspectives and a Compare area that preserves a reference beside two or three related views. The person can still ask a named-metric question or explicitly begin a filtered investigation.

The semantic contract continues to answer what may be computed. The task specification answers what question is being asked. The comparison specification answers which definitions, populations and encodings must remain compatible. Models help navigate these choices; they cannot authorize an invalid computation.

The core must work without keys, in Python with native Streamlit/ECharts, on Community Cloud within the current upload/resource envelope. No authored JavaScript/CSS, live-app screenshots, lineage system, new heavyweight data engine, unrestricted expression language or user-testing gate.

## Delivery priority

| Order | Deliverable | Why it belongs in this build |
| --- | --- | --- |
| **P0: fidelity** | Correct metric top-K, ECDF compression/error disclosure, distinct statistical/display/review scopes and stable category keys; prevent unsupported geometry from silently choosing a model task. | Three reproducible representation defects and a contract-consistency gap precede feature expansion. |
| **P1: shared kernel** | Anchored cohort/reference comparison, exact population/denominator contracts, keyed comparisons and a common encoding manifest. | Several chapters converge on the same missing infrastructure. Without it, more charts repeat the context/scale problems. |
| **P1: exploration flow** | Finite perspective coverage, deliberate selection/compare/filter actions and small related-view bundles. | Makes the dataset understandable from different angles while retaining orientation. |
| **P1: useful witnesses** | Two-group ECDF/quantile comparison; conditional center/spread; explicit categorical marginals and a few facet companions. | These close demonstrated analytical gaps using the current numerical stack. |
| **P1: model integration and evidence** | Coverage/task-aware Jev options; coherent Terra packets; reuse of recorded predictive diagnostics; versioned comparison export/replay and independent evaluation. | Integrates the stack rather than leaving new views detached from the investigation. |
| **P2: follow-on recipes** | Semantic time-aggregation/calendar context, measured concentration, selected-pair influence and optional exact density. | Valuable, but secondary to the shared comparison foundation. Do not silently count them as core commitments if the narrower release is selected. |

Recommended scope: implement P0 and all P1 as one cohesive release. Time/concentration are the first follow-ons because they reuse the new kernel; influence/density follow measured need. Maps, parallel coordinates, clustering/embeddings, lag discovery, forecasting, inflation services and new causal modeling remain out of scope.

## 1. Representation and task correctness

### 1.1 Metric ranking and identity

Add a typed comparison intent/order to metric plans, not a widget-only reorder. Supported initial choices: recorded metric value descending/ascending; natural declared order; fixed reference order; frequency when the task actually asks for frequency. Evaluate all original eligible groups in the bounded family **before** selecting top groups by the requested quantity. Rank finite defined values, expose undefined groups and ties, then recompute Other from the omitted source union as today.

Retain structured category keys: field identities, typed values, parent/facet identities and an explicit synthetic-remainder flag. Labels are presentation only. A real label containing the join separator, or named Other, cannot collide with another group or the remainder. Persist selected/omitted original keys and counts. Define whether ranking refers to original or transformed values. Existing ordinal intent takes precedence where that is the selected task.

Do not promote extreme observed means/rates to reliable performance rankings. Show per-group support/exposure and undefined denominators. If a full group family exceeds the computation budget, return a reason or require a narrower question; do not claim a complete top-K from a convenient sample. Start with existing small automatic families and a measured bounded on-demand family. Exact caps are engineering policies to benchmark, not research results.

### 1.2 ECDF representation

Define the curve as right-continuous `F(x)=count(values≤x)/nonmissing_count`. Start with observation-rank/tie-aware compression that retains a subset of observed-value locations and their exact cumulative probabilities. Preserve endpoints and significant probability jumps. For this method family, independently checking every unique source threshold certifies maximum vertical error, with the curve extended by zero below the minimum and one at/above the maximum. Record that error, retained location count and tie convention. Any later method that introduces other jump locations must instead check the union of source and rendered jumps, including left and right limits and explicit endpoint extensions; a source-threshold-only check would not certify it.

Keep the current 1,200-mark engineering bound unless measurements justify changing it. If a tolerance cannot be achieved within that bound, label the achieved approximation/error and offer a narrower or exact threshold query, or decline that representation. Exact retained vertices do not justify describing the entire staircase as exact. Do not confuse display error with sampling uncertainty.

The native and analytical renderers must share the recorded step convention and vertices. Mark selection must say whether it denotes observations at a value, at/below a threshold or another supported predicate. Do not reinterpret the current exact-value row map as cumulative membership without an explicit operation.

### 1.3 Coverage of the numerical/statistical/display pipelines

Replace the overloaded sampled boolean with a typed scope description, preserving legacy reading:

- Eligible paired/valid source rows and missing/excluded counts.
- Rows used for statistics: full or sampled, exact membership or reproducible source reference, scheme and seed.
- Marks/aggregates used for display: counts, memberships, domain source, omitted rows or probability mass.
- Records/cells used for a Terra asset: exact plotted content and any further reduction.
- Selection semantics: what can actually be selected and whether source rows are members, contributors or dependencies.

A 6,000-row statistic with 5,000 plotted points must disclose both scopes. Domains intended to describe the full eligible pair cannot silently come only from the plotted sample. A rare omitted island must not fall outside an unlabeled sampled domain. A reduced asset and its table must match; never downsample aggregate cells independently after drawing the complete grid.

### 1.4 Modeling geometry and task eligibility

Use semantic quantity geometry when offering automatic model targets and validation recipes. Circular/coordinate/compositional targets must not silently enter ordinary scalar-error regression if that task/loss is unsupported. This is not a blanket ban on geographical predictors or all prediction involving those fields. Ask for a supported task or mark it unavailable.

Retain existing entity holdout and prediction-time availability. A spatial-transfer question requires an appropriate declared validation scope, such as validated supplied blocks, or an explicit unsupported result. Random spatial interpolation is a different task from predicting a new area. Do not invent spatial independence, CRS, geographic identity or a missing block definition. No geocoding calls are needed for this change.

## 2. New contracts

Names below are proposed Python/Pydantic contracts, not implemented public APIs. Reuse existing identities, hashing and `extra=forbid` validation. Store task/view recipes separately from business declarations in SemanticModel.

| Contract | Required meaning |
| --- | --- |
| **ExplorationTask** | Task family, question/goal, focus metric/fields, observation/value grain, base context, requested comparison and normalization, admissible operation IDs, recipe version and budget. A human title alone cannot determine these. |
| **PerspectiveCoverage** | Exact finite catalog/search scope; eligible, blocked with reason, outside budget, screened, computed, presented, explicitly opened/checked states; support and omission counts. Never call this percentage of all possible truths. |
| **CohortSelection** | Base context/revision; source result/mapping hash; selected marks/rows or supported predicate; row/entity selection policy; deliberate entity closure within the base; cohort revision; selection scope/limitations. |
| **ComparisonSpec** | Base/cohort/reference memberships; reference=whole or remainder; row/entity overlap; metric definitions; denominator/allocation population; permitted sensitivity versus same-estimand comparison; missingness and coverage policy. |
| **ComparisonManifest** | Structured category identities/order and Other membership; shared bin edges or quantile grid; series colors/roles; compatible numeric domains; transformation parameters/reference fit; approximation and support conventions; native/analytical renderer bindings. |
| **ComparisonBundle** | Anchored base result/context; selection/spec/manifest IDs; two or three compatible child results/contexts; checked exclusions; operations and evidence relations. Every child validates against its own exact recorded context. |
| **AnalysisScope / ReferenceSpec** | Statistical/display/review memberships and approximations; any reference line/band's source, unit, population, method and meaning. Targets, empirical ranges, confidence intervals and predictive intervals are distinct. |

A bundle is a bounded analytical artifact, not a data lineage feature. Do not weaken the existing global context checks to allow mixed contexts generally. Instead validate a bundle's permitted parent/child references explicitly.

### Cohort semantics that must be resolved

1. **Recorded rows versus entity closure.** Selecting a Furniture line is not automatically selecting every line in its order. If the person chooses whole orders, close the selected entity keys only within the anchored base population; disclose the expansion. Row-disjoint sets can still contain overlapping entities.
2. **Members versus contributors.** Group member rows can include missing amount/identity values. Show actual contributors and denominators separately. A selected aggregate is not fully selected merely because one member is selected; display an explicitly labeled membership fraction or compute its cohort value.
3. **Interval dependencies.** Counter intervals include both endpoint readings. Unioning endpoints of selected intervals can create unselected intermediate intervals. The starter comparison path should reject unsupported interval-cohort operations instead of silently deriving them from row union. Original counter views remain available.
4. **Anchored versus cohort-relative denominator.** A selected group's share of the original base is different from its share inside the selected cohort. Child context membership alone does not define this. Record numerator and denominator populations/components independently.
5. **Allocation population.** Equal allocation across entity memberships depends on which group family/population is used. Selection must not silently refit attribution shares. Keep anchored allocation or explicitly recompute a differently named quantity.
6. **Time coverage.** A whole-upload declaration does not establish arbitrary selected-row coverage. Preserve unknown gaps and existing refusal rules. Derived coverage for an exhaustive supported predicate would require a separately validated rule, not an exception added for convenient charting.

## 3. Interaction and display

### Overview

Reuse Discover rather than add a wizard. Present applicable perspectives: category contribution/exposure; quantitative distribution; time; quantitative relationships; categorical intersections; spatial applicability; data/meaning fitness. Display meaningful status/reason, not one chart for every combination. A dataset with no supported geography is not forced into a map. A field outside a screen cap is unexamined, not evidence of independence.

Retain the current ranked shortlist as a useful attention aid. Apply a selected focus before positional caps. A nonwinning eligible view must remain requestable. Do not equate eager tab rendering or a delivered card with a person actually reviewing it; record explicit actions honestly.

### Select, compare, filter

- **Select/preview:** capture exact membership in view state; preserve the base investigation, pins, context, provider budget and modeling allowance. No provider call and no model refit.
- **Compare:** compute a bounded selected-versus-remainder or selected-versus-whole bundle, with explicit overlap and denominator policy. Default to a disjoint reference only when row/entity meaning supports it.
- **Begin filtered investigation:** retain today's explicit context transition, invalidation and recomputation. This is a distinct action.
- **Clear/return:** remove or change selection while retaining the anchor. Meaning/parsing/base-context changes invalidate incompatible bundles.

Streamlit 1.67's ECharts selection state is read-only. Consume an event from one native chart and server-render selected/reference companions. Do not promise live synchronized brush geometry across widgets or attempt to set its Session State. Use native grids, tabs/forms, detail tables and explicit series styles. No custom frontend is required.

### Comparable encodings

Compare by structured key, never result-list position. Freeze the reference's category set, order and exact remainder membership. A new alternative winner can be reported as outside the fixed comparison; asking for a fresh ranking creates another task.

Use shared numeric domains when the task compares the same quantity on compatible transformations/normalizations. Different quantities or a deliberate shape comparison may justify independently labeled scales; same physical unit alone is insufficient to choose every scale policy. Fix histogram edges/origin for distribution comparisons. Bind categorical colors by identity. Display-standardization parameters must state their reference population; separately fitting z-scores to each cohort can hide the very difference being examined. Never confuse display transforms with train-only model preprocessing.

Expose per-group `member_rows`, valid value count, entity count, numerator/denominator, weight/exposure and period support where applicable. Unknown is not zero. Reference lines/bands must say whether they are business targets, empirical quantiles or another supported construction. Do not relabel a historical 90% range as a 90% confidence interval or a process-control limit.

## 4. Core analytical witnesses

### 4.1 Distribution shape

From an existing box/distribution, compare **two named groups** or a selected cohort/reference using corrected ECDFs and matched quantile differences. Keep the compact box and identify its existing min/max-whisker convention. Reuse the declared linear quantile estimator, group nonmissing denominators and units. Show missing and omitted support.

Compute reported two-group CDF distance from the full source CDFs over the union of their unique observed thresholds; derive quantiles from source values using the recorded estimator. Do not compute ranking statistics from independently compressed display curves. If a future statistic is itself approximated, disclose that separately from display error: the CDF-distance error is bounded by the sum of the two curves' certified maximum vertical errors.

A CDF distance or quantile difference is an exploratory effect, not a population test or a paired treatment effect. No automatic i.i.d. band for repeated entities/time. Use a documented bounded group-family screen alongside between-mean separation; do not enumerate every subgroup. Start with one meaningful pair per task and preserve swap/sign and unit-rescaling invariants.

Histogram sensitivity can reuse current charts, adding explicit width/origin and finite fallbacks rather than automatic KDE. Count, proportion and density remain separate recipes; density areas, not arbitrary heights, integrate to one. Do not declare a true number of latent modes.

### 4.2 Conditional center and spread

Reuse the existing quantile-bin records, but expose their q1/median/q3/counts and record bin boundaries/orientation. A band or compatible interval representation must consume these exact values in both renderers. Add a cheap spread-change screen alongside the median-range screen under the existing bounded pair budget; it is a candidate witness, not a calibrated independence test.

Retain raw-pair detail, absence/support and the finite-domain guards. A band across adjacent supported bins must not silently bridge unsupported gaps. Do not infer clusters or causes from widening branches. A conditional-mean predictor that shows no gain does not disprove variance-only dependence.

### 4.3 Categorical intersections

The existing small joint-count heatmap is useful. Preserve structured row/column keys rather than flattening them into one ambiguous label. Add explicit **whole population**, **within-row**, **within-column** and **within-cell metric** scopes through a typed marginal specification. `group` currently refers to the joint cell; it is not a row marginal.

For the existing recorded-row cross-tab, normalized modes should use the explicitly declared complete-pair population, with missing category pairs counted separately. This is different from a semantic active-population ratio whose denominator can retain unassigned grouping rows. Never silently exchange those definitions or infer a missing exposure from a case-only table. A zero observed intersection is not a declaration of structural impossibility.

For a matrix of counts, these scopes answer different questions. A rate such as profit/sales inside a cell is not a composition across cells. For overlapping distinct-entity membership, row/column shares may not sum to one; do not normalize them to manufacture closure. An independence-model diagnostic also requires a defined observation unit and assumptions; no automatic chi-square badge for arbitrary metrics or overlapping entities.

Start with a small shared-scale bar comparison of a few selected cells/levels, reusing the comparison manifest. Proposed first bounds: four facets, eight item levels and 32 intersections in the complete requested grid. Require that grid to fit; do not assign the flat view’s pooled Other to invented facet cells. Route an explicit two-category count question to the supported cross-tab operation; an ambiguous percentage request must clarify its denominator instead of falling back to one category’s frequency.

Conditional scatter facets can follow for two to four supported cells within the same rendering budget, not 64 independently scaled plots. Shared domains and visible support are part of the task, not optional cosmetics.

## 5. Follow-on recipes and scope cuts

| Recipe | Safe first form | Conditions / reason to defer |
| --- | --- | --- |
| Temporal aggregation/context | Expose D/W/MS sensitivity for semantic metrics through the existing time helper; keep actual dates and period completeness. A small calendar phase view is the next extension. | Preserve gap/series/grain guards. Daily sums versus monthly sums have different period meaning; do not compare list positions or interpret larger buckets as a changed effect. |
| Trailing smoother | A named mean of complete consecutive period aggregates beside the raw series, with full window required. | Start with approved sums/counts; do not smooth ratios by averaging rates, borrow selected-row coverage or call the line a forecast. Record delay, membership union and synthetic periods. |
| Calendar phase/subseries | Month-of-year or weekday view with chronological observations and explicit complete-cycle policy. | No inferred seasonality from a short or trend-only series. Cycle thresholds are engineering policies. Defer holiday/fiscal/DST/multiple-seasonality decomposition. |
| Common-baseline series | Two to four compatible series, common positive reference date/value and original units retained. | No unrelated first-observation baselines, offset units, implicit inflation/currency conversion or inherited group coverage. |
| Concentration | Cumulative contribution table over original eligible parts, using existing bars. | Verified positive nonnegative additive partition; exclude synthetic Other from the category count. No 80/20 law, power-law fit, negative net contributions or overlapping incidence. |
| Influence | One chosen pair; OLS-reference leverage/residual/deletion sensitivity with original rows preserved. | Guard rank deficiency/leverage≈1/perfect fits; model-specific inspection, not error identification or automatic deletion. |
| Dense-pair view | Optional exact bounded numeric count grid with source memberships and raw-point detail. | Existing categorical heatmap is not a numeric density-grid implementation. Preserve complete cells/table/edges and approximation disclosure; never assert genuine clusters from cells. |

These are not all required for the first comparison release. Do not implement each chapter's three suggestions mechanically. Shared state, numerical fidelity and core witnesses are the priority; extra chart families compete against that scope.

## 6. Model responsibilities

**Deterministic Python/profilers:** compute components, memberships, cohort closure, comparison domains/bins, CDF/quantile accuracy, task eligibility and coverage. Produce an interpretable evidence bundle even with no configured providers. Names/profile shape can propose a question, not business meaning or causality.

**Jev:** within the existing call cap, choose among complete eligible task/bundle/check options using focus, missing perspectives, support, cost and redundancy. An abstain choice remains valid. Its preference probability is not the chance that an analytical claim is true. Do not ask it to repair arithmetic or select a favorable validation protocol.

**Terra:** map a question to a finite task or a clarification; read coherent companion evidence rather than unrelated winners; propose a specific executable check and explain what would change the interpretation. Supply exact definitions, reference/cohort scopes, support/approximation and matched tables/images. A static asset cannot audit live UI quality. Extend operation schemas only after the executor exists. Keep numerical assertions bound to code artifacts and causal explanations as hypotheses.

**TabPFN/local models:** reuse existing recorded fits/held-out predictions for appropriately scoped diagnostic slices. A selected error cohort is exploratory, not a fresh unbiased evaluation. A child diagnostic must reference the original ModelRun/base context and its valid held-out row subset explicitly; do not relax model-context checks globally. No extra fit merely because a person brushes a chart. Scalar point prediction does not cover every distributional dependence. Forecasting requires a separate temporal pipeline, horizon, features, baselines and rolling-origin protocol.

**Human:** supplies business grain, legitimate exposure/reference, materiality and task, and chooses exact rows versus whole entities and anchored versus cohort-relative quantities. There is no exhaustive metadata gate before descriptive exploration.

Provider budgets stay as currently bounded. Core numerical operations launch no paid requests. Evaluate deterministic navigation, then Jev, then matched text/table versus identical-table-plus-image Terra. Use programmatic ground truth, not the proposing model, for correctness.

## 7. Implementation sequence and module map

1. **Fidelity fixtures and recipe versioning.** Add independent regression fixtures first, then implement P0 in `firstlook/discovery.py`, `semantic/planner.py`, `semantic/engine.py`, `modeling.py`, `visualization/compiler.py`, `visualization/review_assets.py` and scope displays in `ui/components.py`. Preserve old record inspection and explicit legacy recomputation policy.
2. **Contracts and comparison executor.** Extend `contracts.py`/semantic contracts as appropriate; add a focused `firstlook/comparison.py` for membership/population algebra and child planning. Reuse `semantic/policy.py`, engine, ingest/context hashing and existing source identities. Keep analytical work out of page functions.
3. **Workspace and jobs.** Extend `state.py` and `ui/runtime.py` with separate selection/bundle state and jobs identified by base context **and cohort revision**. Reject stale companions when selection changes without changing the base. Keep snapshots immutable and global/per-session admission limits.
4. **Discover/Challenge UI and render manifest.** Update `app_pages/discover.py`, `ui/components.py`, compiler and analytical renderer together. Upgrade current paired challenges to keyed comparisons and compatible domains instead of parallel ad hoc implementations.
5. **Core witnesses.** Add finite group-shape and conditional-spread operations; marginal/facet support in the metric planner/engine. Reuse existing operations whenever their semantics match. Update questions, challenge eligibility, hypothesis allowlists and rule references together.
6. **Coverage and model packets.** Add typed coverage bookkeeping in discovery/planner, expose it natively, and pass task/bundle evidence through `investigation.py` and the existing provider adapters. Preserve rejected/negative checks and budget exclusions.
7. **Evidence and release validation.** Extend evidence/replay for bounded multi-context bundle references, all manifests and recipe identities. Keep existing bundle formats readable, test fresh-process replay, benchmark within the current envelope, then run screenshot-free native interactions. No live-model or Cloud-availability claim follows from local tests.

Do not silently replace historical ECDF/top-K behavior while reporting byte-equivalent replay. New calculations need explicit recipe versions in plan identity. Legacy results can remain inspectable and either replay through a retained finite method or receive an explicit migration/not-recomputed status. A checksum or repeatable bad representation does not establish validity. No uploaded code, pickle or arbitrary query executes.

## 8. Independent acceptance suite

All items below are **future acceptance criteria**, not tests claimed to have passed in this research review. Preserve the current suite and source-backed semantic invariants.

| Area | Independently defined oracle / negative case |
| --- | --- |
| Metric top-K | Totals 40, 40, 1,000 with row counts 40, 4, 1: metric rank must name 1,000; with one named slot the remaining total is 80. Include ties, signed sums, undefined values, real Other labels, structured-key collisions and ordinal/reference order. |
| ECDF | Use sorted Python lists/bisect at every source threshold for the observed-location subset method, with explicit endpoint extensions. Include 1,199/1,200/1,201 distinct values, the 50,000-row high-mass-at-1199 fixture, ties, negatives and unequal gaps. Verify achieved error and exact threshold queries separately. Reject an invented jump location under that method; any supported generalized method needs union-of-jumps and left/right-limit verification. |
| Display scope | At 6,000 eligible pairs, all 6,000 may support the statistic while only 5,000 marks are plotted; record both. Review reduction has another exact scope. Include rare omitted islands and duplicate points. |
| Group shape | Pure shift, scale-only, equal-center/different-tail and crossing-quantile cases, missingness, unequal n and dependent rows. CDF distance and quantiles must match full-source oracles even when display vertices change. Swapping groups reverses signed differences; positive unit scaling preserves CDF distance. Any explicitly approximated distance must meet the sum-of-errors bound. |
| Conditional spread | ±x branches: flat medians/zero signed association but increasing known IQRs. Include constant-spread and permuted nulls, tied x, unsupported bins and both recorded orientations. |
| Cohort membership | Hand-enumerate repeated orders spanning categories: exact rows versus whole-order closure **inside base**, missing IDs, overlaps and valid contributors. Selecting a sampled point must not claim all records in its rectangle. |
| Interval membership | Counter readings 100,110,140,160 imply intervals 10,30,20. Selecting first and third intervals cannot create the middle interval from endpoint-row union. Correct interval semantics or explicit refusal passes. |
| Denominator/allocation | Distinguish half-base share from cohort-relative share; row disjointness from entity disjointness. Recompute weighted mean of values 10,20 with weights 1,3 as 17.5, not 15. Preserve anchored allocation or record a different definition. |
| Crosstab scopes | Counts `[[10,30],[20,40]]`: total 100; row totals 40/60; column totals 30/70. Verify joint/row/column fractions independently. Overlapping order membership and cell rates must not acquire forced 100% closure. |
| Comparable displays | Keyed comparisons survive label/row permutations. Same-quantity comparisons share intended domains/bins/colors; incompatible units/normalizations do not. Fixed Other membership cannot follow a reranked alternative silently. |
| Temporal follow-on | Unknown date stays unknown. Missing/partial window blocks a full-window smoother. For `2, 4, 8, 16, 32` the trailing three-period means are `missing, missing, 14/3, 28/3, 56/3`. An appended future point cannot alter an earlier trailing result. |
| Scope/state | Selection preview leaves base context/results/pins and provider/model counters intact; compare creates validated children; explicit filter creates another context; changed cohort rejects stale job results. Meaning changes invalidate all incompatible children. |
| Replay and models | Bounded bundle references import/validate/recompute in a fresh process with no provider calls. Recorded held-out slices stay subsets of the original test membership. Unsupported geometry/transfer tasks cannot silently choose an inappropriate target/protocol. |

Add metamorphic tests for row order, equivalent labels, units, column order and harmless presentation changes. Equivalent-source tests must redeclare fixture semantics for the new exact fingerprint/parse scope, not bypass scope validation. Column order need not leave IDs/hashes identical; mapped analytical coverage should not silently lose an explicitly selected focus. Declare the bounded task family rather than promising every pair/partition is examined.

A seeded evaluation should compare the existing shortlist, deterministic task/companion planning, and optional model variants under matched budgets. Include null data, small denominators, subgroup reversal, equal-center/different-spread, dense duplicates, missingness, unsupported causes and adversarial approximation cases. Measure useful nonduplicate evidence, prespecified pattern coverage, false promotion, omissions, abstention, unsupported claims, numerical error, latency and RSS. Functional correctness is not a measured human productivity gain.

## 9. Budget and release boundary

Preserve the current 50,000-row/80-field/25 MiB import limits, decoded-frame guard, twelve automatic findings, eighteen working views, global/session worker limits and provider budgets. Companion views count against working-view and retained-artifact limits. Reuse grouped component tables and source context; do not recompute an exhaustive cube or retain a new full dataset for every view.

Start with two/three companions, two-group distribution comparisons, up to four facets, and the existing 24 expensive pair-shape screens. Retain the 1,200 ECDF/time and 5,000 scatter display bounds with truthful approximation, not arbitrary extra sampling. Any on-demand density view should use a complete bounded grid within the existing review payload budgets. Exact defaults are engineering proposals to validate on this machine and deployment environment.

The previous release measured roughly 3.5 seconds for discovery and 358 MiB peak process RSS on its 50,000 × 20 fixture. Use the same workload and report exact scope; seek the same order of latency with bounded incremental comparison cost. No unmeasured Cloud guarantee or 100× productivity claim. If the narrower release needs a scope cut, retain all P0/shared-comparison/core-witness work and defer P2 recipes, rather than delivering more chart types with unresolved comparison semantics.
