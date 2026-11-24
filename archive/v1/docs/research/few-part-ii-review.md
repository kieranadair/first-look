# First Look: learning from Part II of Now You See It

Subsequent implementation: the selected uplift is delivered in First Look 0.3; see [build report](../development/exploration-uplift.md). The review below preserves its original research-stage findings and evidence boundaries.

Research and design review, 22 November 2026. Application baseline: First Look 0.2, commit `6f151db7d8ebcee485769c44dc24615b0c592c0f`.

## Recommendation

The next release should make exploration **accurate, comparative and continuous**. The current semantic contract establishes whether a calculation is permissible; the next layer should establish what analytical question it answers, which perspectives have actually been examined, and how related views can be compared without losing their reference population.

This means repairing three concrete representation problems first, then building a small, coordinated comparison workbench over the existing algebra. A larger chart gallery, unrestricted model agents, automatic clustering or forecasting would add complexity before addressing the main limitations.

This is a proposal, not an implemented uplift. Runtime code and deployment configuration were not changed. Original synthesis, an engineering plan and synthetic audit evidence were saved. No paid providers, app screenshots or user study were used.

## Scope and method

Source: Stephen Few, *Now You See It: An Introduction to Visual Data Sensemaking*, second edition, Analytics Press, 2020, ISBN 9781938377129. Only **Part II, Getting the Lay of the Land**, was considered: its introduction on printed pp. 97–106 and Chapters 5–11 on pp. 107–252. Part III's statistical process control chapter is outside this review.

A separate sub-agent read each of the seven chapters, compared it with the repository's research and actual implementation, checked substantive lessons against primary papers or official methodological/technical sources, and proposed at most three additions. The primary agent read the Part II introduction, audited cross-cutting behavior, independently reproduced key findings and selected a coherent combined scope. Chapter reviews remain in the ignored `reports/few-section2/` working area; the supplied book/chapter extracts remain outside the repository.

The attachment is an imperfect OCR transcription. Printed-page pointers refer to its page markers and contents; illustrations were not independently inspected. Claims about actual images, colors or perceptual quality cannot be established from this attachment alone. Recommendations based on figure descriptions were checked against their accompanying prose and external research. None of the source studies establishes this app's productivity or validates our proposed engineering defaults.

Evidence types used here: **M** mathematical invariant or counterexample; **S** statistical methodology with stated assumptions; **E** empirical study within its task/sample; **O** official API, standard or implementation behavior; **X** expert guidance; **H** proposed product design requiring evaluation. Code probes establish current behavior, not human comprehension.

## What the app already has

Do not rebuild the semantic uplift. First Look already supports editable roles, entity/value grain, sums and distinct counts, weighted means, entity averages, explicit ratios, snapshot/counter definitions, unit/transform restrictions, hierarchy/membership evidence, observation schedules, scoped gap handling, exact contexts and evidence replay. It has histograms, ECDFs, grouped boxes, correlations, conditional medians, subgroup/extreme/rank challenges and held-out model/error diagnostics.

Jev already chooses among eligible alternatives. Terra already receives bounded matched chart/table evidence and can propose executable checks. Hosted TabPFN and local baselines already share a held-out protocol. Those strengths are inputs to the next design, not evidence that all relevant angles are already covered.

The current UI presents a lead finding and six/twelve cards. Selection in the inspector can create a filtered context, clearing the current investigation and model. Pins preserve old snapshots, but there is no live selected/reference comparison. A diverse shortlist is useful; it is different from a task-oriented overview or a coordinated set of perspectives.

## Chapter-by-chapter synthesis

