# First Look v2 contributor guide

Read `docs/v2/SPECIFICATION.md`, `PLAN.md` and `TESTS.md`. Purpose: help people investigate their own data, see consequential choices and explain what evidence supports. Three destinations: Data, Investigate, Record. No demo gallery or feature itinerary.

- Fresh Python-only Streamlit implementation. `archive/v1/` is reference only; never import it into v2. Its tests/docs are historical, not the active specification.
- Keep immutable source, stable identities, explicit grain/denominators, honest missingness, comparable views and immutable saved records. Unknown meaning is not permission. Models suggest; Python calculates; people own interpretation.
- Use the installed Streamlit skill/version-matched references for UI and `.agents/skills/typesafe-ai/SKILL.md` for Jev work. Skills do not imply product features.
- Owner Cloud Secrets/environment names remain compatible. No real keys, uploaded data or live provider transcripts in git. No automatic paid requests on upload/rerun. Offline work remains useful.
- Prediction is one explicit retrospective diagnostic, fixed memberships and train-only preparation. No held-out labels reach hosted fitting. No generated code executes.
- Test the 18 essential behaviours in TESTS.md; add only for distinct risks. Archive is excluded from active lint/types/tests/deployment.
- Native Streamlit/ECharts and licensed typography own the UI. No custom JS/CSS frontend. Screenshots are authorized locally; keep reports ignored. No user-testing gate or unmeasured productivity claims.
- V2 spec is current; earlier research mappings remain in `archive/v1/docs/research/`.
