# Development

Run commands from the repository root with Python 3.12. Install development dependencies only in development; Community Cloud installs `requirements.txt`.


```bash
pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
ty check firstlook app_pages streamlit_app.py
python -m scripts.benchmark
python -m scripts.provider_preflight --offline
python -m scripts.evaluate_terra --seeds 17 82
python -m scripts.evaluate_exploration
python -m scripts.evaluate_judgments
```

The provider tests use the **real official SDKs** with controlled HTTP transports or a controlled hosted-SDK boundary. They do not present fixtures as live models. Once keys are configured, `python -m scripts.provider_preflight --live` makes small billable smoke calls. `python -m scripts.evaluate_terra --live --seeds 17` runs a recorded matched text/visual evaluation; inspect correctness, check yield, contradictions, abstention and cost before claiming visual-model uplift.

`evaluate_judgments` runs seven labelled routing cases against the local baseline by default; this is a developer regression pack, not a Jev accuracy claim. After obtaining permission, a budget and agreement about the example metadata sent using `TYPESAFE_API_KEY`, run `python -m scripts.evaluate_judgments --live --allow-paid-requests` for at most seven live Jev requests. The mixed Noul/Choice/Score adapter is exercised without live spending in the normal test suite. Reports stay under ignored `reports/`.

For a real runtime/browser check, start this **development-only** server in one terminal:

```bash
streamlit run streamlit_app.py --server.port=8765 --server.address=127.0.0.1 --server.enableAgentApi=true
```

In another terminal, from the repo root:

```bash
python -m scripts.runtime_smoke
python -m scripts.semantic_smoke
python -m scripts.exploration_smoke
python -m scripts.judgments_smoke
python -m scripts.task_validity_smoke --url http://127.0.0.1:8765
playwright install chromium
python -m scripts.browser_smoke
python -m scripts.semantic_browser_smoke
python -m scripts.exploration_browser_smoke
```

The browser test verifies actual chart-mark selection, filtering/reset, downloads, responsive cards and light/dark tokens. It captures **no screenshots, video or traces**. Stop the development server after checking.

The judgments runtime script checks the question interpretation/confirmation boundary, Text lab, recorded question library, offline evaluation and evidence export through Streamlit's real development agent API. It makes no provider calls or screenshots. Pass `--url http://127.0.0.1:8767` to use another local port. Restart the development server after changes to imported module exports rather than relying on stale in-process imports.

The task-validity runtime script prepares a synthetic event task, inspects preflight, evaluates actual local models, opens held-out diagnostics, checks recording coverage/task controls and prepares evidence downloads. Default port 8768; it uses no hosted provider. Plain pytest covers numerical and temporal invariants, including future-perturbation tests and legacy parsing replay. Installed third-party skill assets are preserved verbatim and excluded from app lint/formatting and deployment packaging.

For an isolated check of all thirteen native chart templates, with no analyst session or agent API:

```bash
python -m scripts.chart_render_smoke
```

This command starts and stops its own localhost fixture (default port 8766), measures actual SVG plot geometry and histogram intervals at desktop/narrow widths, and verifies treemap source selection. It uses synthetic data and makes no provider calls. Generated fixtures, logs and the JSON report stay under ignored `reports/`. Install Playwright Chromium first; pass `--port` to use another free local port.

## Reference material

- [Current implementation context](CONTEXT.md)
- [Automatic preparation: workflow, architecture and limits](preparation-uplift.md) and [build plan](preparation-plan.md). Run `python -m scripts.preparation_smoke --url http://127.0.0.1:8770` against a development-only agent server for its runtime check.
- [Task-validity uplift](task-validity-uplift.md), [plan](task-validity-plan.md) and [research-to-pattern mapping](../research/task-validity.md)
- [Typed-judgment uplift report](jev-uplift.md) and [build plan](jev-uplift-plan.md)
- [Interface refinement and design rationale](ui-uplift.md), including the authorized screenshot review of bundled examples
- [Comparison/exploration uplift](exploration-uplift.md) and [build design](exploration-uplift-plan.md)
- [Chart design audit and provider policy](../research/chart-design-audit.md), with the deterministic/preference boundary and primary sources
- [Semantic uplift build report](semantic-uplift.md) and [research-to-implementation mapping](../research/semantic-contract.md)
- [Original design specification](specification.md), preserved as design history, not a second setup guide
- [Historical build report](build-report.md)
- [Recorded validation](validation/), retained for provenance; regenerate current results under ignored `reports/`
- [Research evidence](../research/evidence.md)

Runtime dependencies are pinned in the root requirement files. The root CI workflow runs lint, formatting, type checks and tests without live keys. Use `python -m scripts.pin_requirements` only after intentionally resolving and testing a dependency change.