| Chapter and printed pages | Lesson worth retaining | Synthesis into First Look | Qualification / deliberate omission |
| --- | --- | --- | --- |
| **5. Categorical variation**, 107–124 | Counts, totals, typical size, ranking and contribution reveal different aspects of a category. | Rank by the requested metric; expose support/exposure; compare approved count/amount/entity-average definitions; preserve identities and Other membership across alternatives. Later add measured concentration over original parts. | Observed rank is not underlying performance. Do not invent an exposure, treat Other as a real category, or infer an 80/20 law. Treemaps and slope/stacked charts are not prerequisites. |
| **6. Quantitative variation**, 125–164 | Shape, tails and group mixtures can disappear behind averages. | Repair ECDF compression; add two-group ECDF/quantile comparison and explicit histogram sensitivity; use more than between-mean separation to propose a useful group comparison. | Mean/SD do not require normality merely to be valid descriptive summaries. Mixtures need not be multimodal; peaks are not verified populations; fences do not identify errors. No automatic data deletion or normalizing every column. |
| **7. Spatial variation**, 165–176 | A map is useful when location or spatial arrangement answers the question. | Add geographic meaning/intent and model-transfer checks; retain ranked metric views when the task is magnitude comparison. | No default geocoding/map expansion this round. Bubble versus choropleth choice is task-dependent. CRS, geographic identity, rates/exposure, spatial dependence and aggregation effects need contracts before maps. |
| **8. Temporal variation**, 177–202 | Level, growth, temporal scale, recurring phase and smoothing are different questions. | Reuse the temporal engine for semantic aggregation sensitivity and a small calendar-context companion; retain raw chronological evidence. Later add complete-window smoothing or common-baseline comparison under explicit eligibility. | Do not inherit whole-upload coverage into arbitrary selections, average rates, connect unknown observations as measured, or choose a lag because it maximizes correlation. Forecasting and inflation conversion are separate projects. |
| **9. Quantitative relationships**, 203–234 | Direction, shape, spread, unusual combinations and influence are distinct. | Show conditional center **and spread**; preserve complete sampling scope; add bounded influence diagnostics and, later, exact density summaries for overdraw. | Zero Pearson/Spearman or a flat conditional mean does not imply independence. Predictive accuracy and conditioning do not establish causality. Do not sweep smoothers/models until a preferred result appears. |
| **10. Categorical relationships**, 235–238 | A pattern can depend on the intersection of categories and on what lies inside each cell. | Extend the existing joint-count heatmap into bounded conditional comparisons: explicit marginal denominators and a few shared-scale cell/facet companions. | Counts, whole-table shares, row shares, column shares and cell-specific rates must remain distinct [R19]. A matrix full of independently scaled plots is not automatically comparable. |
| **11. Multiple perspectives**, 239–252 | Related views reveal information that separate visits can leave disconnected. | Preserve an anchored reference and a deliberate selected cohort; compute two or three compatible companions with common encoding definitions and a visible coverage record. | A card grid and saved pins are not linked analysis. Do not promise synchronized native brush geometry. Parallel coordinates, embeddings and clustering need their own semantics/evaluation and are deferred. |

The introduction's pp. 97–106 supplies the organizing idea: an overview establishes context for later questions. Its useful modernization is a finite record of supported perspectives and their examination status. It is not a claim that software can prove the dataset has been understood exhaustively.

## Verified current gaps

Numerical evidence is recorded in [few-part-ii-probes.json](few-part-ii-probes.json). These are independently constructed synthetic cases, not book/OCR examples or app screenshots.

### 1. Category selection can answer a frequency question instead of the stated metric question

`firstlook/semantic/engine.py` groups and sorts by source-row count before evaluating the metric and collapsing Other. In the root probe, category totals were 40, 40 and 1,000, with row counts 40, 4 and 1. With two display slots, the result named the first category with 40 and showed an Other total of 1,040; the largest original category was not named. An independent chapter probe reproduced the same issue at the default display limit.

A ranking task must evaluate eligible original groups before selecting by the declared quantity. An initial metric ranking and a paired comparison need different policies: the former selects the relevant extremes; the latter fixes identities/order/remainder membership so ranks can change without changing what is compared. Other must continue to recompute from its source union, especially for means, ratios and allocated entity values. **Evidence: M/code; interpretation of rank uncertainty: S [R06].**

