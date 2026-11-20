# Third-party notices

First Look application code is Apache-2.0. Third-party code and data retain their respective licenses.

- IBM Plex Sans and IBM Plex Mono: Copyright IBM Corp. Licensed under the SIL Open Font License 1.1. Full font licenses are in `static/OFL-PlexSans.txt` and `static/OFL-PlexMono.txt`. Source: https://github.com/IBM/plex . These locally served fonts make no third-party font requests.
- Palmer Penguins: CC0. See `examples/README.md` and the original project attribution.
- UCI Bike Sharing daily: CC BY 4.0. See `examples/README.md` for creator, DOI, source and modification notice.
- Streamlit and the Apache ECharts renderer it distributes: Apache-2.0. First Look calls Streamlit’s native `st.echarts_chart`; it bundles no separately authored frontend or JavaScript library. Sources: https://github.com/streamlit/streamlit and https://echarts.apache.org/ .
- Runtime dependencies retain the licenses in their installed distributions. `requirements-lock.txt` identifies the resolved versions, and evidence bundles include relevant package versions.

Jev/TypeSafe, hosted TabPFN/Prior Labs and OpenAI are external services. This repository includes Python client integrations, not provider model weights or a license to a hosted service. Account access, usage costs, data handling and service terms are controlled by each provider. The app’s explicit per-dataset external-analysis choice precedes those requests.

The public Stephen Few indexes in `docs/research/indexes/` are bibliographic research artifacts linking to the original public library; they do not relicense or reproduce his books or essays.
