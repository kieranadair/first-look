# First Look — build report

Built 20 November 2026 as an open-source Python/Streamlit workbench. The source, runnable app, research register, licenses, example data, tests, provider adapters, replay tools and Cloud setup instructions are included in this repository.

## Delivered behavior

The four work areas connect table understanding, visual discovery, challenges and evidence. Users can correct semantic roles and ordinal order, set a focus and sampling assumption, inspect shared result artifacts, apply actual ECharts selections as a new context, and retain pinned evidence from earlier contexts.

Discovery covers distributions, cumulative distributions, category frequencies, numerical relationships, grouped distributions, category cross-counts, missingness, temporal means and conditional shape. The finite chart compiler supports bar, dot, histogram, ECDF, scatter, box, line and heatmap contracts. A bounded conditional-shape screen surfaces curved patterns whose signed correlation is weak. No selected-winner significance or causal conclusion is generated.

Challenges compute subgroup comparisons, extreme-value sensitivity, Pearson/Spearman differences, mean/median/spread comparisons, missing-value composition, optional exchangeability-gated diagnostic resampling, histogram bin changes, temporal aggregation changes and held-out error spread. Diagnostic views remain distinct from calculated changed/similar verdicts.

The model lens compares actual local dummy, regularized linear/logistic and histogram gradient-boosting models with optional hosted TabPFN, under row, group or time holdout. Exact target copies and two-field target components are excluded. Train-only preprocessing, class order, exact memberships, baseline metrics, accepted hosted fit identity and held-out predictions are recorded. Observed/predicted, residual, confusion and group-error views return to discovery.

The official TypeSafe SDK supplies Jev’s bounded option selection. The official TabPFN client submits and waits for hosted fits/predictions. The official OpenAI Responses SDK supplies structured Terra proposals, matched visual review, synthesis, question parsing and an optional field-meaning review. Field hypotheses require explicit selection to change semantics. Terra executes no generated code or arbitrary chart configuration. Python validates and computes eligible checks; numerical and causal assertions in generated interpretation are screened and remain outside measured observations.

The UI uses native Streamlit 1.67 elements, responsive grids, fragment polling, dual themes, local IBM Plex fonts and a constrained visual system. Application and test code are Python. There is no authored frontend, CSS injection, screenshot path or separate application service.

## Executed validation

| Check | Result |
| --- | --- |
| `python -m pytest -q` | **88 passed**, no warnings |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| `ty check firstlook app_pages streamlit_app.py` | Passed |
| `pip check` | No broken requirements |
| Official SDK controlled transports / hosted SDK boundary | Jev and OpenAI HTTP schemas, budgets, refusal, timeout, unauthorized/rate-limit/server errors, invalid choices and hosted output validation passed |
| Streamlit AppTest | Landing, example loading, semantic form, all four work areas and export passed |
| Development agent API | Real example → investigation → pin → Challenge → Evidence → prepare downloads passed |
| Python/Chromium browser | Actual ECharts mark selection, source-row apply/reset, evidence ZIP download, responsive cards and light/dark tokens passed; no console errors |
| Deterministic replay | Main results and completed checks match, including a fresh-process CLI comparison |
| Matched Terra packet harness | Six independent seeded reversal/nonlinear/null cases matched across text-only and image conditions; no live model ran |

Machine-readable results are in `validation/runtime.json`, `validation/browser.json` and `validation/benchmark.json`. The benchmark regenerates the example bundle in ignored `reports/`; redundant generated bundles and packet dumps are not versioned.

The browser checks use DOM, native event interaction, CSS and geometry assertions. At 1,440px the secondary cards use two columns; at 1,024px and 390px they use a single column, within the viewport. Theme contrast is calculated in tests. No live-app screenshots, browser video, traces or user study were taken.

## Measured performance

Reference environment: Linux x86_64, Python 3.12.14, three logical CPUs, approximately 9.73 GiB machine memory. Runtime versions are pinned and included in the JSON report. These are measurements of this environment, not a Community Cloud service guarantee.

Representative **50,000-row, 20-field** workload: approximately 7.63 MiB CSV, 12.49 MiB decoded analytical table. Measured load: **2.43s**; profile: **1.30s**; discovery: **4.49s**; leading challenges: **0.57s**; local baselines on the bounded 10,000-row model sample: **0.92s**. Peak benchmark-process RSS: **356.84 MiB**, below the proposed 600 MiB representative-workload target.

The smaller Penguins workload completed discovery in approximately 0.84s, export in 0.10s and deterministic replay in 0.19s. Two simultaneous example investigations completed in approximately 1.44s. The report also records ten repeated discovery passes. The nonlinear fixture’s local gradient-boosting held-out R² was approximately 0.966; this is a seeded software fixture result, not a claim about TabPFN or general real-world accuracy.

## Implementation decisions

- Use a lightweight deterministic profiler and explicit semantic hypotheses, rather than loading a heavyweight profiler, learned semantic model or local deep-learning weights into Community Cloud.
- Use `st.echarts_chart`, the verified Streamlit 1.67 API. The originally described `st.e_chart()` is not the implementation API.
- Keep source identity, role revisions, parser settings and row membership in the context hash. Native widget state is not the analytical record.
- Generate Terra images directly from matched result/chart contracts, with the same axis-domain policy and labels as the interactive view. Bounded image rows and text rows match exactly.
- Keep finite logical budgets and transport/poll timeouts; enforce a 360-second application deadline and two admitted workers. Cancellation cannot revoke an already accepted remote charge.
- Safe replay uses finite JSON/data artifacts and recorded outputs. No archived code, pickle or arbitrary query executes. Checksums detect changes, not authorship.
- Pin runtime roots and the resolved Linux/Python 3.12 dependency graph. Provide a separate development dependency file and CI checks.

## Credential-dependent and deployment work

**No live Jev, TabPFN or Terra calls were made.** Real adapters have been exercised through controlled SDK transports/boundaries. Account access, billing, actual remote model identity and service-specific success remain to be verified after owner credentials are configured. Run `python -m scripts.provider_preflight --live` for bounded live checks, then the explicit matched evaluation harness if desired.

The visual-reasoning uplift is a research-backed hypothesis with a reproducible evaluation harness, not a measured result of this build. Color/label sensitivity and the quality/cost of real model proposals require live evaluation. Semantic hypotheses, rankings and chart choices are conditional suggestions; the app does not recover unknown business meaning or establish causality.

Community Cloud configuration and deployment instructions are complete. **The app has not been deployed to Community Cloud.** Repository publication is tracked separately from this historical build report. Source credentials and owner keys are not available in this build. No paid subscription, SaaS infrastructure or account creation is required to use the local workbench.