### 2. An ECDF can have exact retained vertices and a misleading compressed staircase

`firstlook/discovery.py` chooses up to 1,200 locations evenly over distinct-value positions. A valid 50,000-row fixture has values 0…1200 once and 48,799 additional copies of 1199. The location 1199 is omitted. Its true cumulative probability is 0.99998; the displayed post-step segment at that threshold is 0.02398, an error of 0.976. The native spec uses `step=end`; the analytical renderer uses the corresponding post-step convention.

This is a probability-mass fidelity problem, not a claim about screenshot appearance: the horizontal displacement is only one unit on a 1,200-unit range. It matters for threshold interpretation, zooming and selecting a representation with a stated error guarantee. Compression should respect observation ranks/tied mass and certify the actual approximation error. For the proposed observed-location subset method, source-threshold checks with defined endpoint extensions suffice; methods that introduce other jumps require checking both sides of source and rendered jumps. Exact threshold queries, quantiles and reported group CDF distances must use underlying values, independently of display compression. An explicitly approximated CDF distance needs its own disclosure and error bound, at most the sum of the two curves' certified errors. Retained-vertex exactness is insufficient. **Evidence: M/code; quantile conventions: S/O [R08].**

### 3. Statistical sampling and display sampling are conflated

A 6,000-row relationship computes statistics on all 6,000 pairs and plots 5,000 marks. Its current `metadata.sampled` is false and there is no sampling warning. The flag tracks a different 20,000-row statistical cap. Record statistical rows, display rows and Terra review rows separately, including exact memberships, omission counts, scheme and seed. A visible-mark selection is not automatically a selection of every source record in the visual region. **Evidence: code; overdraw motivation: E/design [R10].**

### 4. Conditional-center screening misses variance-only structure

In a 400-row fixture `y=+x` or `−x` at each observed x, Pearson and Spearman are zero and every conditional-bin median is zero. The five IQRs increase 40.5, 120.5, 200.5, 280.5, 360.5. The current discovery returns no relationship/shape finding. Its conditional summary already computes quartiles, but the line encodes only the median.

Add a bounded spread witness and render the recorded quartiles. This is a missing analytical perspective, not proof of a general dependence detector. A point-prediction model can also miss it because the optimal conditional mean is constant. Terra cannot notice an unrendered pair absent from its packet. **Evidence: M/code; shape counterexamples and residual methodology: [R09,R11].**

### 5. Comparison and search scope need explicit representation

Current chart domains are computed per artifact; semantic checks compare some result lists by position. New metric ranking would make positional comparison unsafe. `AnalysisPlan.question` is free text, while the decision to rank, compare shape or inspect conditional variation is not a first-class task contract. Discovery caps and positional slices can exclude fields before ranking; for example, a focus outside the first 40 numeric fields cannot enter the current pair list. No unexamined field should be described as showing no relationship.

The same metadata must govern comparisons, not merely accompany them. Stable keys, denominator populations, reference-fitted transforms, shared bins/domains where appropriate, and complete search statuses belong in the execution contract. These controls are motivated by comparative-visualization work and task taxonomies [R01–R04]; the proposed implementation remains H.

## Research-backed patterns and anti-patterns

