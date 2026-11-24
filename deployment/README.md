# Deployment

Run and deploy from the repository root. Streamlit Community Cloud reads the root `.streamlit/config.toml`; keeping the runtime there avoids configuration and asset-path surprises. Research and session notes are not imported by the application.

## Community Cloud

1. Put this repository in your GitHub account, keeping `streamlit_app.py`, `requirements.txt`, `requirements-lock.txt`, `.streamlit/config.toml`, `static/`, `resources/` and `examples/` together at repository root.
2. Create a Community Cloud app from that repository. Entrypoint: **`streamlit_app.py`**. Select **Python 3.12** under advanced settings.
3. Deploy with no secrets to verify the local workflow. Add the owner credentials in Cloud Secrets when ready.
4. Keep the agent API disabled in production; the checked-in config does not enable it. No separate service, Node build or persistent disk is required.

A restart can end in-memory investigations or workers. Download bundles to preserve evidence. This is a shared open-source workbench with bounded concurrency; if the owner wants tighter public API spending controls, set `allow_external_analysis=false` or `provider_mode="offline"` and enable connected work in a controlled deployment.

### Confirming a deployed update

GitHub `main` and a passing CI run do not establish the code loaded by an existing Cloud process. In **About this workbench** in the sidebar, this release identifies itself as **First Look 0.5.0**, **Chart renderer: 2026-11-23.1**, **Judgment policy: 2026-11-24.1** and **Task policy: 2026-11-24.2**. The renderer marker is read from the loaded compiler module; an older imported module reports that a reboot is required. A missing marker means the entrypoint itself predates this diagnostic.

If the source button links to this repository's `main` but the app still shows older charts, preserve any work and use the owner workspace at `share.streamlit.io` → the app's overflow menu → **Reboot**. Alternatively use **Manage app → overflow menu → Reboot app**. A browser refresh or ordinary script rerun does not force a fresh server build. Follow the [official reboot instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app).

After rebooting, check the sidebar markers and start a fresh local Penguins investigation. The navigation includes **Text lab**, **Event lab** and **Judgments**. Meaning includes Task & availability; Models shows readiness before fitting. Asking a question in Findings shows an interpretation before its explicit execution. Scatterplots should have square inner axes, rotated y-axis titles and declared units in their axis labels. Their safeguards include the square-scatter rule. If the markers are still absent, check the deployed repository, branch, entrypoint and Cloud build logs before changing chart dimensions.

Count versus percentage is a separate analytical choice: single-population histograms/frequencies currently default to recorded row counts. Two-group frequency polygons use within-group proportions so unequal sample sizes do not dominate shape comparisons. Existing proportions are not raw counts labelled as percentages. Changing this default requires an explicit normalisation choice and recorded denominator, not merely appending a percent sign.

## Owner credentials

Copy `.streamlit/secrets.toml.example` to **`.streamlit/secrets.toml`** for local use, or paste its contents into **Community Cloud → App settings → Secrets**. The example contains placeholders only; placeholders never enable a provider.

```toml
[providers]
typesafe_api_key = "REPLACE_WITH_TYPESAFE_API_KEY"
typesafe_model = "jev-latest"
tabpfn_token = "REPLACE_WITH_TABPFN_TOKEN"
tabpfn_model_path = "auto"
openai_api_key = "REPLACE_WITH_OPENAI_API_KEY"
openai_model = "gpt-6.1-terra"
openai_reasoning_effort = "medium"

[app]
provider_mode = "auto"
allow_external_analysis = true
terra_visual_review = true
```

