# Typed judgments as an analytical workflow

First Look 0.4.0 · implemented 24 November 2026 · judgment policy `2026-11-24.1`.

This release implements all six agreed TypeSafe/Jev proposals. The [build plan](jev-uplift-plan.md) records the design and sources. The aim is to connect question interpretation, unresolved semantics, evidence discovery, text features and interpretation review through inspectable judgments, while keeping calculations and permissions in Python. The deterministic workbench remains usable without keys. No new dependency, frontend service or model weight download is required.

## What changed

| Workflow | Jev / Terra contribution | Python and analyst responsibility |
| --- | --- | --- |
| Ask a question | Jev judges catalog applicability, task and intended supplied fields/metrics | Show a proposed interpretation, permit correction, require explicit execution, revalidate exact scope and eligibility; preserve the local route without keys |
| Resolve consequential meaning | Jev judges whether supplied notes explicitly address one decision and selects a source passage | Compute affected metric eligibility, copy the passage verbatim, keep meaning unconfirmed; calculate isolated hypothetical quantities without editing the active contract |
| Derive features from text | Terra can propose concrete binary questions from bounded text-only samples; Jev answers frozen questions per source text | Analyst edits criteria and consents to sharing; code preserves every source ID, unknown status and distribution, computes coverage and compares exact matched predictive memberships |
| Review prose | Terra supplies at most six cited atomic claims; Jev separately judges evidential support and scope | Validate references, flag literal numerical/causal assertions and incomplete checks, withhold flagged/unresolved prose, retain original output and label model-supported prose as interpretation |
| Recommend complementary evidence | Jev scores relevance to an explicit goal with an anchored rubric | Validate candidates; combine relevance with computed family complementarity, support and cost; display components and retain deterministic order when relevance is unresolved |
| Inspect and evaluate | Recorded answers expose requested/resolved models and full distributions | Compare records without re-execution, export definitions, inspect developer-labelled cases and separate local regression results from optional live model evaluation |

## A coherent path through the app

1. **Understand** profiles a dataset and establishes the starting scope. The new **From words to evidence** synthetic example is available under More examples; it includes pre-resolution opening notes and repeated customer identities.
2. **Meaning** shows computed metric dependencies beside focused open decisions. Notes can be reviewed explicitly when Jev is available. **What if?** places two alternative quantity interpretations together, with computed output or a reason an operation remains ineligible. The original declaration is unchanged.
3. **Findings** prepares a question before computation. A visible panel names the interpreted operation, fields, metric and optional grouping. Correct and run it explicitly; the history records both the initial interpretation and executed correction. Unsupported or unresolved requests remain in need of clarification.
4. **Judgments → Recommendations** accepts an analytical goal and explicitly requests relevance review. Rankings expose model relevance, computed complementarity, support, cost and combined score. Eligible complementary views can join the existing investigation; they still pass normal plan validation.
5. **Text lab** separates definition, sharing/request preview, coding results and model evaluation. Up to six independent questions can all be true for one row. Its coverage table distinguishes yes, no, unresolved, missing and overlong text. Select a feature to see its criteria beside coverage and source examples, preview yes/no cohorts or download coded values with original source IDs.
6. **Text lab → Models** compares original permitted predictors with original-plus-coded features on the same final held-out rows. Optional hosted TabPFN uses the augmented protocol. This evaluates predictive utility of frozen questions; it does not establish causal explanations or validate every text label.
7. **Findings/Compare** expose claim-level review next to Terra interpretation. **Judgments** shows one question's criteria and full distribution together, exact state in a secondary inspection control, record comparisons and reusable question definitions.
8. **Evidence** preserves the new records and text/model protocols. Reopened bundles are inspectable without providers. Exports warn that raw model inputs can remain even when original-table inclusion is off.

These stages are actions, not an automatic cascade of paid requests on page navigation. Existing Explore, Compare, Models and Challenge capabilities remain available independently.

## Question design and code policy

`firstlook/judgment_catalog.py` centralizes task-specific wording. Inputs use descriptive paths and identities rather than positional choices. New requests carry only task-relevant state plus a short untrusted-data boundary; they do not repeat the legacy universal chart prompt. Choice routing has a companion applicability Noul so a high-probability selection cannot turn an unsupported request into an available operation.

`firstlook/judgments.py` records each question's criteria and policy, exact state/hash, full answer, requested/resolved model, usage and request latency when available. The adapter uses the installed TypeSafe SDK, including mixed Noul/Choice/Score requests. It rejects missing answers, unknown identities, mismatched question types, nonfinite probabilities and invalid distributions. Recorded outcomes are recomputed from recorded answers during import. Errors are surfaced independently of judgment values.

Default Nouls resolve yes at ≥0.7 and no at ≤0.3; the middle is unresolved. Choices also need a 0.15 margin between leading options. Relevance Scores use three descriptive levels and reject endpoint ambiguity rather than treating the expected score as certainty. Scores are ordinal engineering inputs, not effect sizes. No independence assumption combines question probabilities. These initial thresholds have not been calibrated against live application cases.

The ranking convention is `0.55 × relevance + 0.25 × family complementarity + 0.15 × support − 0.05 × cost`. Its components are inspectable engineering defaults. Dependency counts are actual defined-metric dependencies, not estimated information gain. A judgment cannot change an estimator, scale, denominator, chart permission, observed value or human declaration.

