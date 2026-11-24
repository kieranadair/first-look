# First Look

**Get to know your data, follow a useful question, and keep an understanding you can explain.**

First Look is an open-source Python app for people who have a table they care about and some context about what it means. Upload your own CSV or Parquet file. Start with an immediate local view, explore related perspectives, check choices that could change an interpretation, and keep the evidence that matters.

The distinctive contribution is a visible connection between **meaning → calculation → comparison → interpretation**. Python calculates; optional AI helps suggest and reason; you supply context and own the judgment. Important friction stays visible—whether a value can be added, whether rows represent repeated entities, or whether a missing day can mean zero. Routine configuration and arithmetic stay out of the way.

## Start locally

Use **Python 3.12** from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

No account or API keys are needed for local analysis. The opening begins **“Hi, I’m First Look.”** Bring your own familiar data; there is no demo gallery or compulsory metadata questionnaire.

## The investigation

There are three destinations:

1. **Data:** open your table, see what was read, optionally supply your question and context, and correct a field role if needed.
2. **Investigate:** choose a useful perspective, inspect its definition and support, compare a selected population with a reference, and resolve consequential meaning beside the evidence. Optional connected assistance can suggest a next step. A predictive check is available when that would help your question.
3. **Record:** keep chosen views with their original definitions, add your interpretation or next question, and download a readable record and checksummed evidence.

**Define → plan → execute → reflect** is an iterative rhythm, not a wizard. Stephen Few's visual sensemaking perspectives inspire questions worth asking: variation across categories, measures, space and time; quantitative and categorical relationships; and several perspectives considered together. The app chooses bounded representations for those tasks rather than presenting a chart gallery. Related evidence stays together; essential definitions are visible beside it.

## What the instruments do

| Instrument | Responsibility |
| --- | --- |
| Local Python and automatic profiling | Preserve source values, identify usable roles, calculate summaries and eligible views, enforce analytical permissions and build reproducible results. |
| Native Streamlit ECharts | Show constrained, inspectable views with truthful denominators, square scatter regions and compatible comparison scales. |
| Jev / TypeSafe | Make narrow relevance or support judgments about supplied evidence; uncertainty stays unresolved. |
| Terra / OpenAI | Suggest interpretations, useful clarifications and allowed next views from bounded verified evidence; optionally reason over a matched analytical image and table. |
| Hosted TabPFN | Contribute predictions to one explicitly requested retrospective diagnostic under a fixed holdout, alongside actual local references. |
| You | Supply domain context, decide business meaning, choose what to investigate and explain what the evidence supports. |

Models cannot execute generated code, change a verified calculation, confirm business meaning or permit an otherwise invalid aggregation. Their prose remains an unconfirmed interpretation. Connected work is opt-in and bounded; no paid requests run on upload or ordinary reruns. Without services, exploration, comparisons and records remain useful.

## Hosting, privacy and limits

Deploy `streamlit_app.py` on **Streamlit Community Cloud with Python 3.12**. Owner API keys belong in Cloud Secrets or server environment variables. [Deployment and API setup](deployment/README.md) explains each service, exact names, sharing, request limits and spending controls. Existing V1 secret names remain compatible; no new service is required.

One table is bounded to **25 MiB, 50,000 rows and 80 fields**. Working investigations are held in the session; a restart can discard them. Download the record to preserve work. A source-free export still contains calculated values, supplied context and any recorded model packets. Inspect it before sharing. See [analytical conventions](docs/ANALYTICAL_CONVENTIONS.md) and [evidence inspection](docs/REPLAY.md).

## Development and research

V2 is a fresh implementation, with a deliberately small risk-based test suite. The previous application, its 327 tests and its research are preserved under [archive/v1](archive/v1/REFERENCE.md); V2 never imports that runtime.

- [Product specification](docs/v2/SPECIFICATION.md), [development plan](docs/v2/PLAN.md) and [essential tests](docs/v2/TESTS.md).
- [Contributor guidance](AGENTS.md).
- Preserved research: [Few's visual exploration](archive/v1/docs/research/few-part-ii-review.md), [chart practices](archive/v1/docs/research/chart-design-audit.md), [semantic contracts](archive/v1/docs/research/semantic-contract.md), [Terra](archive/v1/docs/research/terra-integration.md) and [evidence index](archive/v1/docs/research/evidence.md). These explain the research foundation; their historical feature descriptions are not the V2 specification.

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
ty check firstlook app_pages streamlit_app.py
python -m pytest -q
```

Runtime code lives in `firstlook/`, `app_pages/` and `streamlit_app.py`; configuration and licensed assets live in `.streamlit/` and `static/`. `tests/` and `.github/` are active development checks. `archive/v1/` is reference, and `reports/` holds ignored local review artifacts.

Application code is [Apache-2.0](LICENSE). Font, archived dataset, skill and dependency attribution appears in [third-party notices](THIRD_PARTY_NOTICES.md). No credentials or uploaded data belong in Git.
