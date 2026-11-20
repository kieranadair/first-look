# First Look

**An open-source workbench that finds, challenges and preserves a first understanding of an unfamiliar dataset.**

Drop in a table. First Look profiles it, proposes field meanings, builds a focused visual investigation, challenges tempting patterns, and brings held-out predictive diagnostics back into the same evidence trail. It runs locally without API keys. Configure Jev, hosted TabPFN and Terra to connect decision-making, foundation-model predictions and visual reasoning.

Built entirely in Python on Streamlit 1.67’s native ECharts, responsive grids, fragments, navigation, editable tables, Mermaid and dual themes. IBM Plex typography, locally served fonts, a restrained blue/teal palette and clear evidence cards make the interface feel like an analytical workspace.


## Run locally

Use **Python 3.12**, from this repository’s root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open the URL printed by Streamlit. No keys, account or external request is needed for local analysis. Start with **The hidden reversal** to see a strong pooled relationship change direction within recorded groups, or **Beyond a straight line** for a pattern correlation can miss.

## Workflow

1. **Understand** — open CSV or Parquet; inspect missingness, ranges and levels; correct roles, order and units; describe the table’s grain and sampling assumptions.
2. **Discover** — compute a diverse shortlist, including conditional shape; ask a supported question; inspect the quantities and research behind a chart. Select actual marks to preview and explicitly apply source rows.
3. **Challenge** — compare groups, extremes, rank correlation, binning, aggregation, missing-value composition or held-out error spread. Negative, changed and insufficient results remain evidence.
4. **Evidence** — pin findings and checks, add notes, reorder a brief and download an investigation bundle. Reopen it without calling a model; recompute deterministic results from the exact source data.

The **Model lens** compares dummy, regularized linear/logistic, gradient-boosting and optionally hosted TabPFN predictions under an explicit row, group or chronological holdout. Target-copy and exact component leakage are excluded. Numerical preprocessing is fit on training rows. Observed/predicted, residual, confusion and group-error views use held-out rows only. A hosted model that loses to a baseline remains visible.

Connected mode runs one visible suggested model protocol, Jev’s constrained view choice, and Terra’s proposal–check–synthesis loop. The focus and split appear before execution. Choose a different protocol in Model lens. A provider failure preserves completed local work. The optional Terra field-meaning review proposes validated roles; only explicit user selection changes active semantics.

## Documentation

- [Deploy to Streamlit Community Cloud](deployment/README.md) — runtime files, owner secrets and usage caps.
- [Development and validation](docs/development/README.md) — tests, evaluation tools and recorded measurements.
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