| Pattern | Anti-pattern to prevent | Basis and practical boundary |
| --- | --- | --- |
| Explicit task + semantic eligibility | Treating a numeric column and a valid chart as a complete analytical question | Task abstraction separates why/what/how; a taxonomy supports design, not a measured productivity guarantee. [R01,R02] |
| Overview with finite coverage + drill-down | Letting a few large correlations stand in for an overview; equating card count with understanding | Voyager 2 increased field coverage in its controlled study while supporting focused work. Coverage here means recorded coverage of our catalog, not every possible truth. [R03] |
| Selected/reference companions | Replacing the reference whenever a selection is applied; silently comparing different category sets | Coordinated interactions and global encoding consistency motivate continuity; they introduce tradeoffs rather than one universal layout. [R04] |
| Metric-specific rank with exposure/support | Ranking totals by row count or tiny-denominator rates as reliable performance | Exact ranking is arithmetic; generalizing performance requires a suitable model and uncertainty assumptions. [R06] |
| Full distribution and conditional spread | Assuming equal means, zero correlation or a good conditional-mean fit means no relevant difference | Constructive counterexamples and model diagnostics show information lost by reductions. [R08–R11] |
| Explicit shape/scale/normalization recipes | Independently choosing bins or axes in each panel, then attributing visual differences to data | Histogram/quantile methods have assumptions and conventions; group counts, proportions and density answer different questions. [R07,R08] |
| Preserve observations; audit sensitivity | Deleting extremes because a fence, model or residual flags them | Residual, leverage and influence differ; skewed data can yield many conventional boxplot extremes. [R11] |
| Search history plus bounded stopping | Calling repeated exploratory checks confirmation, or reusing a tuned holdout as fresh validation | Visual multiple-comparison experiments and adaptive-analysis theory document this risk. No generic FDR guarantee is added here. [R05,R12] |
| Time, entity and geographic task contracts | Treating every observation as exchangeable, every coordinate as an ordinary scalar target, or hosted TabPFN as an automatic forecaster | Evaluation must match transfer and quantity geometry. Existing coordinates can be useful predictors for a declared task; they should not silently choose that task. [R13,R14,R17] |
| Structured model proposals over measured evidence | Asking a model to establish a denominator, normality, business cause or genuine cluster from a picture | Newer AI makes navigation and synthesis more plausible. It does not supply missing design assumptions or establish its own correctness. [R15–R17] |

## Book guidance that needs adaptation

The point is to preserve Few's analytical discipline while testing his prescriptions.

- Normality is not required to calculate or use a finite-data mean or SD descriptively. Their sensitivity and relevance differ from the assumptions of particular inferential procedures. Pair them with robust summaries and shape; do not add an automatic normality gate. [R07]
- Heterogeneous populations do not necessarily produce multiple modes. The height paper cited in Chapter 6 specifically qualifies that inference. Peaks cannot count latent business groups. [R07]
- The supplied introduction's signed-residual-sum wording, interpreted literally, is not a goodness-of-fit criterion: residuals can cancel. Our synthetic residuals sum to zero with RMSE about 8.165. Use appropriate losses and residual patterns; existing modeling metrics already do this. OCR uncertainty also counsels against assuming every wording issue reflects the original typesetting. [R11]
- A 40-point change from index 103 to 143 is approximately 38.8% relative growth. A log difference is not exactly a simple percentage change. References, elapsed time and units matter. [R13]
- Observed group differences, conditional patterns and successful prediction are useful without being causal. More conditioning can also introduce bias. Keep explanations as hypotheses unless a separate causal design supports them. [R12]
- Bars, maps, parallel coordinates, jitter, smoothing and stacking serve different tasks. Do not convert a task-specific preference into a universal hard rule. Use the simplest supported representation that answers the stated task, then evaluate additions. [R04,R06,R10,R14]

## The recommended next release

The cohesive product change is a **comparison-oriented Explore experience inside Discover**, with the existing ranked shortlist retained as one lens.

