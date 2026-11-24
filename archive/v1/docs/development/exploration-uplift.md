# First Look 0.3: comparative exploration

Implemented 22 November 2026 against application baseline `6f151db`. Research rationale: [Few Part II synthesis](../research/few-part-ii-review.md). Detailed design: [exploration-uplift-plan.md](exploration-uplift-plan.md). This report records the delivered build and supersedes future-tense placement decisions in that design.

## Delivered experience

Eight work areas separate preparation, investigation and preservation. **Understand** profiles the source and visibly asks what a row represents. **Meaning** owns operational definitions. **Explore** provides perspective coverage and finite analytical recipes. **Findings** retains the shortlist, questions and inspector. **Compare** anchors a reference beside a chosen cohort. **Models** owns predictive protocols and related held-out diagnostics. **Challenge** displays original/alternative evidence together. **Evidence** preserves observations and comparison boards.

The user's latest UI direction takes precedence over the earlier suggestion to put everything inside Discover. Related graphs occupy the same board, with visible population, denominator, support and approximation. On wide desktop a distribution comparison places selected/reference curves and source quantile differences together. Compact headings and secondary post-computation configuration preserve space. Native grids reflow on smaller screens. Expanders hold supporting research/technical details rather than the primary comparison. Visible purpose/action commentary introduces each workflow area.

## Analytical changes

- Metric-specific top-K evaluates original groups before selecting extremes. Other recomputes its source union; keys and synthetic-remainder flags distinguish identities, including a real category named Other. Natural, metric ascending/descending and frequency order are explicit choices.
- ECDF compression retains observed locations by probability ranks/tied mass and certifies maximum vertical error against source thresholds. Source quantiles, group CDF distances and exact threshold queries do not use compressed curves. Native and offscreen renderers share right-continuous endpoint extensions; virtual endpoints carry no source rows. The 1,200-vertex cap reserves room for those extensions.
- Scatter scopes separate eligible rows, statistical rows, visible points and review reductions. Source-derived domains retain omitted extremes. Reduced images and tables match. Aggregate cells and temporal intervals are never randomly discarded for review.
- Conditional summaries show medians and quartiles; a bounded spread screen recovers variance-only structure. Unsupported bins remain gaps. Group-shape proposals use supported contrasting groups, with full-source quantile/CDF effects and missing/omitted support.
- Categorical cross-tabs support count, whole-table share, within-first-category, within-second-category and descriptive independence residuals. Their denominator is complete recorded pairs, distinguished from a semantic active-population ratio. No automatic significance test is added.
- Finite recipes add a complete numeric density grid, chosen-pair OLS influence, original-part concentration, bounded metric facets, histogram width/origin sensitivity with count/proportion/density normalization, and temporal context. Facets use one scale and complete cells; density retains exact edges/memberships. No outlier is deleted automatically.
- Temporal recipes reuse the existing semantic engine: D/W/MS reaggregation, complete trailing windows, calendar-phase companions beside raw chronology, and common-positive-baseline series with compatible units/basis and original values. Unknown/partial observations remain explicit. Offset/unsupported units, independently chosen baselines and averages of rates are refused.

## Contract and state changes

Tasks, finite coverage, numerical/display scope, cohort selection, comparison specification, shared manifest and bundle are typed boundaries. Focus is applied before automatic field caps. Coverage records supported perspectives and budget omissions; it does not claim exhaustive dataset understanding.

Previewing preserves the current investigation and model. Comparing validates selected/reference memberships and child contexts independently. Exact rows differ from whole-entity closure inside the anchor; disjoint rows can share entities. Numerator/denominator populations and anchored entity allocation remain distinct. Unsupported counter interval cohorts are refused rather than inferred from endpoint unions. Explicit filtering preserves a returnable reference. Workers reject stale cohort revisions.

Saved boards retain their dataset/semantic snapshot and, when used, original predictive run. Evidence format 3 validates each permitted context reference explicitly and replays each board under its own parsing/meaning scope. Ordinary results retain strict global-context checks. Versions 1/2 remain readable. Unversioned historical calculations are inspectable and explicitly marked `legacy-recipe-inspection-only`; repaired methods are not presented as byte-identical legacy recomputation.

## Model integration

Python owns arithmetic, memberships, approximation and eligibility. Jev receives coverage and can choose an eligible missing distribution task within the existing decision call. Terra receives matched companion evidence, can propose executable checks and can review one comparison per investigation; accepted checks run in the relevant child's exact context. Generated numerical/causal assertions and unknown evidence references are rejected. Provider failure preserves numerical work.

Predictive slices reference original holdout membership and losses; no selection causes a refit or fresh-validation claim. Unsupported circular/coordinate/compositional targets cannot silently enter scalar regression. Human operational meaning, exposure, completeness, compatible reference bases and materiality remain necessary. Owner keys stay in server-side Secrets/environment configuration; no frontend key entry or new runtime dependency was added.

## Validation

175 tests pass, with lint, formatting and type checks. New cases use independently defined source/membership oracles: metric rank, tied probability mass, source CDF distance, conditional spread, denominators, allocation, entity closure, counter refusal, sparse cells, influence, temporal windows/cycles/baselines, stale jobs, model slices, context-preserving snapshots and fresh-process replay. Existing controlled official-SDK tests remain; no live provider was called.

The real Streamlit agent API exercises opening perspectives, adjacent companions, cohort preview, comparison, saving/export, explicit filtering/return and the dedicated Models page. Browser checks use DOM measurements, native charts and actual downloads; no screenshot, video or trace is captured. At **1440 × 900**, both cumulative charts occupy the same row (top approximately 515 px; bottom approximately 795 px), with quantile differences alongside. At 1024/390 px the boards reflow without horizontal overflow. No page errors or browser console warnings were observed in that check.

A seeded analytical evaluation covers ten variants each of linear, curved-center, variance-only and independent-null data. The reconstructed previous center/association screen finds none of the variance-only cases; the new shortlist contains a witness in all ten. Neither promotes a relationship in these ten null cases. These finite fixtures are not a general detection guarantee or a human-productivity study. The high-mass ECDF case improves maximum vertical error from **0.976** to approximately **0.00082**, matching the independent source oracle and reported bound.

The declared 50,000 × 20 workload measured approximately **3.6 seconds** for discovery and **360 MiB** peak process RSS in the benchmark process. This is a local workload measurement, not a Community Cloud guarantee. Two pre-existing pandas/NumPy resampling deprecation warnings remain in the replay fixture; numerical results pass.

Durable machine-readable records: [runtime](validation/exploration-runtime.json), [browser](validation/exploration-browser.json), [evaluation](validation/exploration-evaluation.json), [benchmark](validation/exploration-benchmark.json). Regenerated outputs belong in ignored `reports/`. Run commands are in [development guidance](README.md).

## Deliberate boundaries

Maps/geocoding, parallel coordinates, clustering/embeddings, automatic lag search, forecasts, inflation conversion, new causal modeling, unrestricted generated code and Part III SPC remain outside the approved uplift. No app screenshots, user-testing gate, lineage subsystem or custom CSS/JavaScript frontend was introduced. Live provider verification and actual Cloud availability still depend on owner setup. No measured 10× or 100× productivity claim is made.
