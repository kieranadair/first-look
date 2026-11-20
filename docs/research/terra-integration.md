Research and integration specification dated 20 November 2026.

Use GPT-6.1 Terra as First Look’s multimodal investigation and synthesis layer. It should propose questions that the existing catalog did not prioritize, compare evidence across views, suggest concrete challenges, and explain what changed after those challenges. Profilers remain the source of measured facts, Jev remains a bounded decision component, tabular foundation models remain the predictive lens, and Python enforces analytical validity.

The relevant API model is gpt-6.1-terra, accessed through the OpenAI Responses API using an OpenAI API key. This replaces the earlier gpt-5.4 default for the language adapter. The owner supplies the key after implementation; the app ships with placeholders and controlled-transport tests. [Official model reference](https://developers.openai.com/api/docs/models/gpt-6.1-terra)

Terra is a plausible integration candidate, not a demonstrated improvement to First Look before evaluation. Vendor capability evidence, a direct third-party analytics benchmark, academic findings about related systems, and the proposed app design are distinguished below.

# 1 The gap Terra should bridge

A profiler can tell us that fields are missing, two measures correlate, and a distribution is skewed. It does not, by itself, formulate a coherent investigation across several such observations.

Jev can judge a supplied hypothesis, choose among eligible plans and assess relevance under a rubric. Its interface does not generate the open-ended explanation, new question or connected written account. Jev can also accept images; the useful distinction is generative reasoning and synthesis, not “Terra can see and Jev cannot.” TypeSafe currently describes its image/Box features as experimental. [TypeSafe image interface](https://docs.typesafe.ai/images)

A tabular foundation model can reveal predictive structure and held-out error patterns. Its score does not explain which visual relationship to inspect next, why two views appear inconsistent, or which missing assumption prevents an interpretation.

Terra can bridge these outputs by forming a hypothesis, identifying the evidence needed to challenge it, and revising the explanation after code computes the check.

| Component | Primary responsibility | What it should hand to the next component |
| --- | --- | --- |
| Automatic profiler | Measured summaries and quality evidence | DatasetProfile and typed result tables |
| Jev | Bounded role, relevance and next-check judgments | Valid option IDs, probabilities and abstention |
| Tabular foundation model | Predictive structure under a recorded protocol | Held-out predictions, errors and baseline comparisons |
| Terra | Question generation, cross-view reasoning and explanatory synthesis | Proposed plans, evidence relations and labeled interpretation |
| Python analytical core | Computation, validity, provenance and rendering | Verified artifacts and accepted or rejected actions |

The highest-value role is a bounded investigation loop, not a chat panel that restates the dashboard.

# 2 Findings from the research

## Direct evidence about Terra

OpenAI documents image input, text output, reasoning effort, structured outputs and function calling for GPT-6.1 Terra. Its launch evaluations concern visual reasoning, professional tasks and computer use. Those capabilities establish a suitable interface and candidate model; they do not validate statistical investigation in this app. [Model reference](https://developers.openai.com/api/docs/models/gpt-6.1-terra), [Launch evaluation](https://openai.com/index/introducing-gpt-6-1-terra/)

Plotly reports that Terra passed 40 of 43 questions in its private synthetic data-analytics exam. It passed the straightforward analytics, ambiguous-request, impossible-request and data-quality groups, but found only three of five planted hidden patterns and passed four of five statistical traps. The evaluation used an agentic querying harness, not First Look or an isolated visual-reasoning task. It supports trying Terra alongside independent analytical engines rather than assigning it sole responsibility for discovery. [Plotly’s evaluation](https://plotly.com/blog/gpt-6-1-terra-plotly-data-analytics-bench/)

## Academic findings and their product consequences

| Research | Finding within the study’s scope | Pattern to implement | Limit |
| --- | --- | --- | --- |
| Same Stats Different Graphs, CHI 2017 | Datasets can share selected summary statistics while having very different visible structure | Let a visual reviewer suggest shape-sensitive follow-ups | This does not establish that Terra detects those structures correctly |
| ChartQA, Findings ACL 2022 | Chart questions combine visual references with logical and arithmetic reasoning | Supply the image, underlying values and analytical question together | Exact arithmetic remains code’s job |
| DePlot, Findings ACL 2023 | Separating plot-to-table conversion from language reasoning improves its evaluated reasoning pipeline | Reuse known result tables instead of reconstructing values from pixels | First Look already has the table; it does not need DePlot as another model |
| LIDA, ACL 2023 Demonstrations | A staged system separates data summarization, goal exploration and visualization generation | Use generative goal exploration before constrained execution | A systems demonstration does not validate unrestricted generated code |
| Data Formulator 2, CHI 2025 | Eight study participants used different iterative strategies with blended graphical and natural-language interaction | Allow revision and continuation of an investigation, preserving prior context | A small interface study does not prove First Look’s productivity |
| InsightBench, ICLR 2025 | Its multi-step baseline outperformed approaches focused on individual queries in the reported benchmark | Evaluate question formulation, follow-up discovery and synthesis together | Planted datasets and model-based evaluation do not establish universal usefulness |
| Chart-to-Text, ACL 2022 | Fluent summaries still contained factual errors and hallucinations | Separate measured statements from generated interpretation and verify references | Fluency and text-similarity scores cannot establish correctness |
| ChartQAPro, Findings ACL 2025 | Performance fell sharply on harder chart questions; one reported model fell from 90.5% to 55.81% | Include difficult, unanswerable and representation-sensitive cases | These are earlier-model results, not measured Terra performance |
| ChartCheck, Findings ACL 2024 | Chart-claim verification requires evidence and remains challenging across reasoning types | Evaluate individual claims and explanations against artifacts | A second model agreeing is not proof |

Sources: [Same Stats Different Graphs](https://www.research.autodesk.com/publications/same-stats-different-graphs/), [ChartQA](https://aclanthology.org/2022.findings-acl.177/), [DePlot](https://aclanthology.org/2023.findings-acl.660/), [LIDA](https://aclanthology.org/2023.acl-demo.11/), [Data Formulator 2](https://www.microsoft.com/en-us/research/publication/data-formulator-2-iteratively-creating-rich-visualizations-with-ai/), [InsightBench](https://proceedings.iclr.cc/paper_files/paper/2025/hash/0dfe31d6e703e138d46a7d2fced38b7c-Abstract-Conference.html), [Chart-to-Text](https://aclanthology.org/2022.acl-long.277/), [ChartQAPro](https://aclanthology.org/2025.findings-acl.978/), [ChartCheck](https://aclanthology.org/2024.findings-acl.828/).

The synthesis is to combine visual hypotheses, exact tabular evidence and executable checks. These papers do not justify treating a vision-language model as a statistical oracle.

# 3 Required behaviors

## Generate a worthwhile question

Given an evidence packet, Terra can suggest that a pooled association may differ by group, a weak linear summary may hide a curve, or a good global model score may conceal concentrated errors.

The output is a proposed investigation with known field IDs, a reason to investigate, required evidence, and one or more catalog operation IDs. A fluent hypothesis without an executable check remains a labeled question.

## Reconcile several views

Terra compares an original finding, its challenge, and relevant model diagnostics. It can explain why they qualify one another: a pooled relationship need not hold within groups; predictive accuracy need not imply a large marginal correlation; a mean comparison may hide different distributions.

It must preserve context differences rather than manufacture a contradiction. Different row subsets, units, conditioning variables or model splits are surfaced explicitly.

## Improve the next action

A proposal says what to compute next and what result would change the interpretation. Jev can rank validated proposals for relevance and cost. Code executes the selected plan.

An unsupported request such as “prove why this caused the outcome” becomes an explanation of what the data cannot establish and a supported descriptive alternative.

## Write an evidence-linked explanation

Produce four short parts: what was observed, what was checked, what remains a hypothesis, and what to investigate next. Numerical facts use artifact bindings; natural-language interpretation remains clearly identified.

This expands the earlier language adapter beyond semantic parsing and canned brief selection while preserving the same contract boundaries.

# 4 Bounded investigation loop

1. Profiling, semantics and existing discovery compute the initial evidence.
2. Jev selects a diverse shortlist from valid candidates.
3. Python builds a small EvidencePacket from related findings, tables, context and independently rendered chart assets.
4. Terra returns up to three HypothesisProposals, including an explicit no-useful-next-step outcome.
5. Code checks roles, fields, prerequisites, support, novelty, context and budget.
6. Jev may prioritize the eligible proposals. It cannot make an ineligible proposal valid.
7. Execute at most two additional cheap checks, or use the already budgeted model experiment when appropriate.
8. Terra receives the new artifacts and produces an updated synthesis, recording which hypotheses were supported, weakened or left unresolved.
9. Stop. Additional user-directed rounds are explicit and consume the existing bounded follow-up allowance.

Use at most two Terra requests for the automatic investigation loop, plus one optional metadata/semantic request. Replace the earlier two-language-call initial budget with this maximum of three. Refusal repair consumes the same cap. If the optional semantics call is omitted, its slot can support one bounded repair.

No repeated model self-critique loop, arbitrary Python generation, unrestricted SQL, provider browsing, remote shell, computer-use automation or hidden agent framework is needed. The app orchestrates structured requests and existing Python operations.

A proposal that duplicates an existing plan is linked to that result instead of rerun. When no eligible proposal remains, the correct result is to stop.

# 5 Evidence packets and contracts

## EvidencePacket

Include packet ID and hash; dataset/context/semantic revisions; user focus and declared assumptions; known field roles; selected findings; exact metric references; bounded plotting data; image-asset IDs; chart specifications; support and sampling; completed challenges; model split and baseline summaries; eligible next operations; and remaining budget.

The 48,000-character cap applies to textual metadata and plotting values, excluding image base64. If a packet exceeds it, reduce views or sampled points and regenerate their images and tables together. Never truncate JSON, drop a caveat, or leave an image showing records absent from its supplied table.

Every chart asset links to the exact result, filters, displayed rows, encodings and domain. Omit raw records and sensitive field exemplars unless the disclosure policy permits them. Plotted points and categories themselves are data and must be disclosed as such.

## HypothesisProposal

Fields: hypothesis ID; question; hypothesis type; referenced evidence IDs; involved field IDs; proposed operation and typed arguments; missing assumptions; expected informative result; stop or abstain status; and explanatory text.

Supported types initially include subgroup dependence, nonlinear-looking shape, changing residual spread, extreme-value dependence, summary sensitivity, missingness composition and interpretation ambiguity.

The model does not supply its own effect size, probability of truth or executable code. “Expected informative result” describes what would matter, not a fabricated result.

## EvidenceRelation

Represent relations such as qualifies, differs-under-context, supported-by-check, weakened-by-check and unresolved. Code validates their prerequisites when a registered quantitative predicate exists.

For example, a subgroup-direction statement must refer to the exact supported group summaries. “All groups” cannot include unobserved, omitted or unsupported groups.

A citation or valid reference ID alone does not prove a free-form sentence follows from the evidence.

## NarrativeSynthesis

Separate verified observation blocks, completed-check blocks, model-generated interpretations and next questions. Bind numeric values and registered directional claims to artifacts. Render verified values in Python.

Free explanatory prose can connect ideas and describe plausible interpretations. It must not be promoted to a verified statistical claim because it passed JSON validation or received agreement from Jev.

When generated prose adds unsupported quantities, causal assertions or invented units, reject the affected block and use the deterministic evidence summary. Preserve a useful question where possible.

## Reproducibility

Record exact packets, prompts, requested/resolved model identity, responses, accepted/rejected proposals, selected checks, token usage and asset hashes. Replaying the saved investigation uses saved outputs and does not call Terra.

# 6 Visual reasoning without live app screenshots

Preserve the existing ban on screenshots of the live application. Do not add Playwright screenshot calls, desktop captures, browser-image traces, or computer-use monitoring.

Instead, generate bounded chart images directly from validated result artifacts in Python. Use an offscreen Matplotlib Agg renderer with explicit Figure objects. The images are analytical assets, not captures of the Streamlit UI.

The native ECharts view and review asset share result identity, field encodings, units, domain policy, category order, bins and missingness policy. Record any rendering difference. Do not call this a pixel-equivalent audit of the actual ECharts widget.

The initial review renderer only needs scatterplots, grouped comparisons, distributions and residual diagnostics. Reuse chart-contract data; do not create a second statistical implementation.

Limit a packet to three PNG assets, each no more than 1.5 MiB with a long edge at most 1,200 pixels. Use readable axis labels and at most 600 plotted observations per review view, sampled reproducibly and labeled. These are proposed engineering budgets.

Store the exact plotting data supplied with each image. The text-only and image-plus-table evaluation conditions receive the same underlying plotting data; images must not secretly reveal more records.

Use a single rendering lock, close figures and buffers, and avoid global pyplot state. Re-measure Cloud memory after adding Matplotlib. Cache only within the session’s bounded artifact store.

A visual impression of curvature, separation or changing variance starts a hypothesis. It cannot become a measured result until a supported Python check executes. Terra’s view of a static analytical asset cannot establish that the live UI has no clipped labels, accessibility problems or selection bugs.

# 7 Small analytical extensions

Keep the existing challenge catalog and add only two operations to make visual hypotheses actionable:

| Operation | Definition | Interpretation boundary |
| --- | --- | --- |
| quantile_bin_summary | For a supported numeric pair, compute 3–6 recorded quantile bins with paired support, x medians and y median/quartiles; resolve tied boundaries explicitly | Reports conditional summaries, not proof of a functional or causal relationship |
| residual_spread_by_bin | For an existing held-out ModelRun, learn predictor-bin boundaries on training rows and compare held-out error/spread and counts within those bins | Reports observed error variation under the recorded split, not a calibrated uncertainty guarantee |

Minimum support, units, missingness and row memberships remain visible. Do not silently pool under-supported bins.

A nonlinear-looking proposal can use the bin summary and the existing linear, gradient-boosting and foundation-model comparisons. Do not add a separate unrestricted modeling framework.

Do not label visual clusters as verified population subgroups. A future cluster detector needs its own contract, stability procedure and tests.

An apparent outlier uses the existing sensitivity check. A suspected pooled/group discrepancy uses the existing subgroup challenge. A request for another chart uses a valid alternative encoding of the same result.

These extensions are engineering designs motivated by the research; the papers do not validate their default bin counts or support thresholds.

# 8 Product integration and example

In Discover, place a compact “Read the evidence” section below the lead finding. It contains a short synthesis, up to three proposed questions, and links to the supporting views. Keep verified observations and possible explanations visually distinct.

In Challenge, show how the interpretation changed after a check. Preserve the original and the new explanation. An evidence relation links them.

In Model lens, Terra can suggest which supported error group or residual view deserves attention. It cannot rewrite metrics, choose a favorable split after seeing outcomes, or invent an explanation of feature importance.

In Evidence, add the synthesis, outstanding questions and proposal history to the existing brief. Model-authored interpretation remains labeled after export and import.

## Flagship example

A dataset shows a pooled relationship. The model lens also finds useful predictive structure, but errors vary across recorded groups.

Terra sees the pooled chart, a group view and a held-out residual view with their exact tables. It proposes checking whether the pooled result describes the supported groups and whether prediction errors grow across a permitted predictor’s range.

Code validates those checks; Jev prioritizes; Python computes them. The revised synthesis describes the observed group differences and error concentration, identifies what remains unexplained, and proposes a next question.

The value is the connected investigation that a person can inspect and continue. An impressive-sounding paragraph without those computations is not the feature.

# 9 Configuration and implementation

Use the existing OpenAI provider slot. There is no fourth service account.

```toml
[providers]
openai_api_key = "REPLACE_WITH_OPENAI_API_KEY"
openai_model = "gpt-6.1-terra"
openai_reasoning_effort = "medium"

[app]
terra_visual_review = true
max_terra_loop_requests = 2
max_terra_initial_requests = 3
max_terra_images = 3
max_terra_plot_points = 600
max_terra_packet_chars = 48000
```

These entries extend the existing template; retain the Jev, TabPFN and app-resource fields. Extend the dataset disclosure to include Terra’s chart images and bounded plotting values. Metadata-only permission does not authorize that payload. Redaction must change the image and its matching table together, or disable the visual request. The initial request cap includes the optional metadata request. Typed user follow-ups use the existing separate session allowance.

Use Responses API text and image inputs with structured outputs, recording the actual response model and usage. PNG data URLs avoid making private chart assets publicly accessible. Handle refusal, incomplete responses, unsupported configuration and invalid output. [Vision inputs](https://developers.openai.com/api/docs/guides/images-vision), [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

The model ID and reasoning effort are owner configuration. A missing or placeholder key disables live Terra requests and leaves all deterministic work available. Do not silently substitute a different model.

Required implementation files extend the current plan: firstlook/providers/language.py for the Terra adapter; firstlook/investigation.py for the bounded loop; firstlook/visualization/review_assets.py for offscreen rendering; contracts for packets/proposals/relations/synthesis; and scripts/evaluate_terra.py for the incremental-value benchmark.

Add Matplotlib to the locked dependency set. Test all behavior with controlled transports during implementation. Add a small optional real API smoke for after key setup. Do not claim live Terra output or measured gains before that smoke and benchmark run.

# 10 Evaluation of the proposed uplift

The key question is whether Terra finds a useful next check or explains an evidence relationship that the existing pipeline misses, while preserving factual integrity and a practical budget.

## Matched ablations

A. Existing profilers, deterministic discovery, Jev and tabular-model diagnostics without Terra.

B. The same system plus Terra using tables, metadata and chart contracts only.

C. The same system plus Terra using those identical tables and chart assets.

D. Image-only review as an evaluation condition to measure failure modes, never the production design.

Keep candidates, plotting rows, assumptions, model outputs and permitted operations matched. Record actual token, image and execution costs. Separate gains from general language reasoning from gains that require image input.

## Cases and metrics

Use independent seeded cases with subgroup reversal, curved relationships, changing residual spread, outlier dependence, near-identical summary statistics, ambiguous semantics, no structure, unsupported questions and low-support groups. Prefer new generated instances to memorized public chart examples.

Measure executable-proposal rate, useful nonduplicate checks, known-signal coverage, false promotion on null data, supported-claim accuracy, preservation of caveats, appropriate abstention, replay completeness, latency and cost.

Score known facts and proposed operations with programmatic oracles where possible. Keep benchmark ground truth out of model packets. A model judge can supplement review but cannot be the sole correctness oracle or grade its own claimed discoveries.

Repeat live evaluations across seeds and equivalent label/color/axis presentations. Report uncertainty and failures; a single favorable response is not a validated pattern.

## Added acceptance scenarios

| ID | Assertion |
| --- | --- |
| TER-01 | Missing or placeholder keys launch no request |
| TER-02 | Every image has a matching result, context, plotting data and manifest |
| TER-03 | No live-app screenshot path is used |
| TER-04 | Invented fields, operations, metrics and units are rejected |
| TER-05 | Visually proposed structure remains a hypothesis until a check executes |
| TER-06 | Duplicate proposals reuse existing results |
| TER-07 | Contradictory or weakened evidence survives synthesis and export |
| TER-08 | A high Jev preference cannot override an invalid Terra proposal |
| TER-09 | Narrative quantities resolve to artifacts; unverified prose remains interpretation |
| TER-10 | Model errors use held-out memberships and correct contexts |
| TER-11 | Request, image, operation and deadline budgets stop the loop |
| TER-12 | Null or unanswerable cases support abstention |
| TER-13 | Color/label changes preserve factual bindings and are evaluated for proposal sensitivity |
| TER-14 | Replaying packets and syntheses causes no API calls |
| TER-15 | Text-only and visual conditions receive identical underlying plotting data |

Implement the integration and evaluation harness in the same final build session. No user study or screenshot gate is added. Controlled tests can establish readiness now; live comparative results await the owner’s API key.

The research-backed proposal is therefore to use Terra to expand and connect the investigation, while computation and evidence contracts decide what can be stated as measured fact.
