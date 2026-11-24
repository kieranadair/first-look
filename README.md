# First Look

**An open-source workbench that finds, challenges and preserves a first understanding of an unfamiliar dataset.**

Drop in a table. First Look profiles its structure, builds an executable semantic contract, proposes reusable metrics, compiles valid visual analyses, challenges tempting interpretations, and brings held-out predictive diagnostics into the same evidence trail. It runs locally without API keys. Configure Jev, hosted TabPFN and Terra to connect decision-making, foundation-model predictions and visual reasoning.

Built entirely in Python on Streamlit 1.67’s native ECharts, responsive grids, fragments, navigation, editable tables, Mermaid and dual themes. IBM Plex typography, locally served fonts, a restrained blue/teal palette and clear evidence cards make the interface feel like an analytical workspace.


## Run locally

Use **Python 3.12**, from this repository’s root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open the URL printed by Streamlit. No keys, account or external request is needed for local analysis. Start with **The hidden reversal** to see a strong pooled relationship change direction within recorded groups, **Beyond a straight line** for a pattern correlation can miss, or **Orders aren’t rows** for declared retail metrics, overlapping membership and time policies. **From words to evidence**, under More examples, supplies synthetic opening notes for the connected Text lab.

## Workflow

1. **Understand** — open CSV or Parquet; inspect profiles; correct roles, order and units; set a focus and sampling assumption.
2. **Meaning** — review focused decisions about quantities, row/entity grain, hierarchies, membership, denominator populations, observation schedules and predictor availability. See which metrics depend on each decision, review supplied notes and compare isolated hypothetical quantity meanings. Define and exchange a contract for the exact table; hypothetical assumptions never confirm it.
3. **Explore** — see which perspectives were screened, computed or left unexamined. Open distributions, conditional center and spread, categorical intersections, concentration, influence, density counts or temporal context. Compare shapes using common-bin frequency polygons; switch validated contributions between ranked bars, cumulative shares and a treemap overview. Related views sit together with their scope and support.
4. **Findings** — browse the shortlist, ask a supported question, inspect and correct its proposed interpretation, then explicitly run it. Inspect definitions and select chart marks. Preview a cohort while retaining the reference, or explicitly begin a filtered investigation.
5. **Compare** — choose exact rows or whole entities inside an anchored reference. Compare with the remainder or whole population using fixed category identities, compatible axes and explicit denominators. Distribution curves and source quantile differences appear together on desktop. Save the board, query exact thresholds, or return to the original investigation after filtering.
6. **Models** — evaluate a declared predictive task. Inspect related held-out diagnostics side by side; cohort boards reuse recorded predictions without refitting.
7. **Text lab** — define or ask Terra to propose concrete binary questions about one text field. Freeze the definitions, preview sharing and request budgets, then let Jev code bounded source rows. Inspect unknowns and coverage, preview cohorts and compare original versus augmented predictors on identical held-out memberships, optionally with hosted TabPFN.
8. **Challenge** — test subgroup, extremes, influence, distribution, binning and time effects, plus alternative metric definitions. Compatible original/alternative views share axes and category identities. Changed and insufficient results remain evidence.
9. **Evidence** — pin results, preserve comparison boards with their original meanings, add notes and download a checksummed investigation. Reopen without a model call; recompute deterministic results from the exact source data. Recorded text inputs can remain in an export without the original table.
10. **Judgments** — inspect exact Jev questions, criteria, distributions, model versions, inputs and code outcomes. Explain goal-aware recommendations, compare recorded judgments, export reusable definitions and inspect the small labelled evaluation pack.

A sales amount, account balance, percentage, running meter and circular direction have different operational permissions. Missing days remain unknown by default; zero-filling needs an explicit complete event-recording declaration. Overlapping category incidence is not presented as a 100% partition. Repeated order totals are deduplicated at their declared value grain and require an attribution convention before grouping overlapping entities. A semantic edit invalidates dependent work while preserving pinned evidence.

The **Models** page compares dummy, regularized linear/logistic, gradient-boosting and optionally hosted TabPFN predictions under an explicit row, group or chronological holdout. Target-copy and exact component leakage are excluded. Declared repeated-entity boundaries enforce group holdout; fields unavailable at prediction time are excluded for every provider. Numerical preprocessing is fit on training rows. Observed/predicted, residual, confusion and group-error views use held-out rows only. A hosted model that loses to a baseline remains visible.

Connected mode runs one visible suggested model protocol, Jev’s constrained view and clarification choices, and Terra’s proposal–check–synthesis loop. The focus and split appear before execution. Choose a different protocol in Models. A provider failure preserves completed local work. The optional Terra field-meaning review proposes validated roles and typed semantic hypotheses; selected metadata hypotheses can be confirmed together. Models cannot grant an invalid operation permission. Optional comparison review gives Terra coherent companion evidence and lets Jev prioritize eligible checks, within one review allowance per investigation.

New Jev integrations use atomic Noul, Choice and Score judgments. Python decides whether a response is actionable, preserves an unresolved outcome and combines relevance with computed complementarity, support and cost. Terra's prose receives a visible claim-level support/scope review against cited evidence; a model endorsement is not verification. Text questions are frozen before predictive evaluation, with no automatic search against the final holdout. Live provider accuracy and productivity gains remain unmeasured.

## Documentation

- [Deploy to Streamlit Community Cloud](deployment/README.md) — runtime files, owner secrets and usage caps.
- [Development and validation](docs/development/README.md) — tests, evaluation tools and recorded measurements.
- [Typed-judgment uplift](docs/development/jev-uplift.md) and [implementation plan](docs/development/jev-uplift-plan.md) — the six integrated workflows, provider boundaries and validation.
- [Interface refinement and design rationale](docs/development/ui-uplift.md).
- [Exploration uplift: implementation and validation](docs/development/exploration-uplift.md) and [Few Part II research synthesis](docs/research/few-part-ii-review.md).
- [Chart design audit](docs/research/chart-design-audit.md) — all thirteen templates, sources, Python-enforced rules and separate Jev/Terra guidance.
- [Executable semantic contract: research, patterns and limits](docs/research/semantic-contract.md).
- [Research evidence](docs/research/evidence.md) and [Terra integration](docs/research/terra-integration.md).
- [Analytical conventions](docs/ANALYTICAL_CONVENTIONS.md) and [replaying evidence](docs/REPLAY.md).
- [Contributor/session guidance](AGENTS.md) and [current implementation context](docs/development/CONTEXT.md).

## Repository layout

| Location | Purpose |
| --- | --- |
| `streamlit_app.py`, `app_pages/`, `firstlook/` | Deployable Python application |
| `.streamlit/`, `static/`, `examples/`, `resources/`, runtime requirements | Runtime configuration and licensed assets |
| `deployment/` | Cloud setup and clean deployment-bundle instructions |
| `tests/`, `scripts/`, `.github/` | Development tools and CI |
| `docs/research/` | Research evidence and bibliographic indexes |
| `docs/development/` | Implementation specification, session context and historical validation |
| `reports/` | Ignored, regenerated local outputs |

Application code is [Apache-2.0](LICENSE). Data, fonts and dependency attribution are in [third-party notices](THIRD_PARTY_NOTICES.md) and [example data notices](examples/README.md). No API keys are committed.
