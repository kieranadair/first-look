# Deployment

Run and deploy from the repository root. Streamlit Community Cloud reads the root `.streamlit/config.toml`; keeping the runtime there avoids configuration and asset-path surprises. Research and session notes are not imported by the application.

## Community Cloud

1. Put this repository in your GitHub account, keeping `streamlit_app.py`, `requirements.txt`, `requirements-lock.txt`, `.streamlit/config.toml`, `static/`, `resources/` and `examples/` together at repository root.
2. Create a Community Cloud app from that repository. Entrypoint: **`streamlit_app.py`**. Select **Python 3.12** under advanced settings.
3. Deploy with no secrets to verify the local workflow. Add the owner credentials in Cloud Secrets when ready.
4. Keep the agent API disabled in production; the checked-in config does not enable it. No separate service, Node build or persistent disk is required.

A restart can end in-memory investigations or workers. Download bundles to preserve evidence. This is a shared open-source workbench with bounded concurrency; if the owner wants tighter public API spending controls, set `allow_external_analysis=false` or `provider_mode="offline"` and enable connected work in a controlled deployment.

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

| Component | Receives | Responsibility |
| --- | --- | --- |
| Local Python | Source table and user corrections | Profiles, eligibility, statistics, splits, metrics, chart contracts and checks |
| Jev / TypeSafe | Metadata, candidate summaries and valid choices | Prefer a supplied option or abstain; cannot make an invalid chart valid |
| Hosted TabPFN | Permitted training values/labels and held-out predictors | Predictions under the recorded split; no local weights or GPU |
| Terra / OpenAI Responses | Field summaries, bounded plotting tables, chart contracts and up to three matched chart images | Suggest questions, propose eligible checks and reconcile computed evidence; no code execution |

Terra’s images are generated **offscreen from analytical contracts**. They are not screenshots of the app. The text-only comparison receives identical underlying plotting data. Model prose is labeled interpretation; unverified numerical or causal assertions are omitted. Evidence exports record requested/resolved models, packets, usage, decisions, rejected proposals and asset hashes. Provider data retention follows the configured service/account; `store=False` is sent to OpenAI, not a promise about every provider’s retention.

Use dedicated provider keys/projects for this public app and provider-enforced spending/request caps. Verify whether each limit is a hard cutoff or an alert. Visitors can consume the configured account quota without seeing its key. Per-session limits do not impose a global monthly spending cap.

Keys belong in Cloud Secrets, not source code, browser storage or frontend session variables. The application uses one owner credential set; BYO visitor credentials are not enabled. Keep actual `.streamlit/secrets.toml` and `.env` files out of Git.

## Clean deployment artifact

```bash
python -m scripts.package_deployment
```

This creates `dist/first-look-deployment.zip` containing only application code, runtime requirements, configuration, licensed assets, notices and a checksum manifest. It excludes development tools, research, working context, generated reports, caches and actual secrets. Extract and run from the archive root. The regular GitHub repository can be deployed directly; the artifact is an optional runtime-only handoff.