Environment variables override provider secrets: `TYPESAFE_API_KEY`, `TYPESAFE_MODEL`, `TABPFN_TOKEN`, `TABPFN_MODEL_PATH`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_REASONING_EFFORT`. `FIRSTLOOK_PROVIDER_MODE=offline` disables every provider even if keys exist. `auto` and `live` make configured integrations available; execution still requires an explicit action and the dataset’s **Allow external analysis** choice. There are no visitor API-key widgets or mutable per-visitor provider credentials.

In the app, open **Understand → Investigation settings → Allow external analysis for this dataset**. To request a connected pass after the local overview, use **Findings → Investigation options → Investigate with connected models**. The sidebar reports configured credentials; it does not establish successful authentication. Models provides the separate hosted TabPFN evaluation controls.

| Component | Receives | Responsibility |
| --- | --- | --- |
| Local Python | Source table and user corrections | Profiles, eligibility, statistics, splits, metrics, chart contracts and checks |
| Jev / TypeSafe | Task-specific metadata, eligible candidates and criteria; source text only after separate text permission | Atomic applicability, intent, relevance, note-evidence, text-coding and claim support/scope judgments; Python owns decisions and permissions |
| Hosted TabPFN | Permitted training values/labels and held-out predictors | Predictions under the recorded split; no local weights or GPU |
| Terra / OpenAI Responses | Field summaries, bounded plotting tables, chart contracts and up to three matched chart images; optional eight text-only examples without target values | Suggest questions, propose eligible checks and frozen text-feature definitions, reconcile computed evidence; no code execution |

Terra’s images are generated **offscreen from analytical contracts**. They are not screenshots of the app. The text-only comparison receives identical underlying plotting data. Model prose is labeled interpretation; unverified numerical or causal assertions are omitted. Evidence exports record requested/resolved models, packets, usage, decisions, rejected proposals and asset hashes. Provider data retention follows the configured service/account; `store=False` is sent to OpenAI, not a promise about every provider’s retention.

Use dedicated provider keys/projects for this public app and provider-enforced spending/request caps. Verify whether each limit is a hard cutoff or an alert. Visitors can consume the configured account quota without seeing its key. Per-session limits do not impose a global monthly spending cap.

No additional keys are needed for the new workflows. Text lab requires both dataset external-analysis permission and its separate **Allow sharing this dataset's selected text** checkbox. The page previews rows, questions and request/input bounds before coding. Limits are six frozen features, 240 rows, 2,000 characters per text, two coding experiments and two matched model experiments per context. Empty, overlong and unresolved rows are reported separately. Standard Jev jobs allow at most eight requests, 256 questions and 384,000 conservative input-budget bytes; text coding has a separate maximum of 64 requests, 1,440 questions and 2,000,000 input-budget bytes. Every request is additionally bounded to 40 questions and 48,000 serialized-input bytes. These are application guardrails, not provider billing quotes or global spending limits. See [analytical conventions](../docs/ANALYTICAL_CONVENTIONS.md).

You can inspect the Judgments library, local question routing and labelled baseline without keys. Live calibration remains a separate, explicitly authorized development step: `python -m scripts.evaluate_judgments --live --allow-paid-requests` sends up to seven bounded example requests. Ordinary inspection and evidence replay make no provider calls.

Event lab preparation and its local baselines need no new keys or runtime packages. Hosted evaluation uses the existing TabPFN credential and dataset permission, after a successful deterministic preflight. It permits two preparations and two model evaluations per context, with one final evaluation per frozen task. Derived tables contain entity keys, history and outcomes; exported evidence can include them even without original-file inclusion. Data remains session-scoped and downloadable; Community Cloud restarts can discard it. Keep the production agent API disabled.

Keys belong in Cloud Secrets, not source code, browser storage or frontend session variables. The application uses one owner credential set; BYO visitor credentials are not enabled. Keep actual `.streamlit/secrets.toml` and `.env` files out of Git.

## Clean deployment artifact

```bash
python -m scripts.package_deployment
```

This creates `dist/first-look-deployment.zip` containing only application code, runtime requirements, configuration, licensed assets, notices and a checksum manifest. It excludes development tools, research, working context, generated reports, caches and actual secrets. Extract and run from the archive root. The regular GitHub repository can be deployed directly; the artifact is an optional runtime-only handoff.
