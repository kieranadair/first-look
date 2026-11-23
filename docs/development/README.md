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
```

The provider tests use the **real official SDKs** with controlled HTTP transports or a controlled hosted-SDK boundary. They do not present fixtures as live models. Once keys are configured, `python -m scripts.provider_preflight --live` makes small billable smoke calls. `python -m scripts.evaluate_terra --live --seeds 17` runs a recorded matched text/visual evaluation; inspect correctness, check yield, contradictions, abstention and cost before claiming visual-model uplift.

For a real runtime/browser check, start this **development-only** server in one terminal:

```bash
streamlit run streamlit_app.py --server.port=8765 --server.address=127.0.0.1 --server.enableAgentApi=true
```

In another terminal, from the repo root:

```bash
python -m scripts.runtime_smoke
python -m scripts.semantic_smoke
python -m scripts.exploration_smoke
playwright install chromium
python -m scripts.browser_smoke
python -m scripts.semantic_browser_smoke
python -m scripts.exploration_browser_smoke
```

The browser test verifies actual chart-mark selection, filtering/reset, downloads, responsive cards and light/dark tokens. It captures **no screenshots, video or traces**. Stop the development server after checking.

For an isolated check of all thirteen native chart templates, with no analyst session or agent API:

```bash
python -m scripts.chart_render_smoke
```

This command starts and stops its own localhost fixture (default port 8766), measures actual SVG plot geometry and histogram intervals at desktop/narrow widths, and verifies treemap source selection. It uses synthetic data and makes no provider calls. Generated fixtures, logs and the JSON report stay under ignored `reports/`. Install Playwright Chromium first; pass `--port` to use another free local port.

## Reference material

- [Current implementation context](CONTEXT.md)
- [Interface refinement and design rationale](ui-uplift.md), including the authorized screenshot review of bundled examples
- [Comparison/exploration uplift](exploration-uplift.md) and [build design](exploration-uplift-plan.md)
- [Chart design audit and provider policy](../research/chart-design-audit.md), with the deterministic/preference boundary and primary sources
- [Semantic uplift build report](semantic-uplift.md) and [research-to-implementation mapping](../research/semantic-contract.md)
- [Original design specification](specification.md), preserved as design history, not a second setup guide
- [Historical build report](build-report.md)
- [Recorded validation](validation/), retained for provenance; regenerate current results under ignored `reports/`
- [Research evidence](../research/evidence.md)

Runtime dependencies are pinned in the root requirement files. The root CI workflow runs lint, formatting, type checks and tests without live keys. Use `python -m scripts.pin_requirements` only after intentionally resolving and testing a dependency change.
