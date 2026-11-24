# First Look v2 · product and build specification

## Purpose, distinctive contribution and user value

Help a person understand an unfamiliar table they have a reason to care about, investigate a question, and explain what the evidence supports. The primary user knows some domain context and can read ordinary charts, but benefits from an analytical partner. The distinctive contribution is the visible link between meaning, a calculated consequence, a fair visual comparison and a revisable interpretation. The first-use value is immediate useful exploration of the user's own data; continued value is better-supported judgment, reusable understanding and a readable investigation.

The product is an open-source Python/Streamlit utility, hosted on Community Cloud. Auto EDA, Jev, Terra, hosted TabPFN and native ECharts serve that purpose. Provider diversity, chart count and metadata completion are not user outcomes. No measured superiority or learning multiplier is claimed.

## Experience and scope

Three destinations: **Data**, **Investigate**, **Record**. No public example gallery, showcase datasets, preparation workspace, ontology-completion queue, model laboratory or provider inspection destination. Synthetic data exists only in tests/developer checks.

The opening says **“Hi, I’m First Look.”** It invites a table the person knows a little about, explains the benefits and philosophy, and makes upload the dominant action. Suggested copy: “Bring a table you know a little about. We’ll explore what’s in it, follow what catches your eye, and check the choices that could change its meaning. You bring the context. I’ll help with the calculations and comparisons.” A brief explanation of session storage and integrated model-assisted analysis sits beside upload. No account, keys or questionnaire is required to start.

After upload, show a useful recorded-data view immediately, a short plain-language orientation and a few purposeful starting directions. A question and domain notes are optional. Continuing copy is short, warm, specific and dismissible where appropriate. It does not pretend the app is human or that model guesses are established facts.

The rhythm is **define → plan → execute → reflect**: name what matters, choose a useful next view, inspect the calculated evidence, then revise an interpretation or question. SolveIt/REPL's inspectable iterations and Polya's problem-solving approach inform that rhythm. It is iterative, not a mandatory wizard or four compulsory pages. The fastai principle is a useful whole task before taxonomic foundations. Few's principles guide task-appropriate representations, comparable scales, distributions behind averages and relevant related evidence visible together.

## Data

One CSV/Parquet table; 25 MiB source, 50,000 rows, 80 fields, 80 MiB decoded memory. Immutable source data and stable internal column/record identities. Preserve leading-zero identifiers, large integer strings, duplicate labels and literal missing markers. Empty cells are missing by default; explicit missing tokens/parser options are available in a secondary control. Parsing problems are disclosed, not silently converted to zero. Profiles calculate full-source support, missingness, distinctness, numeric quartiles/domain and observed time span. Free-text values do not enter default connected packets.

The user can inspect representative records and correct a field's analytical role in one place. Domain notes are retained. Per-field business meaning is deliberately small: unknown/additive/nonadditive, supplied unit and optional value entity. The entity distinguishes a value on every row from a repeated value counted once per identifier. Equality suggests a question; it never confirms the answer. Meanings remain human declarations. There is one authority, not competing legacy flags or bulk approval queues.

## Investigate

One explicit request yields an inspectable result. The seven perspectives in Few's *Vistas of Understanding* inspire questions rather than a chart checklist. Current technology can choose eligible perspectives, supply full-source calculations, preserve definitions and connect related evidence without asking a user to construct a dashboard first. Representation remains subordinate to question and meaning:

| Question family | Useful representation and boundary |
| --- | --- |
| Variation across categories | Ranked bars for counts/contributions. Treemap only for a valid nonnegative partition when an overview of many parts helps; no universal count threshold substitutes for the task. |
| Variation within measures | Histograms for counts by interval, common-bin frequency polygons for distribution comparison, horizontal-value quantile curves and clearly defined box summaries. Exact source quantiles stay available behind a display. |
| Variation in space | A conditional location view only after the user identifies latitude/longitude degrees and the spatial pattern is relevant. No automatic geocoding or inference that a map is required. |
| Variation over time | Recorded lines/bars, explicit nonnegative series-total normalization, full-window trailing averages, deviations from those averages and weekday/hour heatmaps. Smoothing reveals a trend; deviations examine what remains relative to it. No time transformation is silently applied. |
| Quantitative relationships | Square scatter regions, complete-pair statistics, within-group contrasts and ranked multi-measure profiles. Association and shape suggest questions, not causes. |
| Categorical relationships | Small multiples with common axes and explicit within-group denominators. Overlapping entity membership is distinguished from mutually exclusive row categories. |
| Many variables/perspectives | Bounded parallel coordinates or aligned ranked profiles, plus related comparison views visible together. Separate units/ranges remain explicit; no automatic claim of clusters. |