1. **Repair representation fidelity.** Metric-ranked top-K; probability-mass-aware ECDF compression with error metadata; truthful statistical/display/review sampling scopes; stable group identities. Add domain-aware automatic modeling eligibility where quantity geometry is unsupported.
2. **Preserve an anchored reference and compute deliberate companions.** A mark selection first previews its exact membership. A separate compare action computes a selected/reference bundle. Beginning a filtered investigation remains an explicit context transition. Do not weaken existing context invalidation.
3. **Make supported perspectives visible.** Show which task families are available, blocked by meaning, outside the budget, screened, computed or actually visited. Offer a useful missing perspective alongside a high-scoring finding. Apply focus before search caps.
4. **Add only the analytical witnesses that close demonstrated gaps.** First: two-group ECDF/quantile differences, conditional center/spread and a small categorical facet comparison with explicit marginal scope. Add temporal aggregation/calendar context and concentration after those shared contracts work. Influence and dense-pair counts follow as bounded extensions.
5. **Reuse the existing model stack to navigate that evidence.** Keep deterministic baseline behavior complete without keys. Extend existing Jev/Terra options and packets only for executable tasks, inside existing budgets. Evaluate incremental model benefit rather than adding another framework or provider.

Implementation contracts, module changes, acceptance fixtures and scope cuts are specified in [the next-uplift plan](../development/exploration-uplift-plan.md).

### Example analyst journey — invented, not results

An analyst opens Superstore and chooses Sales. The overview establishes row/entity grain and which analytical views are available. The categorical view offers recorded sales, order count and sales per order using approved definitions. A rare category with high recorded sales is not hidden merely because it has few rows.

The analyst selects a category and asks to compare it with the remainder. The original population remains anchored. A companion shows both distributions on the same scale and another shows approved amount/exposure components. Selecting whole orders instead of exact line rows is a deliberate choice that changes the cohort. The display explains whether it compares cohort-relative rates or shares of the anchored base.

A subgroup or time question adds one compatible companion. If missing dates cannot be interpreted under that scope, the time view preserves unknowns. If the analyst requests a categorical intersection, a small facet view shows the cells and their support; it does not silently change denominators between panels.

Jev may choose which eligible perspective deserves attention. Terra may ask whether a contrast comes from order frequency, typical amount, spread or a conditional relationship, then request the corresponding Python check. A tabular model may add held-out predictive evidence under a declared task. The final brief preserves the reference, cohort, definitions, exclusions, approximation and completed checks. None of these steps automatically declares a cause.

## Evaluation and limits

The review established three current representation defects and one distributional-screen blind spot with small, independent synthetic constructions. It did not implement their fixes. Future acceptance must include independent arithmetic/membership oracles, render-contract invariants, row/column/order/label perturbations, null and low-support cases, fresh-process replay and screenshot-free UI assertions.

Compare the current shortlist with deterministic task coverage/comparison, then optional Jev, matched text/table Terra and identical-table-plus-image Terra. Score planted-pattern recovery **and** false promotion, unsupported claims, omissions, duplicate computation, abstention, latency and memory. Never use the proposing model as the sole judge. A model cannot recover evidence excluded before its packet was built. A checked example is not a universal detector or a human-productivity result.

No extra user-testing or screenshot gate is required for the next build. Functional/analytical evidence can be collected in one build session; empirical comprehension/productivity and paid-provider uplift remain unmeasured until a separate evaluation supports them.

Defer maps/geocoding, parallel coordinates, embeddings and cluster discovery, automatic lag search, forecasts, inflation services, new causal modeling, unrestricted generated code and a large chart gallery. Each introduces additional contracts and evaluation obligations; none resolves the immediate defects or the loss of comparison context. Basic spatial meaning/task guards are still worthwhile now.

## Sources and evidence boundaries

The book is the reviewed expert source (**X**), not proof that every recommendation is experimentally validated. The sources below support specific claims; their task/sample/method limits carry into the synthesis. Primary-paper depth varies across the chapter reviews: some claims use author/publisher abstracts and official references rather than a full PDF. No claim of exhaustively reading every cited publication is made.

