# Deploying First Look v2

The application runs from the repository root. It needs Python 3.12, server-side Python packages and Streamlit; no separate service, Node build, GPU or persistent database is required.

## Streamlit Community Cloud

1. Put this repository in your GitHub account. Create an app at [share.streamlit.io](https://share.streamlit.io/) using the intended repository and branch.
2. Set the entrypoint to **`streamlit_app.py`** and Python to **3.12** in advanced settings. Keep root `requirements.txt`, `requirements-lock.txt`, `.streamlit/config.toml` and `static/` intact.
3. Deploy. Without keys, upload, profiling, views, comparisons, local predictive references and records work locally in the server process.
4. Add the owner credentials to **App settings → Secrets** when ready. Paste the structure below or use the checked-in [placeholder file](../.streamlit/secrets.toml.example). Save and restart as prompted.
5. Verify the welcome screen, three destinations (**Data, Investigate, Record**) and sidebar release **First Look 2.0.0** after upload. A source link alone does not establish which release a running process has loaded.

The repository can be deployed directly. The archived V1 tree is not imported, discovered by active tests or installed as an application. For a runtime-only handoff, copy `streamlit_app.py`, `app_pages/`, `firstlook/`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`, `static/`, `requirements.txt`, `requirements-lock.txt`, `LICENSE` and `THIRD_PARTY_NOTICES.md`. Do not copy actual secrets. V1 packaging scripts remain historical and are not a V2 release command.

Keep Streamlit's agent API disabled in production. It is useful only for explicit local development review. Session memory is temporary: Cloud sleep, reboot or replacement can discard uploads, work and worker results. Ask users to download evidence they want to keep.

If Cloud has not loaded an update, preserve any work, check repository/branch/entrypoint and build logs, then use the owner dashboard's **Reboot app** action. An ordinary browser refresh cannot force a new server build. Follow [Streamlit's reboot guidance](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app).

## Configure the services

All three integrations are optional and independent. V2 keeps the existing owner secret names. Do not place keys in Python source, browser storage or visitor-editable state. There is no visitor BYO-key flow.

### 1. Terra through OpenAI

1. Open the [OpenAI API platform](https://platform.openai.com/), choose or create a project, and enable billing for that project.
2. Create a dedicated API key with the permissions needed for Responses requests. Copy it directly into the `openai_api_key` secret below.
3. Set `openai_model` to the Terra model identifier available to your account. The current application default is `gpt-6.1-terra`; model access is account-dependent. `openai_reasoning_effort` defaults to `medium`.
4. Set project budgets, alerts and available model/rate restrictions. Check whether a budget is a warning or a hard cutoff; do not assume an alert stops spending.

Terra receives field summaries, supplied question/context, the bounded active result table and allowed next-view candidates. If `terra_visual_review=true`, a supported view can include one offscreen analytical PNG with its matching table. This is an analytical rendering, not a screenshot of the app. Free-text column values and default identifier examples are omitted; deliberately selected result labels can still identify people or entities. Terra returns unconfirmed interpretations and hypotheses, not new verified measurements.

### 2. Jev through TypeSafe

1. Create or open your [TypeSafe account](https://typesafe.ai/) and obtain a service API key from its account/dashboard tooling.
2. Put the key in `typesafe_api_key`. Use `typesafe_model="jev-latest"` unless your account requires another available model identifier.
3. Configure the provider's available quota and request/spending controls for this application.

Jev receives a bounded evidence packet and explicit narrow judgment questions about relevance or support. Python retains the distinction between yes, no, uncertain and failed. A favorable judgment never confirms a business definition or grants aggregation permission. Jev and Terra can be enabled separately.

### 3. Hosted TabPFN through Prior Labs

1. Create or open a [Prior Labs account](https://priorlabs.ai/) and obtain the hosted TabPFN access token supplied by its API/client onboarding.
2. Put the token in `tabpfn_token`. Keep `tabpfn_model_path="auto"` unless your account's documented model access requires another value.
3. Configure available usage controls for this account. No local foundation-model weights or GPU are required.

The predictive check is explicitly requested, not run on upload. Local reference and linear/logistic baselines work without hosted access. Hosted fitting receives training predictors and labels; prediction receives held-out predictors. Held-out labels stay local for scoring. Only use it for a question where a retrospective predictive diagnostic is useful.

### Secrets structure

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

Placeholder strings do not enable an integration. For local use copy the example to `.streamlit/secrets.toml`, which is ignored by Git. Environment variables override the corresponding provider secrets:

| Secret | Environment variable |
| --- | --- |
| `openai_api_key` | `OPENAI_API_KEY` |
| `openai_model` | `OPENAI_MODEL` |
| `openai_reasoning_effort` | `OPENAI_REASONING_EFFORT` |
| `typesafe_api_key` | `TYPESAFE_API_KEY` |
| `typesafe_model` | `TYPESAFE_MODEL` |
| `tabpfn_token` | `TABPFN_TOKEN` |
| `tabpfn_model_path` | `TABPFN_MODEL_PATH` |
| `[app].provider_mode` | `FIRSTLOOK_PROVIDER_MODE` |

`FIRSTLOOK_PROVIDER_MODE=offline` disables every provider even when credentials exist. `auto` and `live` make configured integrations available; they do not trigger automatic work. `[app].allow_external_analysis=false` is the owner-wide off switch. `terra_visual_review=false` disables analytical images while preserving text/table assistance.

## What the visitor does

In **Investigate**, the visitor enables **Allow connected assistance for this table**, reviews the sharing explanation and explicitly requests **Think this through with me**. The same permission is required before including hosted predictions in a predictive check. Uploading, navigating and ordinary reruns never trigger a paid provider request. A missing/failed service preserves local work.

Limits are four distinct assistance requests and one predictive experiment per uploaded working dataset. Changing meanings or ordinary controls does not replenish them. One assistance request can use both configured reasoning/judgment services; it is not a one-call billing promise. Hosted TabPFN adds a fit/predict protocol to the one diagnostic. These session limits limit accidental repeats; **they are not a global spending cap**. Visitors can consume the owner's quota without seeing its keys. Use dedicated provider accounts/projects, provider-enforced limits and the owner-wide off switch as appropriate.

The app sends `store=False` to OpenAI. Data retention, billing and service terms remain those of each configured provider/account. Recorded evidence can retain bounded provider inputs, responses and predictions; a source-free export can still contain sensitive values. See [analytical conventions](../docs/ANALYTICAL_CONVENTIONS.md) and [record inspection](../docs/REPLAY.md).