Missingness remains a useful cross-cutting perspective. Routine statistics are computed deterministically. Initial suggestions use field roles/support and diversity, not p-value shopping or a universal significance/interestingness score. These options appear as ways to investigate the current data, not a public feature gallery.

Supported summaries: recorded rows, distinct recorded identifiers, recorded/entity mean or median, additive sum, and weighted mean with explicit weights. Proportions declare their denominator; overlapping distinct-entity incidence is not a 100% partition. Repeated entity amounts must be constant at the chosen entity; overlapping grouped totals require an explicit attribution choice or are blocked. Quantities marked nonadditive cannot be summed. Counts/distributions/recorded means remain available while business meaning is unresolved. Coordinate/circular names should be flagged rather than advertised as generic scalar prediction candidates.

Unknown consequential meaning opens a small decision beside the source evidence and numerical alternatives. A user can declare an additive row amount, a once-per-entity amount, a nonadditive quantity, or retain uncertainty. Only the declared implications propagate. No generic approval checklist. “I don’t know” leaves useful recorded-data exploration available.

Time views preserve unobserved periods as unknown. Explicit all-missing observations remain unknown. Zero filling is offered only for count/additive event quantities after the user declares complete event recording, a calendar period and complete-through boundary. Calendar heatmaps disclose that observed weekday/hour combinations can have unequal exposure across the included weeks. No carry/interpolation, counters, forecasting or implicit coverage inference in v2.

Comparisons live beside the active investigation. A categorical cohort is compared with the remainder/reference under identical definitions, common histogram bins and compatible numeric scales. Grouped relationship views show pooled and within-group evidence without causal claims. A selected comparison can be retained; changing filters is an explicit change in analytical population. Statistics use all eligible rows; scatter display reduction is deterministic and clearly distinguished from statistical support. Scatter inner plot regions are square without forcing equal units on unrelated axes.

Each result visibly states what was calculated, population/support, omitted records, estimator/grain/denominator and important limitations. Detailed tables and source inspection are optional, not a replacement for readable views. Related evidence stays together rather than hiding essential context in expanders.

## Integrated analytical instruments

Jev, Terra and TabPFN are always part of the app. Existing owner Cloud Secrets/environment names remain compatible; visitors enter no keys and encounter no enable/consent/provider-mode controls. The upload screen explains bounded sharing before data is opened. Development assumes configured services and uses controlled clients in tests; there is no offline or local-only product mode. Supplied legacy off flags have no effect.

Jev and Terra review the first uploaded view automatically, then review new executed views, changed question/context, meaningful declarations, comparisons and completed predictive evidence. Work is asynchronous, scoped, deduplicated and cached per analytical context. Ordinary reruns and returning to reviewed evidence do not repeat paid work. There is no four-review cutoff. Explicit retry is available after a failed review; failures remain honest service errors. The evidence bundle retains the most recent twenty-four review records. Stale results cannot replace a changed investigation.

Terra receives bounded metadata, supplied notes, the current verified result and up to three allowed next-view candidates; one matched analytical image/table pair where supported supports visual reasoning. It returns structured, unconfirmed hypotheses, cited interpretation and candidate IDs. It cannot generate executable code, alter meanings, invent measurements or declare completed checks. Suggestions refer to actual supplied fields/results. User interpretations and model interpretations remain distinguishable.

Jev answers narrow source-support/applicability or candidate-relevance questions. Python owns arithmetic and execution. Uncertain answers remain unresolved; an API failure is not a negative judgment. Literal source citations are validated, and judgments never confer analytical permission. Both adapters record model identity, usage and bounded inputs/results for inspection/export with appropriate privacy disclosure.

