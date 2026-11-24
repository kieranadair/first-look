# Typed judgments and analytical workflow uplift

Build date: 24 November 2026. This implements the six agreed TypeSafe-skill proposals in First Look, retaining Python-only native Streamlit and Community Cloud constraints.

## Architecture and authority

Jev answers versioned, independently understandable Noul, Choice and Score questions. Python validates all answer identities/distributions, applies explicit per-question policies, revalidates operation eligibility and owns control flow. Confidence is recorded, not substituted for a correctness probability. Scores are rubric rankings, not statistical probabilities or effect estimates. Question probabilities are never multiplied under an independence assumption.

The existing legacy Choice adapter remains replay-compatible. New requests use task-specific state and a short trust boundary rather than universal chart-selection prose. Each batch records exact state, specifications, thresholds, requested/resolved model, usage, hash, outcomes and policy version. Missing/invalid answers or transport errors are provider errors, never false/negative judgments. Standard and text-coding jobs have independent finite request/question/input budgets.

## Deliverables

1. **Question interpretation:** Python supplies eligible fields and finite task candidates. Jev maps field names and task intent through atomic judgments and a companion applicability Noul. A saved interpretation is shown before execution, supports explicit correction, is scoped to dataset/semantics/population and is revalidated when executed. Local interpretation and direct controls remain available without keys. Unsupported requests and unresolved mappings request clarification; they never become a nearest available operation silently.
2. **Consequential clarifications:** compute dependencies on unresolved meanings and show affected metric eligibility. Offer isolated, labelled hypothetical row/entity weighting or quantity interpretations where meaningful. Copies never confirm the active contract. Alternatives record their explicit assumptions and do not establish truth, exposure or recording completeness. Jev can assess supplied notes for evidence relevant to the selected decision, with citations retained as source text rather than automatically confirmed metadata.
3. **Text lab:** versioned binary questions with concrete yes/no criteria, manually entered or proposed by Terra using bounded text-only samples without targets. Explicit external permission and a preview identify rows, source field, bytes, questions and maximum requests before coding. Up to six features and 240 selected source rows; duplicate text can reuse an answer but retains all source memberships. Missing, overlong and unresolved inputs remain separate statuses. Rows are never silently turned into negative observations. The source dataset remains immutable. Exact values/coverage, cohort preview, independent overlapping features, CSV download and frozen-question predictive comparisons are supported.
4. **Claim review:** retain original Terra synthesis, split prose into bounded claims, attach exact cited evidence, enforce known IDs and reject unsupported numeric/causal assertions deterministically. Jev checks semantic support and scope against only that evidence. Claims without decisive support remain pending/flagged, not verified. Checked prose is displayed with review status; the model is an additional signal, not a numerical validator. Both ordinary and cohort reviews use this mechanism.
5. **Complementary evidence ranking:** score relevance of eligible candidates with anchored rubrics. Python combines this with computed novelty, support, coverage and cost; explain the component values and retain deterministic fallback. Rank finite supported challenges the same way. Strong correlation alone does not establish relevance or causal meaning. No chart rule, estimator or semantic permission is delegated.
6. **Judgments workbench:** inspect recorded question definitions, distributions, input scope, model/policy versions and code outcomes; compare records without paid re-execution. Export reusable definitions and records. Run a small synthetic, labelled offline evaluation pack and optional owner-authorised live evaluation via CLI. Check unsupported cases, ambiguity, option-order identity, irrelevant text and abstention. Report measured cases/accuracy/coverage/cost separately from model confidence and avoid productivity claims.

## Text-feature modeling protocol

Feature questions are frozen before predictive evaluation. Terra's proposal receives neither target values nor held-out errors. No automatic feature-search loop tunes against the final test set. The first implementation compares original permitted predictors against original-plus-coded features using exactly matched held-out memberships; hosted TabPFN is optional. Original group-holdout and predictor-availability declarations carry into the derived modeling table. A source text declared unavailable at prediction time cannot become an eligible derived predictor. Human confirmation of availability is required. Derived tables have their own source bytes, fingerprint, semantic contract and mapping to original row IDs; they are not appended to the original dataset under its old fingerprint.

Coding and analysis have explicit row/feature/call budgets and use the existing background job manager. Cancellation stops later batches; stale context results cannot publish. Predictor evaluation needs adequate labelled rows and class support and preserves negative results. Model-coded features are interpretations with coverage and unresolved values, never newly observed facts.

## State, UI and evidence

Use focused native forms and adjacent result panels. Definitions, interpretation, support, alternatives and essential charts remain visible; raw payloads belong in secondary inspect controls. Add Text lab under Investigate and Judgments under Preserve. Register context invalidation for prepared questions, text runs and jobs. Existing pinned evidence remains immutable. Export/import includes judgment definitions/records, claim audits, prepared question records and text runs. Loading evidence never calls a provider. Text-derived modeling snapshots remain independently inspectable and original source membership remains explicit.

## Validation and release

- Real installed SDK with controlled HTTP responses for all three primitives, mixed batches, invalid distributions/types/IDs, missing answers, question-order changes and budget failures.
- Independent known-answer tests for ranking, intent applicability, semantic alternative calculations and source immutability, text coverage/deduplication/membership, and matched predictive splits/leakage restrictions.
- Claim review cases covering uncited, contradicted, unchecked, quantified and causal claims, including provider failure and partial evidence.
- Evidence roundtrips, data-free inspection, malformed records and context invalidation.
- AppTest/native runtime checks for new pages, prepared-intent execution, Text lab controls and judgment inspection. No live provider calls in CI.
- Ruff, type checks, complete existing suite and runtime-only packaging. Push reviewed text files and the installed TypeSafe skill/license/lock to GitHub main with an expected-parent lease. GitHub publication is distinct from observed Community Cloud deployment.

## Sources

- Installed `.agents/skills/typesafe-ai/SKILL.md` and its recorded upstream commit in `skills-lock.json`.
- https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md
- https://docs.typesafe.ai/patterns/companion-noul.md
- https://docs.typesafe.ai/patterns/composite-scoring.md
- https://docs.typesafe.ai/cookbooks/verify_llm_outputs.md
- https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery.md
- https://docs.typesafe.ai/model-jaggedness.md

These are integration design sources, not independent validation of this application or a measured productivity gain. Existing Few/semantic research and all deterministic analytical contracts remain in force.
