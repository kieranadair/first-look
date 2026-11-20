# Current implementation context

Updated 20 November 2026 after the initial build and repository cleanup.

## Product and architecture

First Look combines profiling, editable semantic roles, constrained native ECharts, bounded discovery, challenges, held-out model diagnostics and portable evidence. Four work areas: Understand, Discover, Challenge, Evidence. Python 3.12; Streamlit 1.67; dependencies pinned at root. No SaaS/account/database layer or local foundation-model weights.

Runtime modules are in `firstlook/`; native pages in `app_pages/`; `streamlit_app.py` is the entrypoint. Source row/field identities and context hashes join typed contracts, numerical artifacts, charts, model diagnostics and replay. A session-owned bounded job manager runs expensive work outside reruns.

## Accepted user decisions

- Host on Streamlit Community Cloud.
- Keep owner credentials in server-side Cloud Secrets/environment variables. The user considered BYO keys, then chose the existing owner-key approach with provider usage caps. No BYO implementation was made.
- User supplies and pays for Jev/TypeSafe, hosted TabPFN and OpenAI Terra credentials later. Use dedicated app keys and verify provider hard-limit semantics.
- No screenshots of the live app. Beautiful native UI, light/dark themes, local licensed fonts; no authored frontend.
- Publish as an open-source GitHub repository. Research and future-session context are separated from runtime deployment material.

## Validation and boundaries

Initial build: 88 tests passed, lint/format/type checks passed. AppTest, real agent API, actual browser chart selection/apply/reset/download and responsive light/dark UI checks passed without screenshots. Historical measurements are in `validation/`; current runs write ignored `reports/`.

A representative 50,000-row/20-field benchmark recorded about 4.5 seconds for discovery and 357 MiB peak process RSS on the declared local machine. These are not Cloud guarantees. Live API success and Terra visual uplift have not been verified; official SDKs were tested through controlled transports/boundaries. Actual Community Cloud deployment remains pending.

## Next useful work

1. Configure owner Cloud Secrets and provider usage caps; run explicit live preflight.
2. Deploy root `streamlit_app.py` on Community Cloud with Python 3.12.
3. Evaluate matched text/visual Terra conditions before claiming uplift. Keep quantities and causal assertions outside unverified generated prose.
4. Preserve the full local workflow when a provider is unavailable.

Repository cleanup retains source research and historical measurements, removes obsolete handoffs/checklists/API dumps and generated evidence bundles, and introduces a runtime-only packaging allowlist. `deployment/README.md` is the authoritative deployment guide; `docs/development/README.md` is the development guide.