- **R01 — M. Brehmer & T. Munzner (2013), A Multi-Level Typology of Abstract Visualization Tasks.** Task abstraction/design framework, not an efficacy trial. [Author publication](https://www.cs.ubc.ca/labs/imager/tr/2013/MultiLevelTaskTypology/).
- **R02 — B. Shneiderman (1996), The Eyes Have It.** Task-by-data-type taxonomy and overview/filter/detail guidance. [DOI](https://doi.org/10.1109/VL.1996.545307).
- **R03 — K. Wongsuphasawat et al. (2017), Voyager 2.** Controlled evidence for increased field coverage in its interface/tasks. [Author publication](https://idl.uw.edu/papers/voyager2).
- **R04 — J. Heer & B. Shneiderman (2012), Interactive Dynamics for Visual Analysis; Z. Qu & J. Hullman (2016), Evaluating Visualization Sets.** Interaction taxonomy and consistency/local-effectiveness tradeoffs; neither certifies this app's UI. [Dynamics](https://idl.uw.edu/papers/interactive-dynamics), [Consistency](https://volitionalai.uw.edu/paper/2016-Consistency-BELIV.pdf).
- **R05 — E. Zgraggen et al. (2018), Investigating the Effect of the Multiple Comparisons Problem in Visual Analysis.** Experiment on exploratory/confirmatory use; its observed error rate is not a First Look estimate. [Paper](https://cs.brown.edu/research/ptc/assets/publications/zgraggeninvestigating.pdf).
- **R06 — J. Heer & M. Bostock (2010), Crowdsourcing Graphical Perception; H. Goldstein & D. Spiegelhalter (1996), League Tables and Their Limitations.** Perceptual-task evidence and statistical performance-ranking methodology, respectively. [Perception](https://idl.uw.edu/papers/crowdsourcing-graphical-perception), [Ranking](https://doi.org/10.2307/2983325).
- **R07 — D. Freedman & P. Diaconis (1981), On the Histogram as a Density Estimator; M. Schilling et al. (2002), Is Human Height Bimodal?; NIST location/scale references.** Histogram theory/default assumptions, mixture counterexamples and descriptive definitions. [Histogram paper](https://bayes.wustl.edu/Manual/FreedmanDiaconis1_1981.pdf), [Height](https://staff.washington.edu/tamre/IsHumanHeightBimodal.pdf), [Location](https://www.itl.nist.gov/div898/handbook/eda/section3/eda351.htm), [Scale](https://www.itl.nist.gov/div898/handbook/eda/section3/eda356.htm).
- **R08 — R. Hyndman & Y. Fan (1996), Sample Quantiles in Statistical Packages; NIST Q-Q reference.** Estimator conventions and matched quantile comparisons; no unique estimator preference inferred from the book. [Author page/errata](https://robjhyndman.com/publications/quantiles/), [Q-Q](https://www.itl.nist.gov/div898/handbook/eda/section3/qqplot.htm).
- **R09 — J. Matejka & G. Fitzmaurice (2017), Same Stats, Different Graphs; L. Wilkinson et al. (2005), Graph-Theoretic Scagnostics.** Constructive shape examples and screening design, not guarantees for arbitrary data. [Datasaurus](https://www.research.autodesk.com/publications/same-stats-different-graphs/), [Scagnostics](https://www.tableau.com/sites/default/files/2023-01/Wilkinson_Infovis-05.pdf).
- **R10 — A. Mayorga & M. Gleicher (2013), Splatterplots.** Dense-display abstraction and overdraw motivation; its GPU system is not an intended dependency. [Author manuscript](https://pmc.ncbi.nlm.nih.gov/articles/PMC4048834/).
- **R11 — R. Cook (1977), Detection of Influential Observation in Linear Regression; M. Hubert & E. Vandervieren (2008), An Adjusted Boxplot for Skewed Distributions; NIST model-validation guidance.** Model-specific influence and potential-outlier methods, not authentication or automatic deletion. [Cook DOI](https://doi.org/10.1080/00401706.1977.10489493), [Boxplot paper](https://wis.kuleuven.be/stat/robust/papers/2008/adjboxplot-revision.pdf), [Model validation](https://www.itl.nist.gov/div898/handbook/pmd/section4/pmd44.htm).
- **R12 — C. Dwork et al. (2015), Generalization in Adaptive Data Analysis and Holdout Reuse; G. Shmueli (2010), To Explain or to Predict?; J. Pearl (2009), Causal Inference in Statistics: An Overview.** Adaptive-validation and task/causal distinctions. [Adaptive analysis](https://arxiv.org/abs/1506.02629), [Prediction](https://arxiv.org/abs/1101.0891), [Causal overview](https://ftp.cs.ucla.edu/pub/stat_ser/r350.pdf).
- **R13 — R. Hyndman & G. Athanasopoulos, Forecasting: Principles and Practice, third edition; BLS percent-change guidance; tsibble implicit-missingness guidance.** Established temporal methodology and official arithmetic/API distinctions, not a seasonality guarantee. [Time graphics](https://otexts.com/fpp3/graphics.html), [Decomposition](https://otexts.com/fpp3/decomposition.html), [BLS](https://www.bls.gov/cpi/factsheets/calculating-percent-changes.htm), [tsibble](https://tsibble.tidyverts.org/articles/implicit-na.html).
- **R14 — CDC Field Epidemiology Manual; OGC CRS specification; S. Openshaw, The Modifiable Areal Unit Problem; D. Roberts et al. (2017), structured cross-validation.** Spatial meaning, aggregation and transfer distinctions. [CDC](https://www.cdc.gov/field-epi-manual/php/chapters/describing-epi-data.html), [OGC](https://docs.ogc.org/is/18-010r7/18-010r7.html), [MAUP](https://www.uio.no/studier/emner/sv/iss/SGO9010/openshaw1983.pdf), [Validation](https://doi.org/10.1111/ecog.02881).
- **R15 — Data Formulator 2 (CHI 2025).** Eight-participant evidence for iterative blended interaction in that system; borrow continuity, not unrestricted code generation or its measured effect as ours. [Microsoft Research](https://www.microsoft.com/en-us/research/publication/data-formulator-2-iteratively-creating-rich-visualizations-with-ai/).
- **R16 — InsightBench (ICLR 2025).** A multi-step analytics benchmark; planted data/model-based evaluation are not universal utility or a substitute for independent numerical oracles. [Proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/0dfe31d6e703e138d46a7d2fced38b7c-Abstract-Conference.html).
- **R17 — N. Hollmann et al. (2025), Accurate Predictions on Small Data with a Tabular Foundation Model; From Tables to Time (2025/2026).** Evaluated predictive capabilities and a separate time-series formulation, not automatic causality, business semantics or verified features of our hosted endpoint. [Nature/open text](https://pmc.ncbi.nlm.nih.gov/articles/PMC11711098/), [Temporal formulation](https://arxiv.org/abs/2501.02945).
- **R18 — Streamlit 1.67 installed `elements/echarts_chart.py`, selection-state documentation.** API selection is read-only; no imperative cross-widget brush synchronization is promised. [Public API reference](https://docs.streamlit.io/develop/api-reference/charts/st.echarts_chart). The installed version was inspected because public documentation can advance.

- **R19 — M. Gleicher et al. (2011), Visual Comparison for Information Visualization; W. Javed et al. (2010), Graphical Perception of Multiple Time Series; CDC denominator definitions; NIST contingency decomposition.** Comparison taxonomy, a task-specific line-chart study and exact conditional-count definitions. These motivate a bounded facet option, not universal facet superiority or per-cell significance. [Comparison](https://graphics.cs.wisc.edu/Papers/2011/GAWJHR11/paper.pdf), [Time-series study](https://www.cs.au.dk/~elm/pdf/multilinevis.pdf), [Denominators](https://archive.cdc.gov/www_cdc_gov/csels/dsepd/ss1978/lesson3/section2.html), [Contingency reference](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/chistest.htm).