TabPFN is a conditional, explicitly requested **retrospective predictive-structure check**, not a stage of generic enrichment. One fixed experiment per uploaded investigation always includes hosted TabPFN predictions and actual local baseline/reference. No model-enable or hosted/local switch exists. The human still chooses a meaningful prediction target, permissible predictors and evaluation question; always-on access is not permission to fit an arbitrary target on upload. The user chooses target, permitted predictors and row/group/time holdout. Repeated-entity evaluation preserves group boundaries; chronological splits preserve order. Preparation and target-copy screening use training rows only. Hosted fit sees training predictors/labels and held-out predictors, never held-out labels. Exact memberships and all results, including inferior predictions, are retained. No prospective availability guarantees, text-feature coding, event-label construction, causal inference, automatic model selection or holdout-driven iterative search.

## Record and reproducibility

The record is a readable collection of chosen views, their definitions, important decisions and optional human interpretations/next questions. Pinning is deliberate; writing a note is optional. A saved view is immutable even when later meanings change. A small portable evidence format includes source fingerprint/parser, relevant meanings, exact memberships, requests, verified results and recent model-review records and the predictive record when a check has been run. Original bytes are optional. Checksums detect modification, not authorship. Import is inspection only; recomputation requires matching source bytes and never calls providers. V1 artifacts remain readable by archived v1, not silently migrated through a new parser.

## Architecture

Fresh `firstlook/` modules: `types.py` (small contracts), `data.py` (ingestion/profile), `analysis.py` (calculation/permissions/comparison), `perspectives.py` (conditional categorical, spatial and multivariate calculations), `charts.py` (native ECharts), `session.py` (working state/budgets), `evidence.py` (record/replay), `providers.py` (owner settings/assistance), `prediction.py` (one diagnostic protocol), `ui.py` (shared native UI). Root `streamlit_app.py` owns three-page navigation; `app_pages/data.py`, `investigate.py`, `record.py` remain direct scripts. No v2 imports from archived v1. No custom JS/CSS frontend, agent loop, general SQL interpreter, database, lineage system or provider-specific top-level page.

V1 source, tests, documentation and runtime configuration are preserved under `archive/v1/` with their original commit identity. Active lint/types/tests/deployment exclude that reference tree. Research remains preserved and referenced; current documentation consists of this specification, build/test plans and one short contributor guide. Licensed static typography can be retained as an asset, not copied application logic.

## Research translated into design

- **Human-centred problem solving:** define/plan/execute/reflect, useful whole tasks first, visible intermediate evidence and revisable human interpretation. Automation removes repetitive setup; it does not hide the decisions needed to understand a result.
- **Few and visual perception:** choose views for analytical questions; preserve honest scales, relevant adjacent comparisons and distributions behind averages. His work is inspiration, not a requirement to reproduce book layouts or enumerate every chart.
- **Semantic typing and constrained visualization:** measured structure and human-declared meaning have different authority. Finite request contracts, deterministic eligibility and immutable result definitions make an AI suggestion executable only when it is valid.
- **Language/decision models:** Terra bridges context, question formation and visual hypotheses; Jev evaluates narrow supplied propositions. Neither substitutes for arithmetic, source verification or domain attestation.
- **Tabular foundation models and evaluation:** predictive structure is useful only against a real reference, a fixed partition and training-only preparation. It stays a conditional diagnostic, not an automatic verdict about a dataset.

The source research and bibliographic indexes remain in [the preserved research archive](../../archive/v1/docs/research/), especially [Few's exploration synthesis](../../archive/v1/docs/research/few-part-ii-review.md), [chart rules](../../archive/v1/docs/research/chart-design-audit.md), [semantic contracts](../../archive/v1/docs/research/semantic-contract.md), [Terra integration](../../archive/v1/docs/research/terra-integration.md) and [the evidence review](../../archive/v1/docs/research/evidence.md). Historical implementations and limits described there do not supersede this specification. No user-learning or productivity multiplier is claimed without an evaluation.

## Acceptance

Upload-first welcome; immediate useful local view; one meaning authority; visible consequence before important confirmation; reversible working choices and immutable saved records; adjacent comparable views; integrated contextual AI and purposeful TabPFN prediction; bounded source-safe execution; readable reproducible record; local and Community Cloud compatibility; a small explicitly justified test suite. No new user-testing gate or live-provider performance claims.
