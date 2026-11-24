# First Look v2 contributor guide

Read `docs/v2/SPECIFICATION.md`, `PLAN.md` and `TESTS.md`. Purpose: help people investigate their own data, see consequential choices and explain what evidence supports. Three destinations: Data, Investigate, Record. No demo gallery or feature itinerary.

- Desktop-only product for data professionals using large monitors. Review at 1920 × 1080 and 2560 × 1440; 1600 × 900 is the comfortable minimum browser viewport. Keep related charts, definitions, model perspectives and reflection adjacent. No mobile/small-laptop layout work or device-detection gates. Narrow chart panels can still occur within a desktop composition.

- Fresh Python-only Streamlit implementation. `archive/v1/` is reference only; never import it into v2. Its tests/docs are historical, not the active specification.
- Keep immutable source, stable identities, explicit grain/denominators, honest missingness, comparable views and immutable saved records. Unknown meaning is not permission. Models suggest; Python calculates; people own interpretation.
- Use the installed Streamlit skill/version-matched references for UI and `.agents/skills/typesafe-ai/SKILL.md` for Jev work. Skills do not imply product features.
- Owner Cloud Secrets/environment names remain compatible. No real keys, uploaded data or live provider transcripts in git. Jev, Terra and TabPFN are integral, always-on services; no visitor enable/configuration step or provider-off mode. Review new analytical context automatically and deduplicate ordinary reruns. Development uses injected controlled clients, not an alternate product mode.
- Prediction always includes TabPFN in one explicit retrospective diagnostic, fixed memberships and train-only preparation. No held-out labels reach hosted fitting. No generated code executes.
- Test the 19 focused behaviours in TESTS.md; add only for distinct risks. Archive is excluded from active lint/types/tests/deployment.
- Native Streamlit/ECharts and licensed typography own the UI. No custom JS/CSS frontend. Screenshots are authorized locally; keep reports ignored. No user-testing gate or unmeasured productivity claims.
- V2 spec is current; earlier research mappings remain in `archive/v1/docs/research/`.
