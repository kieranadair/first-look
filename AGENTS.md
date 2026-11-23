# Contributor and agent guidance

First Look is a Python-only open-source Streamlit visual investigation app. Read `docs/development/CONTEXT.md` first for current status. Use `docs/development/README.md` for commands and `deployment/README.md` for deployment. The longer original specification is design history, not a requirement to repeat completed work.

- Keep the deployable application and Streamlit configuration at repository root. Deployment assets are explicitly allowlisted in `scripts/package_deployment.py`.
- Put research and bibliographic material under `docs/research/`; implementation context and historical validation under `docs/development/`. Generated reports belong in ignored `reports/`.
- Use the installed official Streamlit skill at `.agents/skills/developing-with-streamlit/SKILL.md` for Streamlit changes, discovering version-matched references in the installed package.
- Preserve Python-only application/tests, native UI and explicit analytical contracts. The user authorized screenshots for UI review on 23 November 2026, superseding the earlier screenshot prohibition. Do not add a custom JavaScript/CSS frontend or create a user-testing/approval gate. Keep captures of bundled examples in ignored reports, not committed user data.
- Owner API keys come from Cloud Secrets/environment variables. Visitors do not enter keys. Never commit real keys, `.env`, uploaded user data or live provider transcripts.
- Preserve role validation, context identity, held-out memberships and deterministic evidence. Models propose/prioritize; Python computes and validates. No generated code executes.
- No live provider or productivity claims without actual evidence. Keys and live API verification are pending owner setup. Provider budgets are bounded per investigation, not a global spend cap.
- Run appropriate tests, lint and type checks. UI interaction can be tested through AppTest, the development agent API and screenshot-free Python browser assertions. Do not enable the agent API in production.

Semantic-contract work: use `firstlook/semantic/model.py` for atomic declarations and validation. Preserve exact dataset and parsing scope, context invalidation, explicit denominator/value grain and scoped observation coverage. Models rank/propose; they do not bypass operation eligibility or confirm business meaning. Add independent numerical oracles when extending the metric algebra. The shared semantic packet and evidence format must stay aligned with execution.
