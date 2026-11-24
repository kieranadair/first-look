# First Look research evidence register

This research register connects First Look’s implementation requirements to the evidence that motivates them. It complements the build specification and the [detailed academic synthesis](https://chatgpt.com/space/page_1ef7fe0cf80c8191b32880a2fc23b869).

A study can validate a particular perceptual effect, interface comparison or predictive benchmark result without validating this integrated app. Each pattern below preserves that distinction. Software API behavior comes from official documentation; limits, ranking weights, budgets and acceptance targets are engineering choices.

# 1 Visualization perception and design

## R01 Graphical perception

Cleveland and McGill studied accuracy for elementary graphical judgments. Heer and Bostock investigated crowdsourced replication and extensions. These support choosing encodings with attention to the perceptual task, especially where precise comparison matters.

Implementation: prefer position-based comparisons for exact magnitude tasks; retain readable axes, units and support. Provide valid alternatives where the user’s task changes.

Anti pattern: convert a perceptual ranking into a rule that one chart is always best for every dataset and task.

Checks: VIS-01 through VIS-05 validate chart eligibility and scale behavior; browser checks assess access and structural readability. They do not reproduce the original experiments.

Sources: [Cleveland and McGill](https://doi.org/10.1080/01621459.1984.10478080), [Heer and Bostock](https://idl.uw.edu/papers/crowdsourcing-graphical-perception).

## R02 Task dependence

Saket and colleagues and Kim and Heer evaluate chart effectiveness under different tasks and data conditions. The practical implication is that chart selection must include the analytical question.

Implementation: ChartSpec contains task and question, not just field types. A comparison, distribution and relationship can require different valid views of the same fields.

Anti pattern: choose a chart from physical column types alone and call it optimal.

Source: [Task Based Effectiveness](https://arxiv.org/html/1709.08546), [Kim and Heer](https://idl.uw.edu/papers/task-data-effectiveness).

## R03 Scale and aggregation

Work on truncated axes and aggregation choices shows that presentation and summary choices can affect interpretation. The scope of those effects depends on the task and stimulus.

Implementation: zero-baseline magnitude bars; explicit domains; comparable challenge scales; distributions behind averages; alternative summaries and aggregations.

Anti pattern: assume an axis-break marker eliminates exaggeration, or assume a mean describes a group adequately.

Sources: [Truncating the Y Axis](https://arxiv.org/html/1907.02035v2), [Aggregation choices](https://mucollective.northwestern.edu/files/2020-effects-aggregation-choices.pdf).

## R04 Stephen Few

Few’s books, essays and practical guidance supply a substantial design corpus about analytical comparison, context, clutter, dashboards and chart choice. They are expert design guidance, not one experimentally validated selection algorithm.

Implementation: a small conditional rule registry with examples and counterexamples. Preserve the repository’s public article index and relevant-topic index as research artifacts. Link a rule to the actual relevant source.

Anti pattern: claim that every recommendation across Few’s work is a universal law, or that an index proves exhaustive interpretation of his writing.

Source: [Perceptual Edge public library](https://www.perceptualedge.com/library.php).

# 2 Semantic interpretation and constrained recommendation

## R05 Contextual semantic typing

Sherlock, Sato and Doduo investigate semantic column annotation using values and context under their respective training and evaluation conditions.

Implementation: combine value profiles, field context and supplied descriptions; retain hypotheses and unknown; allow correction; distinguish physical type from analytical role.

Anti pattern: infer an organization’s metric definition, measurement unit or causal meaning merely because a classifier returned a type.

Checks: SEM-01 through SEM-05 cover numeric identifiers, ambiguous roles, ordinal order, invalid unit combinations and dependency invalidation.

Sources: [Sherlock](https://vis.csail.mit.edu/pubs/sherlock/), [Sato](https://arxiv.org/abs/1911.06311), [Doduo](https://arxiv.org/abs/2104.01785).

## R06 Explicit constraints

Draco formalizes visualization knowledge as constraints. Too Many Cooks investigates extracting and comparing recommendation rules across systems, illustrating agreement and disagreement in design knowledge.

Implementation: distinguish hard validity from task-dependent preferences. Keep an inspectable record of applied rules and rejected alternatives.

First Look implements a compact Python rule registry and compiler inspired by this work. It does not claim to implement Draco’s solver or inherit its evaluated performance.

Anti pattern: let a model’s relevance score override incompatible units, unsupported aggregation or invalid scale domains.

Sources: [Draco](https://idl.uw.edu/papers/draco), [Too Many Cooks](https://arxiv.org/abs/2308.14241).

# 3 Discovery and mixed initiative analysis

## R07 Bounded candidate search

SeeDB and Foresight investigate automatically finding and prioritizing useful or salient views under defined search and ranking objectives.

Implementation: enumerate a finite typed catalog; compute statistics first; preserve candidate families and exclusions; select a diverse shortlist.

Anti pattern: treat the largest correlation, most surprising aggregate or highest selected significance as a universal measure of analytical value.

The initial ranking weights, six-card display and candidate caps are engineering hypotheses. They are not copied as validated constants from these systems.

Sources: [SeeDB](https://www.vldb.org/pvldb/vol8/p2182-vartak.pdf), [Foresight](https://arxiv.org/html/1707.03877).

## R08 Mixed initiative interaction

Voyager 2, DataSite and Lux explore recommendations integrated with interactive analysis. Their evaluations concern specified interfaces and tasks.

Implementation: recommendations remain editable; the user can correct semantics, steer a focus, select a subset and launch a follow-up through the same pipeline.

Anti pattern: produce a fixed automatic narrative that cannot be corrected or investigated.

No user study is scheduled inside this build. Automated workflow checks establish functional support for these interactions, not measured improvements in human analytical performance.

Sources: [Voyager 2](https://idl.uw.edu/papers/voyager2), [DataSite](https://arxiv.org/html/1802.08621), [Lux](https://arxiv.org/html/2105.00121).

# 4 Statistical reliability under discovery

## R09 Multiple comparisons

Research on visual multiple comparisons examines how searching many views can increase false findings.

Implementation: retain the search family; avoid ranking uncorrected p-values; label discovery as exploratory; include independent-data fixtures and negative results.

Anti pattern: attach a significance claim to the selected winners without accounting for how they were selected.

A restrained null fixture is a useful regression test, not a proof of a universal false-discovery rate.

Source: [Investigating multiple comparisons in visual analysis](https://cs.brown.edu/research/ptc/assets/publications/zgraggeninvestigating.pdf).

## R10 Adaptive reuse

Adaptive-analysis research formalizes risks from repeatedly using a dataset or holdout to choose subsequent questions.

Implementation: record adaptive follow-ups and exact model memberships. Do not promote a repeatedly inspected holdout to fresh confirmatory evidence.

Anti pattern: present every model-driven follow-up as an independent validation simply because it uses previously held-out rows.

Source: [Adaptive analysis and holdout reuse](https://arxiv.org/abs/1506.02629).

## R11 Uncertainty communication

Uncertainty evaluation research distinguishes accuracy, interpretation and decision outcomes. One interval or confidence number does not represent every source of uncertainty.

Implementation: distinguish semantic uncertainty, sampling limitations, descriptive sensitivity, predictive error and provider preference. Resampling defaults are diagnostic and do not automatically produce inferential confidence intervals.

Anti pattern: collapse all uncertainty into a green “confidence” score.

Source: [Uncertainty evaluation survey](https://idl.uw.edu/papers/uncertainty-eval-survey).

# 5 Tabular foundation models and decision models

## R12 Tabular model performance

TabPFN and TabICLv2 provide evidence for tabular foundation-model prediction under their evaluated tasks and protocols. TabArena and TabReD motivate careful comparison across methods and realistic evaluation settings.

Implementation: use a specific backend, explicit task, appropriate split, recorded preprocessing, held-out diagnostics, baselines and resource budgets.

The required Cloud backend is hosted TabPFN for deployment practicality. This engineering choice does not establish that it outperforms TabICL or conventional methods in every use case.

Anti patterns: equate prediction with causality; use training residuals as independent evidence; assume a benchmark result transfers to an arbitrary dataset or later hosted model version.

Sources: [TabPFN](https://doi.org/10.1038/s41586-024-08328-6), [TabICLv2](https://arxiv.org/abs/2602.11139), [TabArena](https://arxiv.org/abs/2506.16791), [TabReD](https://arxiv.org/abs/2406.19380).

## R13 Jev as a bounded component

The independent Jev classification, bias and ordinal-scale studies cited in the synthesis are recent preprints. They motivate bounded judgments, probability evaluation, option-order checks and abstention; they do not validate this app’s recommendation tasks.

Implementation: Jev chooses among complete eligible alternatives, assesses a short relevance rubric or chooses an applicable challenge. Code handles calculations, dependency resolution, validity and rendering.

What Jev can fill in a visualization contract: a selected semantic hypothesis, an analytical intent or eligible candidate ID, a preference among valid templates, and a choice of next supported check.

What it cannot establish: the correct statistic by assertion, a scientific denominator absent from the data, causal meaning, independent model evaluation, arbitrary executable chart callbacks, or truth through high confidence.

What it needs: compact state, computed evidence, explicit option definitions, task context, support and limitations, unknown/none options, calibrated application policy and a benchmark of the actual decisions.

Anti patterns: assume confidence is accuracy; treat independent answers as conditionally coordinated; invent reasoning traces; hide a deterministic fallback as a model decision.

Sources: [Benchmark](https://arxiv.org/abs/2609.37647), [Bias study](https://arxiv.org/html/2610.19619v1), [Ordinal scale study](https://arxiv.org/html/2609.38827v2).

## R14 Calibration and selective prediction

Calibration and selective-classification work provides evaluation concepts for probabilities and abstention. Guarantees from those settings do not automatically apply to Jev or a shifted user dataset.

Implementation: measure proper scoring rules where labels support them, calibration with uncertainty, coverage and error at policy thresholds, and sensitivity to presentation changes.

Anti pattern: import an unverified numerical guarantee or declare a threshold scientifically validated because it seems conservative.

Sources: [Calibration](https://proceedings.mlr.press/v70/guo17a.html), [Selective classification](https://arxiv.org/abs/1705.08500).

# 6 Evaluation accessibility and reproducibility

## R15 Visualization evaluation

VisEval evaluates generated visualizations beyond whether code executes. Algebraic visualization design supplies a way to reason about transformations and invariants.

Implementation: separate numerical correctness, analytical validity, chart-contract validity, interaction behavior and textual claims. Use metamorphic tests for transformations that should preserve an analytical result.

Anti pattern: report success because the renderer produced a chart or an output passed JSON validation.

Sources: [VisEval](https://arxiv.org/html/2407.00981), [Algebraic visualization design](https://doi.org/10.1109/TVCG.2014.2346325).

## R16 Accessible explanations

Research on accessible visualization descriptions distinguishes multiple levels of chart description and interpretation.

Implementation: supply a short chart name, readable computed observation, support and tabular alternative. Keep user interpretation distinct. Use keyboard-accessible controls and non-color-only status.

Anti pattern: assume a short alt string makes a complex interactive chart fully accessible.

Source: [Visualization text model](https://vis.csail.mit.edu/pubs/vis-text-model/).

## R17 Reproducible investigation

The bundle contract is an engineering synthesis of provenance and reproducibility requirements, informed by the statistical and evaluation literature above.

Implementation: distinguish saved-artifact inspection, deterministic recomputation and live model re-execution; preserve exact memberships, decisions and versions; test replay in a fresh process.

Anti pattern: call a prose export reproducible, or promise exact live hosted-model reruns when the service version is unavailable.

The bundle format itself is a proposed application design, not a published validated standard.

# 7 Verified implementation interfaces

| Source | Verified implication for the build |
| --- | --- |
| [Streamlit skills](https://docs.streamlit.io/develop/api-reference/cli/skills) | Official skills can be installed for the current project and track the installed Streamlit package |
| [Native ECharts](https://docs.streamlit.io/develop/api-reference/charts/st.echarts_chart) | Declarative chart specs and normalized selection events; unsupported JavaScript-dependent chart families are excluded |
| [Fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment) | Independent reruns and optional controlled parallel execution |
| [Themes](https://docs.streamlit.io/develop/api-reference/configuration/config.toml) | Native theme tokens support the visual system without a custom frontend |
| [Fonts](https://docs.streamlit.io/develop/concepts/configuration/theming-customize-fonts) | Local font files can be declared and served with the app |
| [App testing](https://docs.streamlit.io/develop/concepts/app-testing/cheat-sheet) | AppTest covers much app behavior but does not natively drive chart selections |
| [Agent access](https://docs.streamlit.io/develop/concepts/ai-agents/agent-access) | Runtime inspection can occur without taking screenshots |
| [Cloud management](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app) | Shared variable resource limits require bounded local work |
| [Cloud status](https://docs.streamlit.io/deploy/streamlit-community-cloud/status) | Repository-root behavior affects entrypoint and asset configuration |
| [Cloud secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management) | Owner credentials belong in Cloud Secrets or an ignored local file |
| [TypeSafe API](https://docs.typesafe.ai/introduction/quickstart) | Use the official systemone endpoint and SDK primitives |
| [TypeSafe SDK](https://github.com/typesafe-ai/typesafe-sdk-python) | Python system_one returns typed answers |
| [TabPFN client](https://github.com/PriorLabs/tabpfn-client) | Hosted model inference and token authentication avoid local weights |
| [TabPFN async jobs](https://docs.priorlabs.ai/capabilities/async-jobs) | Submit and wait operations support a responsive Python job controller |
| [TabPFN dependencies](https://raw.githubusercontent.com/PriorLabs/tabpfn-client/main/pyproject.toml) | Resolve bounded client dependency ranges before pinning deployment requirements |
| [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | Parse bounded semantic and question schemas; handle refusal and incomplete responses |
| [GPT-6.1 Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra) | A verified text-and-image model supporting structured outputs; the investigation role and tests are specified in terra-integration.md |

The installed Streamlit 1.67 documentation was also inspected locally, including the responsive st.grid API. Build-time interface checks should use the locked environment’s documentation.

Sources are current research and interface evidence as of 20 November 2026. Historical Cloud resource figures are not a permanent capacity guarantee. Hosted model aliases and service terms should be recorded at actual use rather than assumed immutable.

# 8 Terra investigation integration

R18 adds a generative hypothesis and cross-view synthesis layer, using exact tables with independently rendered analytical chart assets. It complements Jev’s bounded decisions and the tabular model’s held-out diagnostics. The detailed findings, evidence limits, interface, new contracts and TER-01 through TER-15 tests are in [terra-integration.md](terra-integration.md).

The key sources are [Same Stats Different Graphs](https://www.research.autodesk.com/publications/same-stats-different-graphs/), [DePlot](https://aclanthology.org/2023.findings-acl.660/), [LIDA](https://aclanthology.org/2023.acl-demo.11/), [Data Formulator 2](https://www.microsoft.com/en-us/research/publication/data-formulator-2-iteratively-creating-rich-visualizations-with-ai/), [InsightBench](https://proceedings.iclr.cc/paper_files/paper/2025/hash/0dfe31d6e703e138d46a7d2fced38b7c-Abstract-Conference.html), [Chart-to-Text](https://aclanthology.org/2022.acl-long.277/), [ChartQAPro](https://aclanthology.org/2025.findings-acl.978/), and [ChartCheck](https://aclanthology.org/2024.findings-acl.828/). Plotly’s direct Terra evaluation is an industrial benchmark report, not a peer-reviewed validation of First Look.
