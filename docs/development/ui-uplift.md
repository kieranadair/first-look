# First Look interface refinement

Implemented 23 November 2026. This round changes presentation and navigation, preserving the analytical engine, semantic permissions, model protocols and evidence format.

## Design rationale

The review uses the uploaded Stephen Few, *Now You See It* (2020), Section I, especially Chapter 3, “Thinking with Our Eyes,” pp. 51–55, and Chapter 4, “Visual Data Sensemaking Interaction and Navigation,” pp. 59–90. Two independent chapter/code reviews were combined with direct screenshot-based inspection of bundled examples in the running local app. Screenshots were explicitly authorized for this round, superseding the earlier restriction. This is an expert design review, not a user study.

| Principle and source | Application in First Look |
| --- | --- |
| Keep related evidence available to visual memory: Few Ch. 3, pp. 52–55; comparison and small multiples, Ch. 4, pp. 60–64 and 73–77 | Field roles sit beside field evidence; inspection pairs the chart with its definition, support and limits; comparison and challenge boards retain adjacent views. Responsive layouts reflow when width is insufficient rather than shrinking text to fit. |
| Keep reference context while examining a subset: Few Ch. 4, pp. 69–71 | Preview/compare and explicitly apply/filter remain different actions. Active population and reset/return remain visible near the page heading. |
| Details on demand: Few Ch. 4, p. 85; [Nielsen, Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/) | Parser options, raw execution contracts and bibliographies remain secondary. Once a view exists, its construction controls move to a named popover. Definitions needed to read the chart remain visible. |
| Fluid navigation and bookmarks: Few Ch. 4, pp. 86–90; [Budiu, Recognition and Recall](https://www.nngroup.com/articles/recognition-and-recall/) | Stable page names, native navigation tooltips, direct prerequisite links and a navigable saved-evidence count reduce the need to remember routes. A hidden native inspection page opens at the top instead of preserving a gallery's previous scroll position. |
| Readable, restrained chrome: [WCAG 2.2 contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and version-matched Streamlit 1.67 theme/design/layout references | Neutral surfaces, 16px body text, compact heading scale, quieter borders, explicit table-header text contrast, one action accent and dual light/dark variants. Status retains a text label alongside colour. |

These sources motivate the design choices. They do not measure this app's productivity or establish a universally optimal layout.

## Delivered layout

- **Application shell:** a native logo wordmark replaces repeated sidebar branding. Sidebar width initially uses 240px with normal responsive behaviour and user resizing. Current population, saved-evidence link and provider state remain visible. Eight visible work areas retain their existing URLs; `inspect.py` is a linked detail route, hidden from the primary navigation.
- **Understand:** upload and a guided example share the landing row. After loading, the primary local-investigation action appears near the top. Change dataset, investigation settings and context editing are secondary controls. Existing row context remains visible. Field-role editing and recorded field evidence share a row; the inspector initially chooses a measure when one exists.
- **Meaning:** compact counts replace four large summary metrics. One selected open decision and its reason sit beside the quantity editor. Existing Metrics, Structure & time and Contract tabs retain their responsibilities.
- **Explore:** finite coverage and a starting view remain adjacent. Existing results appear before recipe configuration; Change perspective opens setup only on demand. Companion charts and source support remain visible.
- **Findings and inspection:** a compact browsing toolbar and inline question form lead into the gallery. Rerun/provider options and detailed planner logs are secondary. Inspect opens one chart beside its support, analytical definition and limitations, with Back, Challenge and Pin at the top. Exact values and raw execution details remain accessible without duplicating the gallery.
- **Compare and Challenge:** readable cohort/reference labels, conditional status and supporting rows accompany aligned charts. Explicit filtering remains distinct from previewing. Secondary provider actions follow the board.
- **Models:** target and holdout settings share a compact setup row. Recorded diagnostics keep their existing paired arrangement; hosted-data permission is explained where it matters.
- **Evidence:** preparation/download controls appear before long saved content. Observations and comparison boards have separate reading modes. One pinned observation and note editor is visible at a time; every pin remains in the exported brief, in its recorded order. Notes are captured before switching items.

No custom CSS, JavaScript frontend or new dependency was added. ECharts receives the app font and confined tooltips; numerical values, scales, category identities and source memberships are unchanged.

## Verification

The full suite passes: 175 tests. Ruff lint/format and type checks pass. Existing controlled-provider tests make no live API calls. Existing runtime smoke checks exercise local investigation, challenge navigation and export. Targeted AppTest checks cover the focused inspection route, lazy perspective controls and note switching/reordering/export. Smoke scripts were updated for new labels and secondary controls.

Configured foreground/background contrast ratios are 15.91:1 and 15.66:1 for light/dark body text, 8.71:1 and 10.55:1 for table headers, and 6.20:1 and 5.35:1 for white text on primary buttons. These token checks are not a full accessibility conformance audit; native captions, states and chart interactions need their own evaluation.

The local browser review uses bundled examples. Community Cloud deployment and live provider access remain separate owner setup. Two existing upstream pandas/NumPy resampling deprecation warnings remain in the replay fixture.
