# Third-party notices

First Look application code is Apache-2.0. Third-party code and data retain their respective licenses.

- IBM Plex Sans and IBM Plex Mono: Copyright IBM Corp. Licensed under the SIL Open Font License 1.1. Full font licenses are in `static/OFL-PlexSans.txt` and `static/OFL-PlexMono.txt`. Source: https://github.com/IBM/plex . These locally served fonts make no third-party font requests.
- Archived Palmer Penguins data: CC0. See `archive/v1/examples/README.md` and the original project attribution. V2 has no bundled example gallery.
- Archived UCI Bike Sharing daily data: CC BY 4.0. See `archive/v1/examples/README.md` for creator, DOI, source and modification notice.
- Streamlit and the Apache ECharts renderer it distributes: Apache-2.0. First Look calls Streamlit’s native `st.echarts_chart`; it bundles no separately authored frontend or JavaScript library. Sources: https://github.com/streamlit/streamlit and https://echarts.apache.org/ .
- Archived V1 used Pint (BSD-3-Clause) for quantity/offset-unit validation. Source: https://github.com/hgrecco/pint . V2 does not require Pint.
- TypeSafe AI agent skill: Copyright (c) 2026 TypeSafe AI, MIT. Installed developer guidance at `.agents/skills/typesafe-ai/`; its full license is in that directory's `LICENSE`. Source: https://github.com/typesafe-ai/skills . `skills-lock.json` records installation provenance. The skill is excluded from the runtime-only deployment artifact.
- Prior Labs relational-prediction agent skill: Copyright 2026 PriorLabs GmbH, Apache-2.0. Source: https://github.com/PriorLabs/tabpfn-rel/tree/main/.claude/skills/relational-prediction . Installed developer guidance, references and helper scripts are in `.agents/skills/relational-prediction/`, with the upstream `LICENSE`; `skills-lock.json` records provenance. These developer assets are excluded from the runtime-only deployment artifact.
- Runtime dependencies retain the licenses in their installed distributions. `requirements-lock.txt` identifies constrained runtime versions.

Jev/TypeSafe, hosted TabPFN/Prior Labs and OpenAI are external services. This repository includes Python client integrations, not provider model weights or a license to a hosted service. Account access, usage costs, data handling and service terms are controlled by each provider. The app’s explicit per-dataset external-analysis choice precedes those requests.

The public Stephen Few indexes in `archive/v1/docs/research/indexes/` are bibliographic research artifacts linking to the original public library; they do not relicense or reproduce his books or essays.