## Text features and evaluation boundaries

- The source table is immutable. Every coding run retains exact context, source field, source population, selected original row IDs, frozen definitions and source values. Repeated identical text can share one answer while all rows retain membership.
- The bounded initial slice is all rows up to the limit or a seeded sample (`20261124`). Up to 240 selected rows and six features are supported. Missing/empty or >2,000-character texts are not submitted and never become false answers. Unresolved answers stay explicit.
- A whole-plan preflight computes the same serialized state/question budget as execution. A plan that would exceed a batch or total limit is rejected before its first coding request. UI previews expose rows, requests, questions, character counts and excluded statuses; these are bounds rather than a provider price quote.
- Terra's optional proposal sees at most eight bounded text-only examples, never target values or held-out errors. Criteria are editable before they are frozen. There is no automatic feature-search loop against the final holdout.
- A derived modeling table has new source bytes, fingerprint, schema and an original-row mapping. Original field availability, declared entities and group holdout carry over. Source text unavailable at prediction time cannot produce an eligible predictor. Analyst confirmation of feature availability is additionally required.
- Baseline and augmented local models use identical training and final held-out memberships. Source text is excluded from the baseline; it is represented only by the frozen coded features in the augmented set. Missing, unresolved and overlong feature states are distinct categorical values. Results may reflect recording practices as well as predictive content.
- Each frozen run receives one final predictive evaluation. Negative or insufficient results remain visible; cohorts and repeated inspection do not refit models. Optional TabPFN does not replace the original-predictor baseline or hide weaker performance.

## UI, state and replay

Text lab and Judgments are separate native Streamlit pages. Related definitions, criteria, support and result charts are adjacent; only exact raw payloads and secondary settings use expandable inspection controls. Findings retains a gallery and its separate Inspect route. Meaning adds a focused fifth tab rather than stacking hypothetical controls into the main editor.

Prepared questions, feature proposals, coding/model runs, note reviews, scenarios and rankings participate in context invalidation and the existing worker publication checks. Filter/return preserves the anchored investigation's state. Existing immutable pins, comparison snapshots, cancellation and global worker bounds are retained. Preparing an Evidence download hashes all new result/ledger state so later coding or model results cannot leave the download stale.

Optional version-3 bundle extensions contain judgments, recommendations, question history, workflow and text runs. Import validates recorded answers against frozen questions, context identities, derived schemas and held-out memberships. Source-backed replay checks exact text and source membership. Data-free import remains inspectable, without claiming agreement with omitted source bytes. It never rejudges text or refits provider models. See [replay](../REPLAY.md) for the file list and privacy boundary.

## Limits and credentials

The existing server-side TypeSafe, OpenAI and hosted TabPFN credentials suffice. Text coding and proposals additionally require explicit per-dataset text sharing. The owner keys stay in Cloud Secrets/environment variables; no browser key entry or new credential surface was added.

Standard Jev instances allow eight requests, 256 questions and 384,000 conservative input-budget bytes. Every typed request is capped at 40 questions and 48,000 serialized-input bytes. Text coding has a separate 64-request / 1,440-question / 2,000,000-byte budget. A context permits two text proposals, two coding runs, two feature-model experiments, two note reviews and four explicit relevance reviews. Existing five-question, worker, timeout and Terra limits remain. Provider-instance/context limits are not global public-app spending caps. See [analytical conventions](../ANALYTICAL_CONVENTIONS.md) and [deployment](../../deployment/README.md).

## Validation

The full suite passes **260 tests**, including 28 new tests in `tests/test_judgments_workflow.py`. Ruff, formatting, type checking and runtime-only packaging are required release checks. Tests include:

- Actual installed SDK serialization through controlled HTTP for mixed primitives, malformed/missing responses, identity-preserving option reorderings and independent applicability gating.
- Whole-plan budget rejection before any request, text deduplication with original counts, explicit unknowns, frozen-answer reconciliation and unavailable-predictor rejection.
- Matched baseline/augmented train/test memberships and carried group boundaries; isolated semantic assumptions compared with a known-sum oracle and unchanged source contract.
- Claim citation/scope guards, unresolved/provider-error behavior, eligibility-preserving ranking, copied note passages and atomic rejection of invalid subgroup execution.
- Data-backed/data-free evidence roundtrips, tampered frozen-question rejection, context filter/return, new-page AppTest flows and stale prepared-download invalidation.

The development-only Streamlit agent API smoke passed on a fresh server: proposed interpretation before execution, explicit confirmation, Text lab, Judgments library, labelled baseline and evidence export. Its ignored report is `reports/judgments-runtime.json`; it uses no paid provider, screenshot, video or trace. The renderer is unchanged and the earlier thirteen-template geometry verification remains in the [chart audit](../research/chart-design-audit.md).

The seven-case **local** routing evaluation matched all developer labels with four actionable cases and three abstentions. This is a small regression fixture, not live Jev performance or probability calibration. The two existing pandas/NumPy resampling deprecation warnings remain visible. No live provider effectiveness, user productivity or Community Cloud deployment result is claimed.

Repeatable commands are in [development](README.md). The optional live evaluation requires `--live --allow-paid-requests` and a separately agreed budget; it has not been run for this build. Research and TypeSafe guidance motivate the design, while these tests establish implementation properties only.
